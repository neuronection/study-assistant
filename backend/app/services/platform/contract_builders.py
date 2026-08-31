from typing import Any

from ...ai.contracts.contracts import Constraint
from ...domain.models import SkillVersion

LADDER_WORDS = {1: 50, 2: 70, 3: 100, 4: 140, 5: 400}


def _hint_constraints(
    contract: dict[str, Any], runtime: dict[str, Any]
) -> list[Constraint]:
    level = int(runtime.get("hint_level", 3))
    result: list[Constraint] = []
    if contract.get("no_answer_reveal", True):
        result.append(Constraint("no_answer_reveal"))
    words = contract.get("max_words")
    if words is None:
        words = LADDER_WORDS.get(level, 100)
    result.append(Constraint("max_words", {"n": int(words)}))
    return result


def _chat_constraints(
    contract: dict[str, Any], runtime: dict[str, Any]
) -> list[Constraint]:
    result: list[Constraint] = []
    if contract.get("citation_if_context", True):
        result.append(Constraint("citation_if_context"))
        result.append(Constraint("citations_in_range"))
    if contract.get("no_answer_reveal", False):
        result.append(Constraint("no_answer_reveal"))
    words = contract.get("max_words")
    if words:
        result.append(Constraint("max_words", {"n": int(words)}))
    result.append(Constraint("mentions_in_range", advisory=True))
    result.append(Constraint("proposal_valid"))
    return result


def _plain_constraints(
    contract: dict[str, Any], runtime: dict[str, Any]
) -> list[Constraint]:
    result: list[Constraint] = []
    words = contract.get("max_words")
    if words:
        result.append(Constraint("max_words", {"n": int(words)}))
    return result


def build_constraints(
    version: SkillVersion, runtime: dict[str, Any]
) -> list[Constraint]:
    skill_key = version.skill.key if version.skill else ""
    contract = version.contract or {}
    if skill_key in ("tutor.hint", "quiz.help_hint"):
        return _hint_constraints(contract, runtime)
    if skill_key == "chat.answer":
        return _chat_constraints(contract, runtime)
    return _plain_constraints(contract, runtime)
