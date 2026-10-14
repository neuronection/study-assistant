"""Uniform BYOK contract-test matrix (family plan 17 Layer 4, §15).

Ported verbatim from the desktop reference (tests/ai-provider-setup.test.ts).
Case manifest (normative semantics, names indicative):

1.  happy path per preset — curated persisted, caps inferred, defaults bound;
2.  idempotent re-run appends the fetched catalog, never replaces, dedupes;
3.  manual-row adoption (earliest first) + preset_key stamp;
4.  never clobbers live assignments (chat/vision/stt);
5.  dead-id assignments rebind;
6.  invalid key → classified error, persists nothing;
7.  unknown preset → typed error, no fetch;
8.  hanging fetch → timeout; local refused → local_not_running;
9.  classifier table incl. suspectedVendor prefix hints;
10. snapshot-suffix curation match + zero-match fallback (curated_missed);
11. capability inference split (whisper-1 → stt; tts-* → tts);
12. set-default: task-scoped binding with capability guards + cross-provider
    rejection.

Plan 26 / ADR-0032 additions (decision capability + slots; 13/15 amended
by ADR-0036 — setup binds the `decision` default slot only):
13. bind_decision gap-fills the empty `decision` default slot (one
    assignment, one review row; kind slots inherit);
14. bind_decision=false binds nothing;
15. a live `decision` default is never clobbered (fill empty only);
16. decision-only preset (wire type `decision`) validates via the decision
    probe — ok path persists + binds, failure persists nothing;
17. probe timeout classifies `timeout`;
18. probe is no oracle without a valid key (401/402/403 classification);
19. slot separation enforced both directions + `open-args` never assignable;
20. preset catalog decision data shape (docs-verified decision presets
    ride `presetOrder`; no provisional markers remain);
21. embeddings default gap-fill (`embeddings_model` + `bind_embeddings`;
    empty slots only, never clobbers a live binding).
"""

from typing import Any

import httpx
import keyring
import pytest
from fastapi.testclient import TestClient
from keyring.backend import KeyringBackend
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.decide.systemone.probe import DecisionProbeResult
from app.ai.providers import service as service_module
from app.ai.providers import setup as byok_setup
from app.ai.providers.errors import classify_provider_error, extract_error_status
from app.ai.providers.presets import KEY_PREFIX_HINTS, PRESET_ORDER, SETUP_PRESETS
from app.ai.providers.presets import guess_preset_for_key as _guess_preset_for_key
from app.ai.providers.service import RemoteModel, infer_caps, seed_default_task_assignments
from app.core.secrets import SERVICE
from app.core.vocab import ProviderErrorCode
from app.domain.models import AiModel, DefaultTaskAssignment, Provider


class FakeKeyring(KeyringBackend):
    priority = 1

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        self._store.pop((service, username), None)


@pytest.fixture(autouse=True)
def fake_keyring(monkeypatch: pytest.MonkeyPatch) -> FakeKeyring:
    fake = FakeKeyring()
    monkeypatch.setattr(keyring, "get_password", fake.get_password)
    monkeypatch.setattr(keyring, "set_password", fake.set_password)
    monkeypatch.setattr(keyring, "delete_password", fake.delete_password)
    return fake


def install_catalog(
    monkeypatch: pytest.MonkeyPatch,
    result: list[RemoteModel] | Exception,
) -> list[tuple[str, str, str | None]]:
    calls: list[tuple[str, str, str | None]] = []

    def fake_fetch(
        provider_type: str, base_url: str, api_key: str | None, transport: Any = None
    ) -> list[RemoteModel]:
        calls.append((provider_type, base_url, api_key))
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(byok_setup, "fetch_remote_models", fake_fetch)
    return calls


def wire_catalog(model_ids: list[str]) -> list[RemoteModel]:
    return [RemoteModel(external_id=m, caps=tuple(infer_caps(m))) for m in model_ids]


def models_of(session: Session, provider_id: int | None = None) -> list[AiModel]:
    query = select(AiModel).order_by(AiModel.external_id)
    if provider_id is not None:
        query = query.where(AiModel.provider_id == provider_id)
    return list(session.scalars(query))


def seed_manual_provider(
    session: Session,
    *,
    type_: str = "openai_compatible",
    base_url: str = "https://api.openai.com/v1",
    name: str = "Manual row",
    preset_key: str | None = None,
) -> Provider:
    provider = Provider(
        name=name,
        type=type_,
        base_url=base_url,
        keyring_ref="pending",
        enabled=True,
        status=None,
        preset_key=preset_key,
    )
    session.add(provider)
    session.flush()
    provider.keyring_ref = f"provider:{provider.id}"
    session.flush()
    return provider


def add_model(session: Session, provider_id: int, external_id: str, caps: list[str]) -> AiModel:
    model = AiModel(
        provider_id=provider_id,
        external_id=external_id,
        label=external_id,
        caps=caps,
        enabled=True,
        missing=False,
    )
    session.add(model)
    session.flush()
    return model


def test_preset_metadata_uniformity() -> None:
    assert list(SETUP_PRESETS) == list(PRESET_ORDER)
    assert sorted(PRESET_ORDER) == [
        "anthropic",
        "deepseek",
        "gemini",
        "groq",
        "mistral",
        "ollama",
        "openai",
        "openrouter",
        "typesafe",
    ]
    assert PRESET_ORDER.index("typesafe") > PRESET_ORDER.index("openrouter")
    assert SETUP_PRESETS["ollama"]["local"] is True
    assert SETUP_PRESETS["gemini"]["type"] == "google"
    assert SETUP_PRESETS["gemini"]["base_url"] == "https://generativelanguage.googleapis.com"
    assert [hint["prefix"] for hint in KEY_PREFIX_HINTS] == [
        "sk-ant-",
        "sk-or-v1-",
        "gsk_",
        "AIza",
        "sk-",
    ]
    assert _guess_preset_for_key("sk-ant-api03-xyz") == "anthropic"
    assert _guess_preset_for_key("gsk_abc") == "groq"
    assert _guess_preset_for_key("totally-random") is None
    assert _guess_preset_for_key("") is None


def test_case_1_happy_path_openai_binds_chat_vision_and_stt(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, fake_keyring: FakeKeyring
) -> None:
    calls = install_catalog(
        monkeypatch, wire_catalog(["gpt-5.6-terra", "gpt-5.6-luna", "whisper-1"])
    )
    outcome = byok_setup.setup_provider_from_preset(db_session, "openai", "  sk-live-key  ")

    assert outcome.catalog_count == 3
    assert outcome.assigned_chat_model == "gpt-5.6-terra"
    assert outcome.assigned_vision_model == "gpt-5.6-terra"
    assert outcome.assigned_stt_model == "whisper-1"
    assert calls == [("openai_compatible", "https://api.openai.com/v1", "sk-live-key")]
    provider = db_session.get(Provider, outcome.provider_id)
    assert provider is not None and provider.preset_key == "openai"
    from app.core.secrets import get_secret

    stored = keyring.get_password(SERVICE, provider.keyring_ref)
    assert stored is not None and stored.startswith("enc::")
    assert get_secret(provider.keyring_ref) == "sk-live-key"
    by_id = {m.external_id: m for m in models_of(db_session, provider.id)}
    assert by_id["whisper-1"].caps == ["stt"]
    assert by_id["gpt-5.6-terra"].enabled is True
    chat = db_session.get(DefaultTaskAssignment, "text")
    vision = db_session.get(DefaultTaskAssignment, "vision")
    stt = db_session.get(DefaultTaskAssignment, "stt")
    assert chat is not None and chat.model_id == by_id["gpt-5.6-terra"].id
    assert vision is not None and vision.model_id == by_id["gpt-5.6-terra"].id
    assert stt is not None and stt.model_id == by_id["whisper-1"].id


def test_case_1_happy_path_gemini_maps_wire_type(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = install_catalog(monkeypatch, wire_catalog(["gemini-3.8-flash"]))
    outcome = byok_setup.setup_provider_from_preset(db_session, "gemini", "AIza-key")

    provider = db_session.get(Provider, outcome.provider_id)
    assert provider is not None
    assert provider.type == "google"
    assert provider.base_url == "https://generativelanguage.googleapis.com"
    assert outcome.assigned_chat_model == "gemini-3.8-flash"
    assert outcome.assigned_vision_model == "gemini-3.8-flash"
    assert calls[0][0] == "google"


def test_case_1_happy_path_ollama_keyless(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, fake_keyring: FakeKeyring
) -> None:
    calls = install_catalog(monkeypatch, wire_catalog(["llama3.3"]))
    outcome = byok_setup.setup_provider_from_preset(db_session, "ollama", "")

    provider = db_session.get(Provider, outcome.provider_id)
    assert provider is not None
    assert provider.is_local is True
    assert keyring.get_password(SERVICE, provider.keyring_ref) is None
    assert outcome.assigned_chat_model is None
    assert calls[0][2] is None


def test_case_2_re_setup_appends_the_fetched_catalog_and_dedupes(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, fake_keyring: FakeKeyring
) -> None:
    install_catalog(monkeypatch, wire_catalog(["gpt-5.6-terra", "gpt-5.6-luna"]))
    first = byok_setup.setup_provider_from_preset(db_session, "openai", "sk-first")
    manual_model = add_model(db_session, first.provider_id, "old-favorite", ["text"])

    byok_setup.setup_provider_from_preset(db_session, "openai", "sk-second")

    provider = db_session.get(Provider, first.provider_id)
    assert provider is not None
    from app.core.secrets import get_secret

    assert get_secret(provider.keyring_ref) == "sk-second"
    models = models_of(db_session, provider.id)
    assert sorted(m.external_id for m in models) == [
        "gpt-5.6-luna",
        "gpt-5.6-terra",
        "old-favorite",
    ]
    assert db_session.get(AiModel, manual_model.id) is not None
    terra_rows = [m for m in models if m.external_id == "gpt-5.6-terra"]
    assert len(terra_rows) == 1


def test_case_3_adopts_manual_row_earliest_first_and_stamps(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_catalog(monkeypatch, wire_catalog(["gpt-5.6-terra"]))
    earliest = seed_manual_provider(db_session, name="My OpenAI")
    later = seed_manual_provider(db_session, name="Other OpenAI")

    outcome = byok_setup.setup_provider_from_preset(db_session, "openai", "sk-new")

    adopted = db_session.get(Provider, outcome.provider_id)
    assert adopted is not None and adopted.id == earliest.id
    assert adopted.name == "My OpenAI"
    assert adopted.preset_key == "openai"
    reloaded_later = db_session.get(Provider, later.id)
    assert reloaded_later is not None and reloaded_later.preset_key is None


def test_case_4_never_clobbers_live_assignments(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_catalog(monkeypatch, wire_catalog(["gpt-5.6-terra", "whisper-1"]))
    provider = seed_manual_provider(db_session)
    custom = add_model(db_session, provider.id, "my-custom-model", ["text"])
    seed_default_task_assignments(db_session)
    chat = db_session.get(DefaultTaskAssignment, "text")
    vision = db_session.get(DefaultTaskAssignment, "vision")
    stt = db_session.get(DefaultTaskAssignment, "stt")
    assert chat is not None and vision is not None and stt is not None
    chat.model_id = custom.id
    vision.model_id = custom.id
    stt.model_id = custom.id
    db_session.flush()

    outcome = byok_setup.setup_provider_from_preset(db_session, "openai", "sk-key")

    assert outcome.assigned_chat_model is None
    assert outcome.assigned_vision_model is None
    assert outcome.assigned_stt_model is None
    for requires in ("text", "vision", "stt"):
        row = db_session.get(DefaultTaskAssignment, requires)
        assert row is not None and row.model_id == custom.id


def test_case_5_dead_id_assignments_rebind(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_catalog(monkeypatch, wire_catalog(["gpt-5.6-terra"]))
    seed_default_task_assignments(db_session)
    db_session.commit()
    connection = db_session.connection()
    connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    connection.exec_driver_sql(
        "UPDATE default_task_assignments SET model_id = 99999 WHERE requires = 'text'"
    )
    connection.exec_driver_sql(
        "UPDATE default_task_assignments SET model_id = 99999 WHERE requires = 'vision'"
    )
    connection.commit()
    connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    db_session.expire_all()

    outcome = byok_setup.setup_provider_from_preset(db_session, "openai", "sk-key")

    by_id = {m.external_id: m.id for m in models_of(db_session)}
    assert outcome.assigned_chat_model == "gpt-5.6-terra"
    chat = db_session.get(DefaultTaskAssignment, "text")
    assert chat is not None and chat.model_id == by_id["gpt-5.6-terra"]


def test_case_6_invalid_key_persists_nothing(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(
        provider_type: str, base_url: str, api_key: str | None, transport: Any = None
    ) -> list[RemoteModel]:
        request = httpx.Request("GET", base_url)
        response = httpx.Response(
            401, request=request, json={"error": {"message": "Incorrect API key"}}
        )
        raise httpx.HTTPStatusError(
            "Client error '401 Unauthorized'", request=request, response=response
        )

    monkeypatch.setattr(byok_setup, "fetch_remote_models", boom)

    with pytest.raises(byok_setup.SetupError) as excinfo:
        byok_setup.setup_provider_from_preset(db_session, "openai", "sk-bad")

    assert excinfo.value.classified.code.value == "invalid_key"
    db_session.rollback()
    assert list(db_session.scalars(select(Provider))) == []
    assert list(db_session.scalars(select(AiModel))) == []


def test_case_7_unknown_preset_typed_error_without_fetch(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = install_catalog(monkeypatch, wire_catalog(["gpt-5.6-terra"]))

    with pytest.raises(byok_setup.UnknownPresetError):
        byok_setup.setup_provider_from_preset(db_session, "not-a-preset", "sk-key")

    assert calls == []


def test_case_8_hanging_fetch_times_out_and_local_refused_is_local_not_running(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_catalog(monkeypatch, httpx.ReadTimeout("timed out"))
    with pytest.raises(byok_setup.SetupError) as timeout_error:
        byok_setup.setup_provider_from_preset(db_session, "openai", "sk-key")
    assert timeout_error.value.classified.code.value == "timeout"

    install_catalog(monkeypatch, httpx.ConnectError("connection refused"))
    with pytest.raises(byok_setup.SetupError) as refused_error:
        byok_setup.setup_provider_from_preset(db_session, "ollama", "")
    assert refused_error.value.classified.code.value == "local_not_running"


def test_case_9_classifier_table_and_suspectedVendor_hints() -> None:
    def status_error(status: int, message: str = "err") -> httpx.HTTPStatusError:
        request = httpx.Request("GET", "https://x.test")
        response = httpx.Response(status, request=request, text=message)
        return httpx.HTTPStatusError(message, request=request, response=response)

    def code(error: Exception, **kwargs: Any) -> str:
        return classify_provider_error(error, local_provider=False, **kwargs).code.value

    assert code(status_error(401)) == "invalid_key"
    assert code(status_error(402)) == "insufficient_credit"
    assert (
        code(status_error(400, "failed with status 400: insufficient_quota"))
        == "insufficient_credit"
    )
    assert code(status_error(429)) == "new_user_quota"
    assert (
        code(status_error(403, "ORGANIZATION_RESTRICTED: region not supported"))
        == "region_unavailable"
    )
    assert code(status_error(403, "forbidden")) == "unknown"
    assert code(httpx.ReadTimeout("aborted")) == "timeout"
    assert (
        classify_provider_error(httpx.ConnectError("ECONNREFUSED"), local_provider=True).code.value
        == "local_not_running"
    )
    assert code(httpx.ConnectError("fetch failed")) == "unknown"

    mis_pasted = classify_provider_error(
        status_error(401),
        local_provider=False,
        api_key="sk-or-v1-abc",
        attempted_preset="openai",
    )
    assert mis_pasted.code.value == "invalid_key"
    assert mis_pasted.suspected_vendor == "openrouter"
    assert (
        classify_provider_error(
            status_error(401),
            local_provider=False,
            api_key="sk-ant-api03-x",
            attempted_preset="openai",
        ).suspected_vendor
        == "anthropic"
    )
    assert (
        classify_provider_error(
            status_error(401),
            local_provider=False,
            api_key="sk-abc123",
            attempted_preset="openai",
        ).suspected_vendor
        is None
    )
    assert extract_error_status("API request failed with status 401: bad key") == 401
    assert extract_error_status("fetch failed") is None


def test_case_10_snapshot_suffix_curation_and_zero_match_fallback(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_catalog(monkeypatch, wire_catalog(["gpt-5.6-terra-2026-09-11", "gpt-oss-120b"]))
    outcome = byok_setup.setup_provider_from_preset(db_session, "openai", "sk-key")

    assert outcome.curated_missed is False
    assert outcome.catalog_count == 1
    assert outcome.assigned_chat_model == "gpt-5.6-terra-2026-09-11"

    install_catalog(monkeypatch, wire_catalog(["gpt-99-turbo", "gpt-99-mini"]))
    drifted = byok_setup.setup_provider_from_preset(db_session, "openai", "sk-key")

    assert drifted.curated_missed is True
    assert drifted.catalog_count == 2
    assert drifted.assigned_chat_model is None


def test_case_11_capability_inference_split() -> None:
    assert infer_caps("whisper-1") == ["stt"]
    assert infer_caps("whisper-large-v3") == ["stt"]
    assert infer_caps("tts-1") == ["tts"]
    assert infer_caps("tts-1-hd") == ["tts"]
    assert infer_caps("text-embedding-3-small") == ["embeddings"]
    assert infer_caps("gpt-5.6-terra") == ["text", "vision", "tools"]


def test_case_12_set_default_task_scoping_guards_and_cross_provider_rejection(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_catalog(monkeypatch, wire_catalog(["gpt-5.6-terra", "text-only"]))
    monkeypatch.setattr(service_module, "fetch_remote_models", lambda *a, **k: [])

    setup = client.post("/api/v1/providers/openai/setup", json={"api_key": "sk-test"})
    assert setup.status_code == 200, setup.text
    provider_id = setup.json()["provider"]["id"]

    tasks_before = client.get("/api/v1/tasks").json()
    chat_before = next(t for t in tasks_before if t["task"] == "chat")
    assert chat_before["model_id"] is None

    bound = client.put(
        f"/api/v1/providers/{provider_id}/set-default",
        json={"model_name": "gpt-5.6-terra"},
    )
    assert bound.status_code == 200, bound.text
    tasks_after = client.get("/api/v1/tasks").json()
    chat_after = next(t for t in tasks_after if t["task"] == "chat")
    assert chat_after["model_label"] == "gpt-5.6-terra"

    guard = client.put(
        f"/api/v1/providers/{provider_id}/set-default",
        json={"model_name": "text-only", "task": "ocr"},
    )
    assert guard.status_code == 422

    other = client.post(
        "/api/v1/providers",
        json={"name": "Other", "type": "openai_compatible", "base_url": "https://other.test/v1"},
    )
    assert other.status_code == 201, other.text
    other_id = other.json()["id"]
    shared = client.post(
        "/api/v1/models",
        json={"provider_id": other_id, "external_id": "shared-model"},
    )
    assert shared.status_code == 201, shared.text
    cross = client.put(
        f"/api/v1/providers/{provider_id}/set-default",
        json={"model_name": "shared-model"},
    )
    assert cross.status_code == 409

    custom = client.put(
        f"/api/v1/providers/{provider_id}/set-default",
        json={"model_name": "brand-new-model"},
    )
    assert custom.status_code == 200, custom.text


def test_setup_options_use_contract_names() -> None:
    options = byok_setup.SetupOptions()
    assert hasattr(options, "curated_ids")
    assert hasattr(options, "bind_chat")
    assert hasattr(options, "bind_vision")
    assert hasattr(options, "bind_stt")
    assert hasattr(options, "bind_decision")
    assert ProviderErrorCode.TIMEOUT.value == "timeout"


def test_manual_decision_model_on_any_provider(client: TestClient) -> None:
    """Manual add-model can declare the decision capability on any provider
    row (plan 26 follow-up): the transport seam is stamped from the payload
    or the one shipping transport, explicit-only (unknown transports 422),
    and cleared when the capability goes away."""
    created = client.post(
        "/api/v1/providers",
        json={
            "name": "OpenAI",
            "type": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
        },
    )
    assert created.status_code == 201, created.text
    provider_id = created.json()["id"]

    model = client.post(
        "/api/v1/models",
        json={"provider_id": provider_id, "external_id": "nimble", "caps": ["decision"]},
    )
    assert model.status_code == 201, model.text
    assert model.json()["caps"] == ["decision"]
    assert model.json()["decision_transport"] == "systemone"

    explicit = client.post(
        "/api/v1/models",
        json={
            "provider_id": provider_id,
            "external_id": "jev-latest",
            "caps": ["decision"],
            "decision_transport": "systemone",
        },
    )
    assert explicit.status_code == 201, explicit.text
    assert explicit.json()["decision_transport"] == "systemone"

    rejected = client.post(
        "/api/v1/models",
        json={
            "provider_id": provider_id,
            "external_id": "bad-transport",
            "caps": ["decision"],
            "decision_transport": "carrier-pigeon",
        },
    )
    assert rejected.status_code == 422

    model_id = model.json()["id"]
    edited = client.patch(f"/api/v1/models/{model_id}", json={"caps": ["text"]})
    assert edited.status_code == 200, edited.text
    assert edited.json()["decision_transport"] is None
    back = client.patch(f"/api/v1/models/{model_id}", json={"caps": ["decision"]})
    assert back.status_code == 200, back.text
    assert back.json()["decision_transport"] == "systemone"


def test_case_13_bind_decision_binds_the_default_slot_only(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-0036 §3: setup binds the `decision` default slot only — one
    assignment, one review row; kind slots inherit."""
    install_catalog(monkeypatch, wire_catalog(["openrouter/auto"]))
    outcome = byok_setup.setup_provider_from_preset(db_session, "openrouter", "sk-or-v1-key")

    assert outcome.assigned_chat_model == "openrouter/auto"
    assert outcome.assigned_decision_slots is not None
    assert set(outcome.assigned_decision_slots) == {"decision"}
    assert set(outcome.assigned_decision_slots.values()) == {"typesafe/jev-1.13"}
    provider = db_session.get(Provider, outcome.provider_id)
    assert provider is not None
    decision_models = [
        m for m in models_of(db_session, provider.id) if "decision" in (m.caps or [])
    ]
    assert [m.external_id for m in decision_models] == ["typesafe/jev-1.13", "~typesafe/jev-latest"]
    assert decision_models[0].decision_transport == "systemone"
    assert outcome.catalog_count == 3
    default_row = db_session.get(DefaultTaskAssignment, "decision")
    assert default_row is not None and default_row.model_id == decision_models[0].id
    for slot in (
        "decision:tool-dispatch",
        "decision:boolean-gate",
        "decision:choice",
        "decision:score",
    ):
        kind_row = db_session.get(DefaultTaskAssignment, slot)
        assert kind_row is None or kind_row.model_id is None


def test_case_14_bind_decision_off_binds_nothing(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_catalog(monkeypatch, wire_catalog(["openrouter/auto"]))
    options = byok_setup.SetupOptions(bind_decision=False)
    outcome = byok_setup.setup_provider_from_preset(
        db_session, "openrouter", "sk-or-v1-key", options=options
    )

    assert outcome.assigned_decision_slots is None
    provider = db_session.get(Provider, outcome.provider_id)
    assert provider is not None
    decision_models = [
        m for m in models_of(db_session, provider.id) if "decision" in (m.caps or [])
    ]
    assert [m.external_id for m in decision_models] == ["typesafe/jev-1.13", "~typesafe/jev-latest"]
    for slot in (
        "decision:tool-dispatch",
        "decision:boolean-gate",
        "decision:choice",
        "decision:score",
    ):
        row = db_session.get(DefaultTaskAssignment, slot)
        assert row is None or row.model_id is None


def test_case_15_bind_decision_never_clobbers_a_live_default(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_catalog(monkeypatch, wire_catalog(["openrouter/auto"]))
    live_slot = "decision"
    other = seed_manual_provider(
        db_session, name="Other", type_="decision", base_url="https://api.typesafe.ai"
    )
    live_model = add_model(db_session, other.id, "pinned-jev", ["decision"])
    live_model.decision_transport = "systemone"
    db_session.flush()
    row = db_session.get(DefaultTaskAssignment, live_slot)
    if row is None:
        row = DefaultTaskAssignment(
            requires=live_slot, model_id=live_model.id, fallback_model_id=None
        )
        db_session.add(row)
    else:
        row.model_id = live_model.id
    db_session.flush()

    outcome = byok_setup.setup_provider_from_preset(db_session, "openrouter", "sk-or-v1-b")

    assert outcome.assigned_chat_model == "openrouter/auto"
    assert outcome.assigned_decision_slots is None
    live_row = db_session.get(DefaultTaskAssignment, live_slot)
    assert live_row is not None and live_row.model_id == live_model.id


def install_probe(
    monkeypatch: pytest.MonkeyPatch,
    result: DecisionProbeResult | Exception,
) -> list[tuple[str, str, str]]:
    from app.ai.decide.systemone.probe import DecisionProbeInput

    calls: list[tuple[str, str, str]] = []

    def fake_probe(probe_input: DecisionProbeInput) -> DecisionProbeResult:
        calls.append(
            (
                probe_input.provider.preset_key or "",
                probe_input.model.external_id,
                probe_input.api_key,
            )
        )
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(byok_setup, "probe_decision_provider", fake_probe)
    return calls


def test_case_16_decision_only_preset_probe_validates_and_persists(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe_calls = install_probe(
        monkeypatch,
        DecisionProbeResult(ok=True, latency_ms=5, resolved_model="jev-1.13"),
    )
    outcome = byok_setup.setup_provider_from_preset(db_session, "typesafe", "  ts-key  ")

    assert probe_calls == [("typesafe", "jev-latest", "ts-key")]
    assert outcome.assigned_chat_model is None
    assert outcome.assigned_decision_slots is not None
    assert set(outcome.assigned_decision_slots.values()) == {"jev-latest"}
    assert outcome.catalog_count == 1
    provider = db_session.get(Provider, outcome.provider_id)
    assert provider is not None
    assert provider.type == "decision"
    assert provider.base_url == "https://api.typesafe.ai"
    models = models_of(db_session, provider.id)
    assert [m.external_id for m in models] == ["jev-latest"]
    assert models[0].caps == ["decision"]
    assert models[0].decision_transport == "systemone"
    from app.core.secrets import get_secret

    assert get_secret(provider.keyring_ref) == "ts-key"


def test_case_16_decision_only_probe_failure_persists_nothing(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_probe(
        monkeypatch,
        DecisionProbeResult(ok=False, latency_ms=5, status=401, error="bad key"),
    )

    with pytest.raises(byok_setup.SetupError) as excinfo:
        byok_setup.setup_provider_from_preset(db_session, "typesafe", "ts-bad")

    assert excinfo.value.classified.code.value == "invalid_key"
    db_session.rollback()
    assert list(db_session.scalars(select(Provider))) == []
    assert list(db_session.scalars(select(AiModel))) == []


def test_case_17_decision_only_probe_timeout_classifies_timeout(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_probe(
        monkeypatch,
        DecisionProbeResult(ok=False, latency_ms=10_000, kind="timeout", error="probe timed out"),
    )

    with pytest.raises(byok_setup.SetupError) as excinfo:
        byok_setup.setup_provider_from_preset(db_session, "typesafe", "ts-key")

    assert excinfo.value.classified.code.value == "timeout"
    db_session.rollback()
    assert list(db_session.scalars(select(Provider))) == []


def test_case_18_probe_is_no_oracle_without_a_valid_key(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_probe(
        monkeypatch,
        DecisionProbeResult(ok=False, latency_ms=5, status=403, error="forbidden"),
    )

    with pytest.raises(byok_setup.SetupError) as forbidden:
        byok_setup.setup_provider_from_preset(db_session, "typesafe", "not-a-real-key")
    assert forbidden.value.classified.code.value == "unknown"

    install_probe(
        monkeypatch,
        DecisionProbeResult(ok=False, latency_ms=5, status=402, error="no credit"),
    )
    with pytest.raises(byok_setup.SetupError) as credit:
        byok_setup.setup_provider_from_preset(db_session, "typesafe", "not-a-real-key")
    assert credit.value.classified.code.value == "insufficient_credit"
    db_session.rollback()
    assert list(db_session.scalars(select(Provider))) == []


def test_case_19_slot_separation_enforced_both_directions(
    db_session: Session,
) -> None:
    from app.ai.providers import ProviderError, assign_default_task

    chat_provider = seed_manual_provider(db_session, name="Chat")
    text_model = add_model(db_session, chat_provider.id, "gpt-x", ["text", "vision"])
    decision_provider = seed_manual_provider(
        db_session, name="TypeSafe", type_="decision", base_url="https://api.typesafe.ai"
    )
    decision_model = add_model(db_session, decision_provider.id, "jev-latest", ["decision"])
    decision_model.decision_transport = "systemone"
    db_session.flush()

    bound = assign_default_task(db_session, "decision:tool-dispatch", decision_model.id, None)
    assert bound.model_id == decision_model.id

    with pytest.raises(ProviderError, match="decision"):
        assign_default_task(db_session, "text", decision_model.id, None)
    with pytest.raises(ProviderError, match="decision"):
        assign_default_task(db_session, "decision:choice", text_model.id, None)
    with pytest.raises(ProviderError, match="unknown capability"):
        assign_default_task(db_session, "decision:open-args", decision_model.id, None)
    # ADR-0036: `decision` is the default slot — a decision model binds it.
    default_row = assign_default_task(db_session, "decision", decision_model.id, None)
    assert default_row.model_id == decision_model.id

    routed = add_model(db_session, decision_provider.id, "partial-jev", ["decision"])
    routed.decision_transport = "scoreless"
    db_session.flush()
    with pytest.raises(ProviderError, match="transport"):
        assign_default_task(db_session, "decision:score", routed.id, None)


def test_case_20_preset_catalog_decision_data_shape() -> None:
    from app.ai.providers.presets import ALL_PRESETS, PRESET_ORDER, decision_models_for_preset

    # §13.3 exposure switch flipped (2026-10-13): the docs-verified
    # decision presets ride presetOrder; no provisional markers remain.
    assert "typesafe" in PRESET_ORDER
    assert ALL_PRESETS["typesafe"]["type"] == "decision"
    assert ALL_PRESETS["typesafe"]["provisional"] is None
    assert ALL_PRESETS["typesafe"]["decision_default"] == "jev-latest"
    openrouter = ALL_PRESETS["openrouter"]
    assert openrouter["decision_default"] == "typesafe/jev-1.13"
    assert [entry["id"] for entry in openrouter["decision_models"]] == [
        "typesafe/jev-1.13",
        "~typesafe/jev-latest",
    ]
    assert all(
        entry.get("base_url_override") == "https://openrouter.ai/api"
        for entry in openrouter["decision_models"]
    )
    assert all("provisional" not in entry for entry in openrouter["decision_models"])
    ollama = ALL_PRESETS["ollama"]
    assert [entry["id"] for entry in ollama["decision_models"]] == [
        "nimble",
        "tev1",
        "clef",
        "clef-flash",
    ]
    assert ollama["decision_default"] == "nimble"
    assert ollama["key_url"] is None
    assert decision_models_for_preset("openai") == []
    for preset in ALL_PRESETS.values():
        for entry in preset["decision_models"] or []:
            assert set(entry["caps"]) <= {
                "tool-dispatch",
                "boolean-gate",
                "choice",
                "score",
            }


def test_case_20b_probe_model_id_derives_from_canonical_data() -> None:
    """§15 single-source: probe ids come from the synced preset data —
    never a code literal (family closeout fix, 2026-10-13)."""
    from app.ai.providers.presets import ALL_PRESETS, decision_probe_model_id

    # specs lead…
    assert decision_probe_model_id({"decision_models": [{"id": "custom-jev"}]}) == "custom-jev"
    # …then the declared default…
    assert decision_probe_model_id({"decision_default": "fallback-id"}) == "fallback-id"
    # …and the real catalog answers with its own data, matching what setup
    # and the test endpoint will ask the provider about.
    assert decision_probe_model_id(ALL_PRESETS["typesafe"]) == "jev-latest"
    assert decision_probe_model_id(ALL_PRESETS["openrouter"]) == "typesafe/jev-1.13"
    # A decision preset that declares neither is a data inconsistency —
    # surfaced, never papered over with an invented id.
    with pytest.raises(ValueError, match="declares no decision models"):
        decision_probe_model_id({})


def test_case_21_embeddings_default_gapfills_empty_slot(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§15 follow-up: the preset's docs-verified embeddings default
    gap-fills the empty `embeddings` slot (`bind_embeddings`, empty slots
    only — never a live binding)."""
    install_catalog(monkeypatch, wire_catalog(["gpt-5.6-terra", "text-embedding-3-small"]))
    outcome = byok_setup.setup_provider_from_preset(db_session, "openai", "sk-key")

    assert outcome.assigned_embeddings_model == "text-embedding-3-small"
    row = db_session.get(DefaultTaskAssignment, "embeddings")
    assert row is not None and row.model_id is not None
    embeddings_model = db_session.get(AiModel, row.model_id)
    assert embeddings_model is not None
    assert embeddings_model.external_id == "text-embedding-3-small"
    assert embeddings_model.caps == ["embeddings"]

    # never clobbers: a live embeddings binding survives re-setup
    other = add_model(db_session, outcome.provider_id, "my-embed", ["embeddings"])
    row.model_id = other.id
    db_session.flush()
    outcome_two = byok_setup.setup_provider_from_preset(db_session, "openai", "sk-key")
    assert outcome_two.assigned_embeddings_model is None
    db_session.refresh(row)
    assert row.model_id == other.id


def test_case_21b_bind_embeddings_off_binds_nothing(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_catalog(monkeypatch, wire_catalog(["gpt-5.6-terra", "text-embedding-3-small"]))
    options = byok_setup.SetupOptions(bind_embeddings=False)
    outcome = byok_setup.setup_provider_from_preset(db_session, "openai", "sk-key", options=options)

    assert outcome.assigned_embeddings_model is None
    row = db_session.get(DefaultTaskAssignment, "embeddings")
    assert row is None or row.model_id is None
