from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ...core import secrets
from ...core.vocab import Capability, DecisionCapability, DecisionTransport
from ...domain.models import AiModel, DefaultTaskAssignment, Provider
from .systemone.client import SystemOneClient, resolve_systemone_base_url
from .systemone.engine import SystemOneDecisionEngine, SystemOneEngineParams
from .systemone.probe import DecisionProbeInput, DecisionProbeResult, probe_decision_provider
from .types import (
    DECISION_SLOTS,
    SYSTEMONE_DECISION_CAPS,
    DecisionEngine,
    decision_slot,
)


@dataclass
class DecisionEngineDeps:
    session: Session
    get_api_key: Callable[[Provider], str | None] | None = None
    config_revision: Callable[[Session], str] | None = None
    observe_resolved_model: Callable[[str, str], None] | None = None
    client: SystemOneClient | None = None
    transport: object | None = None

    def api_key_of(self, provider: Provider) -> str | None:
        if self.get_api_key is not None:
            return self.get_api_key(provider)
        return secrets.get_secret(provider.keyring_ref)


@dataclass(frozen=True)
class OffResolution:
    kind = "off"


@dataclass(frozen=True)
class UnconfiguredResolution:
    kind = "unconfigured"
    reason: str


@dataclass(frozen=True)
class UnavailableResolution:
    kind = "unavailable"
    reason: str
    code: str | None = None
    provider_id: int | None = None


@dataclass(frozen=True)
class SystemOneResolution:
    kind = "systemone"
    provider: Provider
    model: AiModel
    api_key: str
    base_url: str


DecisionResolution = (
    OffResolution | UnconfiguredResolution | UnavailableResolution | SystemOneResolution
)


@dataclass(frozen=True)
class AuditMeta:
    provider_id: int | None
    model: str


@dataclass(frozen=True)
class DecisionTransportRegistration:
    transport: DecisionTransport
    capabilities: frozenset[DecisionCapability]
    display_name: str
    resolve_candidate: Callable[[Provider, AiModel, DecisionEngineDeps], DecisionResolution]
    create: Callable[[DecisionResolution, DecisionEngineDeps], DecisionEngine]
    audit: Callable[[DecisionResolution], AuditMeta | None]
    probe: Callable[[DecisionProbeInput], DecisionProbeResult]


def _resolve_systemone_candidate(
    provider: Provider, model: AiModel, deps: DecisionEngineDeps
) -> DecisionResolution:
    base_url = resolve_systemone_base_url(provider, model)
    if base_url is None:
        return UnavailableResolution(reason="The provider base URL is missing or invalid.")
    api_key = deps.api_key_of(provider)
    if not api_key:
        return UnavailableResolution(
            reason="No API key is set for the decision provider.",
            code="needs-key",
            provider_id=provider.id,
        )
    return SystemOneResolution(provider=provider, model=model, api_key=api_key, base_url=base_url)


def _create_systemone(resolution: DecisionResolution, deps: DecisionEngineDeps) -> DecisionEngine:
    if not isinstance(resolution, SystemOneResolution):
        raise ValueError("systemone registration received a non-systemone resolution")
    return SystemOneDecisionEngine(
        SystemOneEngineParams(
            api_key=resolution.api_key,
            base_url=resolution.base_url,
            model=resolution.model.external_id,
            client=deps.client,
            transport=deps.transport,
        )
    )


def _audit_systemone(resolution: DecisionResolution) -> AuditMeta | None:
    if not isinstance(resolution, SystemOneResolution):
        return None
    return AuditMeta(provider_id=resolution.provider.id, model=resolution.model.external_id)


SYSTEMONE_REGISTRATION = DecisionTransportRegistration(
    transport=DecisionTransport.SYSTEMONE,
    capabilities=frozenset(SYSTEMONE_DECISION_CAPS),
    display_name="TypeSafe System One",
    resolve_candidate=_resolve_systemone_candidate,
    create=_create_systemone,
    audit=_audit_systemone,
    probe=probe_decision_provider,
)

REGISTRATIONS: dict[DecisionTransport, DecisionTransportRegistration] = {
    DecisionTransport.SYSTEMONE: SYSTEMONE_REGISTRATION,
}


def get_decision_transport_registration(
    transport: DecisionTransport,
) -> DecisionTransportRegistration:
    return REGISTRATIONS[transport]


def decision_transport_capabilities(
    transport: DecisionTransport,
) -> frozenset[DecisionCapability]:
    return REGISTRATIONS[transport].capabilities


def decision_transport_display_name(transport: DecisionTransport) -> str:
    return REGISTRATIONS[transport].display_name


def decision_transport_of(provider: Provider, model: AiModel) -> DecisionTransport | None:
    if model.decision_transport:
        try:
            return DecisionTransport(model.decision_transport)
        except ValueError:
            return None
    if provider.type == "decision":
        return DecisionTransport.SYSTEMONE
    return None


def _assigned_candidates(
    session: Session, capability: DecisionCapability
) -> list[dict[str, object]]:
    row = session.get(DefaultTaskAssignment, decision_slot(capability))
    if row is None:
        return []
    candidates: list[dict[str, object]] = []
    for field_name in ("model_id", "fallback_model_id"):
        model_id = getattr(row, field_name)
        if isinstance(model_id, int):
            candidates.append({"model_id": model_id, "field": field_name})
    return candidates


def default_config_revision(session: Session) -> str:
    parts: list[str] = []
    for slot in DECISION_SLOTS:
        row = session.get(DefaultTaskAssignment, slot)
        if row is None:
            parts.append(f"{slot}:-")
            continue
        entries = []
        for model_id in (row.model_id, row.fallback_model_id):
            if model_id is None:
                entries.append("none")
                continue
            model = session.get(AiModel, model_id)
            if model is None:
                entries.append("dead")
                continue
            provider = session.get(Provider, model.provider_id)
            entries.append(
                ":".join(
                    str(value)
                    for value in (
                        model.id,
                        int(model.enabled),
                        model.decision_transport or "-",
                        provider.enabled if provider is not None else "-",
                    )
                )
            )
        parts.append(f"{slot}={','.join(entries)}")
    return ";".join(parts)


_RESOLUTION_CACHE: dict[str, tuple[str, DecisionResolution]] = {}


def clear_decision_resolution_cache() -> None:
    _RESOLUTION_CACHE.clear()


def _compute_resolution(
    capability: DecisionCapability, session: Session, deps: DecisionEngineDeps
) -> DecisionResolution:
    candidates = _assigned_candidates(session, capability)
    if not candidates:
        return OffResolution()
    rejections: list[str] = []
    last_index = len(candidates) - 1
    for index, candidate in enumerate(candidates):
        model_id = candidate["model_id"]
        assert isinstance(model_id, int)
        model = session.get(AiModel, model_id)
        if model is None:
            rejections.append(f"Model '{model_id}' is not registered.")
            continue
        provider = session.get(Provider, model.provider_id)
        if provider is None:
            rejections.append(f"Model '{model.external_id}' has no provider.")
            continue
        transport = decision_transport_of(provider, model)
        is_decision_model = Capability.DECISION.value in (model.caps or [])
        if transport is None or not is_decision_model:
            rejections.append(f"Model '{model.external_id}' is not a decision model.")
            continue
        registration = REGISTRATIONS[transport]
        if capability not in registration.capabilities:
            rejections.append(
                f"The transport of '{model.external_id}' does not serve "
                f"{decision_slot(capability)}."
            )
            continue
        resolution = registration.resolve_candidate(provider, model, deps)
        if isinstance(resolution, UnavailableResolution) and index != last_index:
            rejections.append(resolution.reason)
            continue
        return resolution
    return UnconfiguredResolution(
        reason=rejections[0] if rejections else "No decision model is assigned."
    )


def resolve_decision(
    capability: DecisionCapability,
    session: Session,
    deps: DecisionEngineDeps | None = None,
) -> DecisionResolution:
    deps = deps or DecisionEngineDeps(session=session)
    revision_source = deps.config_revision or default_config_revision
    revision = revision_source(session)
    cached = _RESOLUTION_CACHE.get(capability.value)
    if cached is not None and cached[0] == revision:
        return cached[1]
    resolution = _compute_resolution(capability, session, deps)
    _RESOLUTION_CACHE[capability.value] = (revision, resolution)
    return resolution


def engine_readiness(resolution: DecisionResolution) -> dict[str, str | None]:
    if isinstance(resolution, (SystemOneResolution,)):
        return {"state": "ready", "reason": None}
    if isinstance(resolution, OffResolution):
        return {"state": "unavailable", "reason": "No decision model is assigned."}
    if isinstance(resolution, UnavailableResolution) and resolution.code == "needs-key":
        return {
            "state": "needs-key",
            "reason": f"provider:{resolution.provider_id or ''}",
        }
    if isinstance(resolution, UnavailableResolution):
        return {"state": "unavailable", "reason": resolution.reason}
    assert isinstance(resolution, UnconfiguredResolution)
    return {"state": "unavailable", "reason": resolution.reason}
