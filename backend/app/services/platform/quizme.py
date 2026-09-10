import json
import re
from typing import Any

from ...math.equivalence import equivalent

MAX_CHOICES = 6
QUIZME_KEYRING = "quizme"

QUIZME_SYSTEM = (
    "QUIZ-ME MODE: You are assessing the student, not answering for them.\n"
    "- Ask EXACTLY ONE question per turn, using the QUIZ tool.\n"
    "- Start from the material in scope and escalate difficulty as they succeed.\n"
    "- After a graded result, give a one-to-two sentence explanation of the "
    "mistake or a short confirmation, then ask the next question.\n"
    "- NEVER reveal, restate, hint at, or write out the expected answer — the "
    "server grades deterministically and keeps it from you on purpose.\n"
    "- No multi-question dumps; no yes/no questions."
)

_QUIZ_PENDING_VALIDATE_ERROR = "invalid QUIZ arguments"


def validate_quiz_args(args: dict[str, Any]) -> dict[str, Any]:
    question = str(args.get("question", "")).strip()
    if not question:
        raise ValueError("QUIZ requires a question")
    pending: dict[str, Any] = {"question": question[:2000]}
    choices = args.get("choices")
    expected_index = args.get("expected_index")
    expected_latex = str(args.get("expected_latex", "") or "").strip()
    expected_text = str(args.get("expected_text", "") or "").strip()
    accept = [
        str(variant).strip()
        for variant in (args.get("accept") or [])[:10]
        if str(variant).strip()
    ]
    if choices is not None:
        if not isinstance(choices, list) or not (2 <= len(choices) <= MAX_CHOICES):
            raise ValueError(_QUIZ_PENDING_VALIDATE_ERROR + ": choices must be 2-6 options")
        if expected_index is None:
            raise ValueError(
                _QUIZ_PENDING_VALIDATE_ERROR + ": expected_index required with choices"
            )
        try:
            index = int(expected_index)
        except (TypeError, ValueError) as error:
            raise ValueError(
                _QUIZ_PENDING_VALIDATE_ERROR + ": expected_index must be an integer"
            ) from error
        if not (0 <= index < len(choices)):
            raise ValueError(
                _QUIZ_PENDING_VALIDATE_ERROR + ": expected_index out of range"
            )
        pending["choices"] = [str(choice)[:300] for choice in choices]
        pending["expected_index"] = index
        return pending
    if expected_latex:
        pending["expected_latex"] = expected_latex[:500]
        pending["accept"] = accept
        return pending
    if expected_text:
        pending["expected_text"] = expected_text[:500]
        pending["accept"] = accept
        return pending
    raise ValueError(
        _QUIZ_PENDING_VALIDATE_ERROR
        + ": provide choices+expected_index, expected_latex, or expected_text"
    )


def normalize_text(value: str) -> str:
    lowered = value.strip().casefold()
    return re.sub(r"[\s\W_]+", "", lowered, flags=re.UNICODE)


def grade_answer(pending: dict[str, Any], answer: Any) -> tuple[bool, str]:
    """Deterministic grading (ADR-121): choices → exact index; math → the
    equivalence chain; text → normalized match against the expected text or
    the pre-authorized accept variants. Returns (correct, detail)."""
    if "expected_index" in pending:
        try:
            chosen = int(answer)
        except (TypeError, ValueError):
            return False, "choose one of the options"
        correct = chosen == int(pending["expected_index"])
        return correct, "exact choice match"
    answer_text = str(answer or "").strip()
    if not answer_text:
        return False, "empty answer"
    expected_latex = pending.get("expected_latex")
    if expected_latex:
        chain = equivalent(answer_text, str(expected_latex))
        if chain.equivalent:
            return True, f"equivalence chain ({chain.stage})"
        accepted = next(
            (
                variant
                for variant in pending.get("accept", [])
                if normalize_text(variant) == normalize_text(answer_text)
            ),
            None,
        )
        if accepted is not None:
            return True, "accepted variant"
        return False, "equivalence chain did not match"
    expected_text = str(pending.get("expected_text", ""))
    normalized = normalize_text(answer_text)
    if normalize_text(expected_text) == normalized:
        return True, "normalized text match"
    for variant in pending.get("accept", []):
        if normalize_text(variant) == normalized:
            return True, "accepted variant"
    return False, "text answer did not match"


def quiz_public_state(pending: dict[str, Any] | None) -> dict[str, Any] | None:
    """The student-visible card payload — never contains expected answers."""
    if not isinstance(pending, dict) or not pending.get("question"):
        return None
    public: dict[str, Any] = {
        "question": pending.get("question"),
        "choices": pending.get("choices"),
    }
    if pending.get("verdict") is not None:
        public["answered"] = True
        public["verdict"] = pending["verdict"]
        public["verdict_detail"] = pending.get("verdict_detail")
        public["student_answer"] = pending.get("student_answer")
        expected_display = pending.get("expected_latex") or pending.get(
            "expected_text"
        )
        if pending.get("choices") is not None:
            idx = pending.get("expected_index")
            expected_display = (
                pending["choices"][idx] if isinstance(idx, int) and pending.get("choices") else None
            )
        public["expected_display"] = expected_display
    else:
        public["answered"] = False
    return public


def pending_tool_payload(pending: dict[str, Any]) -> dict[str, Any]:
    """Model-facing tool result — carries NO expected-answer material."""
    return {
        "question": pending.get("question"),
        "choices": pending.get("choices"),
        "awaiting": "the student's graded answer arrives with their next message",
    }


def dumps_pending(pending: dict[str, Any]) -> str:
    return json.dumps(pending, ensure_ascii=False)
