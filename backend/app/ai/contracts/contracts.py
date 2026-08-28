import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

CITATION_RE = re.compile(r"\[(\d+)\]")

_FENCED_BLOCK_RE = re.compile(r"```[^\n]*\n.*?```", re.DOTALL)


def _prose_words(output: str) -> int:
    return len(_FENCED_BLOCK_RE.sub(" ", output).split())


@dataclass(frozen=True)
class Constraint:
    kind: str
    params: dict[str, Any] = field(default_factory=dict)
    advisory: bool = False


@dataclass(frozen=True)
class Violation:
    constraint: str
    detail: str


@dataclass(frozen=True)
class ValidationResult:
    violations: list[Violation]
    advisories: list[Violation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def feedback(self) -> str:
        return "; ".join(f"{v.constraint}: {v.detail}" for v in self.violations)


Validator = Callable[[str, dict[str, Any], dict[str, Any]], list[Violation]]


def _require_citation_when_context(
    output: str, params: dict[str, Any], context: dict[str, Any]
) -> list[Violation]:
    chunks = context.get("chunks") or []
    if not chunks:
        return []
    if not CITATION_RE.search(output):
        return [
            Violation(
                "citation_if_context",
                "retrieved material is in context — support claims with [n] citations",
            )
        ]
    return []


def _citations_in_range(
    output: str, params: dict[str, Any], context: dict[str, Any]
) -> list[Violation]:
    chunks = context.get("chunks") or []
    if not chunks:
        return []
    limit = len(chunks)
    out_of_range = [
        int(match)
        for match in CITATION_RE.findall(output)
        if not 1 <= int(match) <= limit
    ]
    if out_of_range:
        return [
            Violation(
                "citations_in_range",
                f"citations {sorted(set(out_of_range))} exceed the provided sources "
                f"(1..{limit})",
            )
        ]
    return []


def _max_words(
    output: str, params: dict[str, Any], context: dict[str, Any]
) -> list[Violation]:
    limit = int(params.get("n", 400))
    words = _prose_words(output)
    if words > limit:
        return [Violation("max_words", f"{words} words exceeds limit {limit}")]
    return []


def _no_answer_reveal(
    output: str, params: dict[str, Any], context: dict[str, Any]
) -> list[Violation]:
    from ...math.leak_guard import check_leak

    candidates: list[str] = []
    if context.get("expected") is not None:
        candidates.append(str(context["expected"]))
    for extra in context.get("expected_candidates") or []:
        if extra:
            candidates.append(str(extra))
    for candidate in candidates:
        leak = check_leak(output, candidate)
        if leak.leaks:
            return [Violation("no_answer_reveal", leak.detail)]
    lowered = output.lower()
    for text in context.get("forbidden_texts") or []:
        stripped = str(text).strip()
        if len(stripped) >= 8 and stripped.lower() in lowered:
            return [
                Violation(
                    "no_answer_reveal",
                    f"output quotes the answer text verbatim ({stripped[:60]})",
                )
            ]
    return []


def _max_blocks(
    output: str, params: dict[str, Any], context: dict[str, Any]
) -> list[Violation]:
    limit = int(params.get("n", 3))
    blocks = context.get("blocks") or []
    if len(blocks) > limit:
        return [Violation("max_blocks", f"{len(blocks)} blocks exceeds limit {limit}")]
    return []


def _mentions_in_range(
    output: str, params: dict[str, Any], context: dict[str, Any]
) -> list[Violation]:
    allowed = {str(ref) for ref in context.get("mention_refs") or []}
    if not allowed:
        return []
    from ..mentions import MENTION_RE

    used = {f"{match.group(1)}{match.group(2)}" for match in MENTION_RE.finditer(output)}
    invalid = sorted(used - allowed)
    if invalid:
        return [
            Violation(
                "mentions_in_range",
                f"handles {invalid} were not offered in this conversation — "
                "reference only listed items",
            )
        ]
    return []


def _proposal_valid(
    output: str, params: dict[str, Any], context: dict[str, Any]
) -> list[Violation]:
    if not context.get("proposals_enabled"):
        return []
    from ..proposals import PROPOSAL_FENCE_RE, validate_proposal_text

    if not PROPOSAL_FENCE_RE.search(output):
        return []
    return [Violation("proposal_valid", problem) for problem in validate_proposal_text(output)]


VALIDATORS: dict[str, Validator] = {
    "citation_if_context": _require_citation_when_context,
    "citations_in_range": _citations_in_range,
    "max_words": _max_words,
    "no_answer_reveal": _no_answer_reveal,
    "max_blocks": _max_blocks,
    "mentions_in_range": _mentions_in_range,
    "proposal_valid": _proposal_valid,
}


def validate(
    output: str, constraints: list[Constraint], context: dict[str, Any]
) -> ValidationResult:
    violations: list[Violation] = []
    advisories: list[Violation] = []
    for constraint in constraints:
        validator = VALIDATORS.get(constraint.kind)
        if validator is None:
            continue
        found = validator(output, constraint.params, context)
        if constraint.advisory:
            advisories.extend(found)
        else:
            violations.extend(found)
    return ValidationResult(violations=violations, advisories=advisories)


CHAT_ANSWER_CONTRACT = [
    Constraint("citation_if_context"),
    Constraint("citations_in_range"),
    Constraint("max_words", {"n": 400}),
    Constraint("mentions_in_range", advisory=True),
    Constraint("proposal_valid"),
]

HINT_LEVEL_WORDS = {1: 50, 2: 70, 3: 100, 4: 140, 5: 400}


def hint_contract(level: int) -> list[Constraint]:
    return [
        Constraint("no_answer_reveal"),
        Constraint("max_words", {"n": HINT_LEVEL_WORDS.get(level, 100)}),
    ]
