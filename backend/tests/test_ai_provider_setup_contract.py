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
"""

from typing import Any

import httpx
import keyring
import pytest
from fastapi.testclient import TestClient
from keyring.backend import KeyringBackend
from sqlalchemy import select
from sqlalchemy.orm import Session

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
        "anthropic", "deepseek", "gemini", "groq", "mistral",
        "ollama", "openai", "openrouter",
    ]
    assert SETUP_PRESETS["ollama"]["local"] is True
    assert SETUP_PRESETS["gemini"]["type"] == "google"
    assert SETUP_PRESETS["gemini"]["base_url"] == "https://generativelanguage.googleapis.com"
    assert [hint["prefix"] for hint in KEY_PREFIX_HINTS] == [
        "sk-ant-", "sk-or-v1-", "gsk_", "AIza", "sk-",
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
    outcome = byok_setup.setup_provider_from_preset(
        db_session, "openai", "  sk-live-key  "
    )

    assert outcome.catalog_count == 3
    assert outcome.assigned_chat_model == "gpt-5.6-terra"
    assert outcome.assigned_vision_model == "gpt-5.6-terra"
    assert outcome.assigned_stt_model == "whisper-1"
    assert calls == [("openai_compatible", "https://api.openai.com/v1", "sk-live-key")]
    provider = db_session.get(Provider, outcome.provider_id)
    assert provider is not None and provider.preset_key == "openai"
    assert keyring.get_password(SERVICE, provider.keyring_ref) == "sk-live-key"
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
    assert keyring.get_password(SERVICE, provider.keyring_ref) == "sk-second"
    models = models_of(db_session, provider.id)
    assert sorted(m.external_id for m in models) == [
        "gpt-5.6-luna", "gpt-5.6-terra", "old-favorite",
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
        classify_provider_error(
            httpx.ConnectError("ECONNREFUSED"), local_provider=True
        ).code.value
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
    assert ProviderErrorCode.TIMEOUT.value == "timeout"
