import contextlib
import time
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ...core.vocab import DecisionTransport
from ...domain.models import AiInteraction
from .registry import (
    REGISTRATIONS,
    AuditMeta,
    DecisionEngineDeps,
    OffResolution,
    SystemOneResolution,
    UnavailableResolution,
    UnconfiguredResolution,
    resolve_decision,
)
from .types import (
    DECISION_ACT_THRESHOLD_DEFAULT,
    DECISION_AUDIT_TASK,
    DECISION_CONFIRM_THRESHOLD_DEFAULT,
    DecisionCapability,
    DecisionOutcome,
    DecisionQuestion,
    DecisionRequest,
    DecisionToolSchema,
    capability_for_questions,
    decision_band,
)


@dataclass(frozen=True)
class DecisionOffStatus:
    status = "off"


@dataclass(frozen=True)
class DecisionUnconfiguredStatus:
    status = "unconfigured"
    reason: str


@dataclass(frozen=True)
class DecisionUnavailableStatus:
    status = "unavailable"
    reason: str
    code: str | None = None
    provider_id: int | None = None


@dataclass(frozen=True)
class DecisionErrorStatus:
    status = "error"
    reason: str
    transport: str | None = None


@dataclass(frozen=True)
class DecisionDecidedStatus:
    status = "decided"
    band: str
    outcome: DecisionOutcome


DecisionStatus = (
    DecisionOffStatus
    | DecisionUnconfiguredStatus
    | DecisionUnavailableStatus
    | DecisionErrorStatus
    | DecisionDecidedStatus
)


@dataclass(frozen=True)
class RunDecisionParams:
    input: str
    tools: tuple[DecisionToolSchema, ...] = ()
    questions: tuple[DecisionQuestion, ...] = ()
    system_prompt: str | None = None
    catalog_entities: dict[str, tuple[str, ...]] | None = None
    capability: DecisionCapability | None = None
    act_threshold: float = DECISION_ACT_THRESHOLD_DEFAULT
    confirm_threshold: float = DECISION_CONFIRM_THRESHOLD_DEFAULT


@dataclass
class DecisionFunnelDeps(DecisionEngineDeps):
    session_factory: Callable[[], Session] | None = None


def resolution_transport(resolution: object) -> DecisionTransport | None:
    if isinstance(resolution, SystemOneResolution):
        return DecisionTransport.SYSTEMONE
    return None


def _record_interaction(
    deps: DecisionFunnelDeps,
    meta: AuditMeta,
    outcome: DecisionOutcome | None,
    latency_ms: int,
) -> None:
    row = AiInteraction(
        context_type="decision",
        context_id=meta.provider_id,
        task=DECISION_AUDIT_TASK,
        model=meta.model,
        input_tokens=outcome.usage.input_tokens if outcome is not None and outcome.usage else None,
        output_tokens=(
            outcome.usage.output_tokens if outcome is not None and outcome.usage else None
        ),
        latency_ms=latency_ms,
    )
    if deps.session_factory is not None:
        with deps.session_factory() as session:
            session.add(row)
            session.commit()
    else:
        deps.session.add(row)


def run_decision(deps: DecisionFunnelDeps, params: RunDecisionParams) -> DecisionStatus:
    capability = params.capability
    if capability is None:
        if params.questions:
            capability = capability_for_questions(list(params.questions))
        else:
            capability = DecisionCapability.TOOL_DISPATCH
    resolution = resolve_decision(capability, deps.session, deps)
    if isinstance(resolution, OffResolution):
        return DecisionOffStatus()
    if isinstance(resolution, UnconfiguredResolution):
        return DecisionUnconfiguredStatus(reason=resolution.reason)
    if isinstance(resolution, UnavailableResolution):
        return DecisionUnavailableStatus(
            reason=resolution.reason, code=resolution.code, provider_id=resolution.provider_id
        )
    transport = resolution_transport(resolution)
    if transport is None:
        return DecisionErrorStatus(reason="unresolvable decision model")
    registration = REGISTRATIONS[transport]
    meta = registration.audit(resolution)
    if meta is None:
        return DecisionErrorStatus(reason="no audit meta for decision resolution")
    request = DecisionRequest(
        input=params.input,
        tools=params.tools,
        questions=params.questions,
        system_prompt=params.system_prompt,
        catalog_entities=params.catalog_entities,
    )
    started_at = time.monotonic()
    try:
        engine = registration.create(resolution, deps)
        outcome = engine.decide(request)
    except Exception as error:
        latency_ms = int((time.monotonic() - started_at) * 1000)
        _record_interaction(deps, meta, None, latency_ms)
        return DecisionErrorStatus(reason=str(error)[:500], transport=transport.value)
    latency_ms = int((time.monotonic() - started_at) * 1000)
    _record_interaction(deps, meta, outcome, latency_ms)
    if (
        outcome.resolved_model
        and outcome.resolved_model != resolution.model.external_id
        and deps.observe_resolved_model is not None
    ):
        with contextlib.suppress(Exception):
            deps.observe_resolved_model(
                resolution.model.external_id, outcome.resolved_model
            )
    return DecisionDecidedStatus(
        band=decision_band(outcome.confidence, params.act_threshold, params.confirm_threshold),
        outcome=outcome,
    )
