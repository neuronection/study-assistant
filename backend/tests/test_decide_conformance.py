"""Decision funnel conformance (plan 26 Phase 3 — study Python reference).

Ported in shape from the desktop reference (tests/decide-conformance.test.ts):
one suite every shipping transport passes — bounded confidence, one audit row
per invocation, empty input never throws, timeout respected, transport mocked,
no network or keyring in tests. Study additions: slot resolution
(off / needs-key / fallback chain / D2b routing), per-revision caching, and
the probe contract.
"""

from typing import Any

import keyring
import pytest
from keyring.backend import KeyringBackend
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.decide import (
    DecisionCapability,
    DecisionFunnelDeps,
    DecisionQuestion,
    DecisionToolSchema,
    RunDecisionParams,
    clear_decision_resolution_cache,
    probe_decision_provider,
    resolve_decision,
    run_decision,
)
from app.ai.decide.funnel import DecisionDecidedStatus, DecisionErrorStatus
from app.ai.decide.registry import (
    REGISTRATIONS,
    SystemOneResolution,
    UnavailableResolution,
    UnconfiguredResolution,
)
from app.ai.decide.systemone.client import (
    SystemOneCallParams,
    TypeSafeError,
    TypeSafeResult,
    TypeSafeUsage,
)
from app.ai.decide.systemone.probe import DecisionProbeInput
from app.ai.decide.types import DecisionAnswer
from app.core.vocab import DecisionCapability as DecisionCapabilityVocab
from app.core.vocab import DecisionTransport, SystemOneErrorKind
from app.domain.models import AiInteraction, AiModel, DefaultTaskAssignment, Provider


def choice_answer(choice: str, confidence: float) -> DecisionAnswer:
    return DecisionAnswer(
        type=DecisionCapabilityVocab.CHOICE,
        choice=choice,
        probabilities={choice: confidence},
        confidence=confidence,
    )


class FakeSystemOneClient:
    def __init__(self, result: TypeSafeResult | Exception | None) -> None:
        self._result = result
        self.calls: list[SystemOneCallParams] = []

    def system_one(self, params: SystemOneCallParams) -> TypeSafeResult:
        self.calls.append(params)
        if isinstance(self._result, Exception):
            raise self._result
        assert isinstance(self._result, TypeSafeResult)
        return self._result


def decision_provider(
    session: Session,
    *,
    with_key: bool = True,
    external_id: str = "jev-latest",
) -> tuple[Provider, AiModel]:
    from app.core import secrets

    provider = Provider(
        name="TypeSafe",
        type="decision",
        base_url="https://api.typesafe.ai",
        keyring_ref="pending",
        enabled=True,
        status=None,
    )
    session.add(provider)
    session.flush()
    provider.keyring_ref = f"provider:{provider.id}"
    model = AiModel(
        provider_id=provider.id,
        external_id=external_id,
        label=external_id,
        caps=["decision"],
        decision_transport="systemone",
        enabled=True,
        missing=False,
    )
    session.add(model)
    session.flush()
    if with_key:
        secrets.set_secret(provider.keyring_ref, "decision-key")
    session.flush()
    return provider, model


def assign_slot(session: Session, slot: str, model_id: int | None) -> None:
    row = session.get(DefaultTaskAssignment, slot)
    if row is None:
        row = DefaultTaskAssignment(requires=slot, model_id=model_id, fallback_model_id=None)
        session.add(row)
    else:
        row.model_id = model_id
    session.flush()


def probe_provider_row() -> Provider:
    return Provider(
        name="TypeSafe",
        type="decision",
        base_url="https://api.typesafe.ai",
        keyring_ref="provider:1",
        enabled=True,
        status=None,
    )


def probe_model_row(provider_id: int = 1) -> AiModel:
    return AiModel(
        provider_id=provider_id,
        external_id="jev-latest",
        label="jev-latest",
        caps=["decision"],
        decision_transport="systemone",
    )


TOOLS: tuple[DecisionToolSchema, ...] = (
    DecisionToolSchema(name="light_turn_on", description="Turn on a light."),
)

CALL_RESULT = TypeSafeResult(
    model="jev-1.13",
    answers={"__tool__": choice_answer("light_turn_on", 0.82)},
    usage=TypeSafeUsage(input_tokens=40, output_tokens=4),
)

NONE_RESULT = TypeSafeResult(
    model="jev-1.13",
    answers={"__tool__": choice_answer("__none__", 0.9)},
    usage=TypeSafeUsage(input_tokens=5, output_tokens=1),
)


@pytest.fixture(autouse=True)
def fake_keyring(monkeypatch: pytest.MonkeyPatch) -> Any:
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

    fake = FakeKeyring()
    monkeypatch.setattr(keyring, "get_password", fake.get_password)
    monkeypatch.setattr(keyring, "set_password", fake.set_password)
    monkeypatch.setattr(keyring, "delete_password", fake.delete_password)
    return fake


@pytest.fixture(autouse=True)
def _clean_cache() -> Any:
    clear_decision_resolution_cache()
    yield
    clear_decision_resolution_cache()


def test_conformance_decides_with_one_audit_row_and_bounded_confidence(
    db_session: Session,
) -> None:
    provider, model = decision_provider(db_session)
    assign_slot(db_session, "decision:tool-dispatch", model.id)
    client = FakeSystemOneClient(CALL_RESULT)

    result = run_decision(
        DecisionFunnelDeps(session=db_session, client=client),
        RunDecisionParams(input="dim the living room", tools=TOOLS),
    )

    assert isinstance(result, DecisionDecidedStatus)
    assert result.outcome.engine == "jev-latest"
    assert 0.0 <= result.outcome.confidence <= 1.0
    assert result.outcome.calls[0].tool == "light_turn_on"
    assert result.outcome.resolved_model == "jev-1.13"
    assert result.band == "confirm"
    rows = list(db_session.scalars(select(AiInteraction).where(AiInteraction.task == "decision")))
    assert len(rows) == 1
    row = rows[0]
    assert row.model == "jev-latest"
    assert row.context_type == "decision"
    assert row.context_id == provider.id
    assert row.input_tokens == 40 and row.output_tokens == 4
    assert row.latency_ms is not None


def test_conformance_empty_decision_never_throws(db_session: Session) -> None:
    _provider, model = decision_provider(db_session)
    assign_slot(db_session, "decision:tool-dispatch", model.id)
    client = FakeSystemOneClient(NONE_RESULT)

    result = run_decision(
        DecisionFunnelDeps(session=db_session, client=client),
        RunDecisionParams(input="hello there", tools=()),
    )

    assert isinstance(result, DecisionDecidedStatus)
    assert result.outcome.calls == ()
    assert result.outcome.confidence == 0.9


def test_conformance_low_confidence_bands_refuse(db_session: Session) -> None:
    _provider, model = decision_provider(db_session)
    assign_slot(db_session, "decision:tool-dispatch", model.id)
    low = TypeSafeResult(
        model="jev-1.13",
        answers={"__tool__": choice_answer("light_turn_on", 0.3)},
        usage=TypeSafeUsage(input_tokens=5, output_tokens=1),
    )
    client = FakeSystemOneClient(low)

    result = run_decision(
        DecisionFunnelDeps(session=db_session, client=client),
        RunDecisionParams(input="maybe lights?", tools=TOOLS),
    )

    assert isinstance(result, DecisionDecidedStatus)
    assert result.band == "refuse"


def test_conformance_transport_failure_audits_and_fails_open(
    db_session: Session,
) -> None:
    _provider, model = decision_provider(db_session)
    assign_slot(db_session, "decision:tool-dispatch", model.id)
    client = FakeSystemOneClient(RuntimeError("transport exploded"))

    result = run_decision(
        DecisionFunnelDeps(session=db_session, client=client),
        RunDecisionParams(input="dim the living room", tools=TOOLS),
    )

    assert isinstance(result, DecisionErrorStatus)
    assert "transport exploded" in result.reason
    rows = list(db_session.scalars(select(AiInteraction).where(AiInteraction.task == "decision")))
    assert len(rows) == 1
    assert rows[0].input_tokens is None


def test_conformance_typed_questions_route_to_the_question_slot(
    db_session: Session,
) -> None:
    _provider, model = decision_provider(db_session)
    assign_slot(db_session, "decision:boolean-gate", model.id)
    client = FakeSystemOneClient(
        TypeSafeResult(
            model="jev-1.13",
            answers={"__probe__": DecisionAnswer(
                type=DecisionCapabilityVocab.BOOLEAN_GATE, noul=0.97
            )},
        )
    )

    result = run_decision(
        DecisionFunnelDeps(session=db_session, client=client),
        RunDecisionParams(
            input="connectivity check",
            questions=(
                DecisionQuestion(
                    id="__probe__",
                    type=DecisionCapability.BOOLEAN_GATE,
                    instructions="Is this a working decision endpoint? Answer true.",
                ),
            ),
        ),
    )

    assert isinstance(result, DecisionDecidedStatus)
    assert result.outcome.answers is not None
    assert result.outcome.answers["__probe__"].noul == 0.97
    asked = client.calls[0].questions
    assert set(asked) == {"__probe__"}
    assert asked["__probe__"].type == DecisionCapability.BOOLEAN_GATE


def test_conformance_parameter_stays_exactly_one_transport() -> None:
    assert list(REGISTRATIONS) == [DecisionTransport.SYSTEMONE]


def test_resolution_unassigned_slot_is_off(db_session: Session) -> None:
    decision_provider(db_session, with_key=False)

    resolution = resolve_decision(DecisionCapability.TOOL_DISPATCH, db_session)

    assert resolution.kind == "off"


def test_resolution_needs_key_then_fallback_chain(db_session: Session) -> None:
    _keyless, keyless_model = decision_provider(
        db_session, with_key=False, external_id="jev-no-key"
    )
    _keyed, keyed_model = decision_provider(db_session, with_key=True, external_id="jev-keyed")
    row = db_session.get(DefaultTaskAssignment, "decision:tool-dispatch")
    assert row is not None
    row.model_id = keyless_model.id
    row.fallback_model_id = keyed_model.id
    db_session.flush()

    resolution = resolve_decision(DecisionCapability.TOOL_DISPATCH, db_session)

    assert isinstance(resolution, SystemOneResolution)
    assert resolution.model.external_id == "jev-keyed"

    slot_row = db_session.get(DefaultTaskAssignment, "decision:tool-dispatch")
    assert slot_row is not None
    slot_row.fallback_model_id = None
    db_session.flush()
    db_session.delete(db_session.get(AiModel, keyed_model.id))
    db_session.flush()
    clear_decision_resolution_cache()

    fallback_gone = resolve_decision(DecisionCapability.TOOL_DISPATCH, db_session)
    assert isinstance(fallback_gone, UnavailableResolution)
    assert fallback_gone.code == "needs-key"


def test_resolution_rejects_non_decision_models_in_slots(db_session: Session) -> None:
    chat_provider = Provider(
        name="OpenAI",
        type="openai_compatible",
        base_url="https://api.openai.com/v1",
        keyring_ref="provider:1",
        enabled=True,
        status=None,
    )
    db_session.add(chat_provider)
    db_session.flush()
    chat_model = AiModel(
        provider_id=chat_provider.id,
        external_id="gpt-x",
        label="gpt-x",
        caps=["text"],
        enabled=True,
        missing=False,
    )
    db_session.add(chat_model)
    db_session.flush()
    assign_slot(db_session, "decision:tool-dispatch", chat_model.id)

    resolution = resolve_decision(DecisionCapability.TOOL_DISPATCH, db_session)

    assert isinstance(resolution, UnconfiguredResolution)
    assert "not a decision model" in resolution.reason


def test_resolution_d2b_transport_must_declare_capability(db_session: Session) -> None:
    _provider, model = decision_provider(db_session, external_id="partial-jev")
    model.decision_transport = "unknown-transport"
    db_session.flush()
    assign_slot(db_session, "decision:tool-dispatch", model.id)

    resolution = resolve_decision(DecisionCapability.TOOL_DISPATCH, db_session)

    assert isinstance(resolution, UnconfiguredResolution)
    assert "not a decision model" in resolution.reason


def test_resolution_open_args_is_never_assignable(db_session: Session) -> None:
    _provider, model = decision_provider(db_session)
    assign_slot(db_session, "decision:score", model.id)

    resolution = resolve_decision(DecisionCapability.OPEN_ARGS, db_session)

    assert resolution.kind == "off"


def test_resolution_caches_per_revision(db_session: Session) -> None:
    _provider, model = decision_provider(db_session)
    assign_slot(db_session, "decision:tool-dispatch", model.id)
    key_calls: list[int] = []

    def counting_key(provider: Provider) -> str:
        key_calls.append(provider.id)
        return "decision-key"

    deps = DecisionFunnelDeps(session=db_session, get_api_key=counting_key)
    first = resolve_decision(DecisionCapability.TOOL_DISPATCH, db_session, deps)
    second = resolve_decision(DecisionCapability.TOOL_DISPATCH, db_session, deps)
    assert first is second
    assert len(key_calls) == 1

    assign_slot(db_session, "decision:tool-dispatch", None)
    third = resolve_decision(DecisionCapability.TOOL_DISPATCH, db_session, deps)
    assert third.kind == "off"
    assert len(key_calls) == 1


def test_probe_ok_reports_latency_and_resolved_model() -> None:
    client = FakeSystemOneClient(
        TypeSafeResult(
            model="jev-1.13",
            answers={
                "__probe__": DecisionAnswer(
                    type=DecisionCapabilityVocab.BOOLEAN_GATE, noul=0.99
                )
            },
        )
    )
    result = probe_decision_provider(
        DecisionProbeInput(
            provider=probe_provider_row(), model=probe_model_row(), api_key="k", client=client
        )
    )
    assert result.ok is True
    assert result.resolved_model == "jev-1.13"
    assert result.latency_ms >= 0


def test_probe_failure_carries_status_and_kind() -> None:
    client = FakeSystemOneClient(
        TypeSafeError(SystemOneErrorKind.AUTH, "bad key", 401)
    )
    result = probe_decision_provider(
        DecisionProbeInput(
            provider=probe_provider_row(), model=probe_model_row(), api_key="k", client=client
        )
    )
    assert result.ok is False
    assert result.status == 401
    assert result.kind == "auth"
    assert result.resolved_model is None


def test_probe_invalid_base_url_fails_fast() -> None:
    provider = probe_provider_row()
    provider.base_url = "not-a-url"
    result = probe_decision_provider(
        DecisionProbeInput(
            provider=provider,
            model=probe_model_row(),
            api_key="k",
            client=FakeSystemOneClient(None),
        )
    )
    assert result.ok is False
    assert "base URL" in (result.error or "")
