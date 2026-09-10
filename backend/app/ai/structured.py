from typing import Any

from pydantic import BaseModel, ConfigDict


class LooseObject(BaseModel):
    model_config = ConfigDict(extra="allow")


class QuizQuestion(LooseObject):
    type: str | None = None
    stem_md: str | None = None
    options_md: list[str] | None = None
    answer: Any | None = None
    explanation_md: str | None = None
    concepts: list[str] | None = None
    skill: str | None = None


class QuizgenOut(LooseObject):
    questions: list[QuizQuestion] | None = None


class Flashcard(LooseObject):
    front: str | None = None
    back: str | None = None


class FlashcardsOut(LooseObject):
    cards: list[Flashcard] | None = None


class ExerciseStep(LooseObject):
    kind: str | None = None
    prompt_md: str | None = None
    payload: Any | None = None
    hint: str | None = None
    expected_answer: Any | None = None
    difficulty: float | None = None


class ExerciseOut(LooseObject):
    title: str | None = None
    kind: str | None = None
    difficulty: float | None = None
    prompt_md: str | None = None
    steps: list[ExerciseStep] | None = None


class RubricOut(LooseObject):
    verdict: str | None = None
    score: float | None = None
    rationale: Any | None = None


class DiscoveredItem(LooseObject):
    key: str | None = None
    name: str | None = None
    description: str | None = None


class ItemsOut(LooseObject):
    items: list[DiscoveredItem] | None = None


def dump_structured(result: Any) -> dict[str, Any]:
    if hasattr(result, "model_dump"):
        return dict(result.model_dump())
    if isinstance(result, dict):
        return dict(result)
    return dict(result)
