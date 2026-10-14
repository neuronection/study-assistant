from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from ...core.vocab import DecisionCapability as DecisionCapability
from ...core.vocab import DecisionTransport as DecisionTransport

DECISION_SLOT_PREFIX = "decision:"

# ADR-0036 §1: the `decision` default slot joins the vocabulary beside the
# kind overrides — study stores it as a DefaultTaskAssignment on
# requires='decision' (the family's `default:decision` row).
DECISION_DEFAULT_SLOT = "decision"

SYSTEMONE_DECISION_CAPS: tuple[DecisionCapability, ...] = (
    DecisionCapability.TOOL_DISPATCH,
    DecisionCapability.BOOLEAN_GATE,
    DecisionCapability.CHOICE,
    DecisionCapability.SCORE,
)

DECISION_TRANSPORTS: tuple[DecisionTransport, ...] = (DecisionTransport.SYSTEMONE,)

DECISION_SLOTS: tuple[str, ...] = tuple(
    f"{DECISION_SLOT_PREFIX}{capability.value}" for capability in SYSTEMONE_DECISION_CAPS
)

DECISION_ACT_THRESHOLD_DEFAULT = 0.85
DECISION_CONFIRM_THRESHOLD_DEFAULT = 0.5

DECISION_PROBE_TIMEOUT_SECONDS = 10.0

DECISION_AUDIT_TASK = "decision"


def decision_slot(capability: DecisionCapability) -> str:
    return f"{DECISION_SLOT_PREFIX}{capability.value}"


def is_decision_slot(value: str) -> bool:
    return value in DECISION_SLOTS


def decision_slot_capability(slot: str) -> DecisionCapability | None:
    if not slot.startswith(DECISION_SLOT_PREFIX):
        return None
    capability = slot.removeprefix(DECISION_SLOT_PREFIX)
    if capability in {cap.value for cap in SYSTEMONE_DECISION_CAPS}:
        return DecisionCapability(capability)
    return None


def transport_decision_caps(transport: str | None) -> frozenset[DecisionCapability]:
    if transport == DecisionTransport.SYSTEMONE.value:
        return frozenset(SYSTEMONE_DECISION_CAPS)
    return frozenset()


def capability_for_questions(
    questions: "list[DecisionQuestion]",
) -> DecisionCapability:
    if any(question.type == DecisionCapability.CHOICE for question in questions):
        return DecisionCapability.CHOICE
    if any(question.type == DecisionCapability.SCORE for question in questions):
        return DecisionCapability.SCORE
    return DecisionCapability.BOOLEAN_GATE


def sanitize_confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number:
        return 0.0
    return min(1.0, max(0.0, number))


def decision_band(
    confidence: float,
    act_threshold: float = DECISION_ACT_THRESHOLD_DEFAULT,
    confirm_threshold: float = DECISION_CONFIRM_THRESHOLD_DEFAULT,
) -> str:
    if confidence >= act_threshold:
        return "act"
    if confidence >= confirm_threshold:
        return "confirm"
    return "refuse"


@dataclass(frozen=True)
class DecisionQuestion:
    id: str
    type: DecisionCapability
    instructions: str
    options: Mapping[str, str | None] | None = None
    levels: tuple[str, ...] | None = None
    criteria: tuple[str, str] | None = None


@dataclass(frozen=True)
class DecisionAnswer:
    type: DecisionCapability
    noul: float | None = None
    choice: str | None = None
    score: float | None = None
    legend: dict[str, str] | None = None
    probabilities: dict[str, float] | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class DecisionToolSchema:
    name: str
    description: str
    parameters: dict[str, Any] | None = None
    app_id: str | None = None


@dataclass(frozen=True)
class DecisionCall:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DecisionUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class DecisionOutcome:
    engine: str
    calls: tuple[DecisionCall, ...] = ()
    confidence: float = 0.0
    reasoning: str | None = None
    answers: dict[str, DecisionAnswer] | None = None
    usage: DecisionUsage | None = None
    resolved_model: str | None = None


@dataclass(frozen=True)
class DecisionRequest:
    input: str
    tools: tuple[DecisionToolSchema, ...] = ()
    questions: tuple[DecisionQuestion, ...] = ()
    system_prompt: str | None = None
    catalog_entities: Mapping[str, tuple[str, ...]] | None = None


class DecisionEngine(Protocol):
    transport: DecisionTransport

    def decide(self, request: DecisionRequest) -> DecisionOutcome: ...
