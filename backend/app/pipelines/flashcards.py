import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.gateway import LLMGateway
from ..ai.parsing import blocks_to_md
from ..ai.runner import AuditRef, TaskRunner
from ..ai.skills import FLASHCARDS_SYSTEM
from ..ai.structured import FlashcardsOut
from ..domain.models import Exercise, ExerciseStep
from ..services.cards import create_card_exercise
from ..services.context import ContextBundle

FLASHCARDS_TASK = "flashcards"
FLASHCARDS_SKILL = "flashcards.generate"
MAX_REPAIR_ROUNDS = 2
MAX_CARDS = 30

KINDS = ("basic", "cloze", "reverse")
CLOZE_RE = re.compile(r"\{\{c?\d*::?[^}]*\}\}|\{\{[^}]*\}\}")


class FlashcardsError(ValueError):
    pass


def validate_card(draft: dict[str, Any], index: int) -> list[str]:
    problems: list[str] = []
    label = f"card {index}"
    if draft.get("kind") not in KINDS:
        problems.append(f"{label}: kind must be one of {KINDS}")
        return problems
    front = str(draft.get("front_md", "")).strip()
    back = str(draft.get("back_md", "")).strip()
    if not front:
        problems.append(f"{label}: empty front")
    if not back:
        problems.append(f"{label}: empty back")
    if draft.get("kind") == "cloze" and front and not CLOZE_RE.search(front):
        problems.append(f"{label}: cloze front needs a {{{{...}}}} deletion")
    return problems


class FlashcardsService:
    def __init__(self, session: Session, gateway: LLMGateway) -> None:
        self._session = session
        self._gateway = gateway

    def generate(
        self,
        profile_id: int,
        *,
        course_id: int,
        node_id: int | None = None,
        count: int = 8,
        source: str = "note",
        source_ref: str | None = None,
        content: str,
        context: ContextBundle | None = None,
    ) -> tuple[list[Exercise], list[str]]:
        count = max(1, min(count, MAX_CARDS))
        prompt = (
            f"Write exactly {count} flashcards from the following source. Mix kinds "
            "(mostly basic, some cloze, a reverse or two).\n\nSource:\n"
            + content[:6000]
        )
        if context is not None:
            extras = context.render_extras()
            if extras:
                prompt = f"{prompt}\n\n{extras}"

        def validate(draft: dict[str, Any]) -> list[str]:
            drafts = draft.get("cards")
            if not isinstance(drafts, list):
                return ["response missing cards list"]
            problems: list[str] = []
            for index, entry in enumerate(drafts[:count]):
                problems.extend(validate_card(entry, index))
            existing = self._existing_fronts(profile_id)
            seen: set[str] = set()
            for index, entry in enumerate(drafts[:count]):
                front = str(entry.get("front_md", "")).strip()
                if front in existing or front in seen:
                    problems.append(f"card {index}: duplicate of an existing card")
                seen.add(front)
            if len(drafts) < count:
                problems.append(f"only {len(drafts)}/{count} cards returned")
            return problems

        runner = TaskRunner(self._session, self._gateway)
        result = runner.run_json(
            task=FLASHCARDS_TASK,
            prompt=prompt,
            validate=validate,
            fallback_system=FLASHCARDS_SYSTEM,
            skill_key=FLASHCARDS_SKILL,
            course_id=course_id,
            render_vars={"count": str(count)},
            max_rounds=MAX_REPAIR_ROUNDS,
            error_type=FlashcardsError,
            audit=AuditRef(
                "flashcards", None, f"generate {count} cards from {source}"
            ),
            schema=FlashcardsOut,
        )
        problems = result.problems
        if problems:
            raise FlashcardsError(
                "cards did not pass validation: " + "; ".join(problems[:10])
            )
        drafts = result.draft.get("cards", [])[:count]

        cards: list[Exercise] = []
        for draft in drafts:
            cards.append(
                create_card_exercise(
                    self._session,
                    profile_id=profile_id,
                    course_id=course_id,
                    node_id=node_id,
                    kind=draft["kind"],
                    front=[{"type": "text", "md": draft["front_md"]}],
                    back=[{"type": "text", "md": draft["back_md"]}],
                    source=source,
                    source_ref=source_ref,
                )
            )
        return cards, []

    def _existing_fronts(self, profile_id: int) -> set[str]:
        rows = self._session.execute(
            select(ExerciseStep.prompt)
            .join(Exercise, Exercise.id == ExerciseStep.exercise_id)
            .where(
                Exercise.profile_id == profile_id, Exercise.kind.like("card_%")
            )
        )
        fronts: set[str] = set()
        for (front,) in rows:
            fronts.add(blocks_to_md(front).strip())
        return fronts
