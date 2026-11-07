from dataclasses import dataclass

from ...core.vocab import ExerciseKind


class ExerciseKindError(ValueError):
    pass


ENGINE_CHAIN = "chain"
ENGINE_EXACT = "exact"
ENGINE_STRUCT = "struct"
ENGINE_FSRS = "fsrs"
ENGINE_RUBRIC = "rubric"


@dataclass(frozen=True)
class ExerciseKindDef:
    kind: ExerciseKind
    engine: str
    widget: str
    card: bool = False


KINDS: dict[ExerciseKind, ExerciseKindDef] = {
    ExerciseKind.MULTI_STEP: ExerciseKindDef(ExerciseKind.MULTI_STEP, ENGINE_CHAIN, "math"),
    ExerciseKind.CARD_BASIC: ExerciseKindDef(
        ExerciseKind.CARD_BASIC, ENGINE_FSRS, "reveal", card=True
    ),
    ExerciseKind.CARD_REVERSE: ExerciseKindDef(
        ExerciseKind.CARD_REVERSE, ENGINE_FSRS, "reveal", card=True
    ),
    ExerciseKind.CARD_CLOZE: ExerciseKindDef(
        ExerciseKind.CARD_CLOZE, ENGINE_FSRS, "reveal", card=True
    ),
    ExerciseKind.MATCHING: ExerciseKindDef(ExerciseKind.MATCHING, ENGINE_STRUCT, "matching"),
    ExerciseKind.ORDERING: ExerciseKindDef(ExerciseKind.ORDERING, ENGINE_STRUCT, "ordering"),
    ExerciseKind.CATEGORIZE: ExerciseKindDef(ExerciseKind.CATEGORIZE, ENGINE_STRUCT, "categorize"),
    ExerciseKind.FILL_BLANK: ExerciseKindDef(ExerciseKind.FILL_BLANK, ENGINE_EXACT, "fill_blank"),
    ExerciseKind.EXPLAIN: ExerciseKindDef(ExerciseKind.EXPLAIN, ENGINE_RUBRIC, "essay"),
    ExerciseKind.ERROR_SPOT: ExerciseKindDef(ExerciseKind.ERROR_SPOT, ENGINE_RUBRIC, "lines"),
    ExerciseKind.CORRECT_SOLUTION: ExerciseKindDef(
        ExerciseKind.CORRECT_SOLUTION, ENGINE_RUBRIC, "math"
    ),
}

STRUCTURAL_KINDS: tuple[ExerciseKind, ...] = (
    ExerciseKind.MATCHING,
    ExerciseKind.ORDERING,
    ExerciseKind.CATEGORIZE,
    ExerciseKind.FILL_BLANK,
)
RUBRIC_KINDS: tuple[ExerciseKind, ...] = (
    ExerciseKind.EXPLAIN,
    ExerciseKind.ERROR_SPOT,
    ExerciseKind.CORRECT_SOLUTION,
)
GENERATABLE_KINDS: tuple[ExerciseKind, ...] = (
    ExerciseKind.MULTI_STEP,
    *STRUCTURAL_KINDS,
    *RUBRIC_KINDS,
)

CARD_KINDS: tuple[ExerciseKind, ...] = tuple(
    kind for kind, definition in KINDS.items() if definition.card
)
DEFAULT_KIND = ExerciseKind.MULTI_STEP


def is_card_kind(kind: str) -> bool:
    try:
        parsed = ExerciseKind(kind)
    except ValueError:
        return False
    return KINDS[parsed].card
