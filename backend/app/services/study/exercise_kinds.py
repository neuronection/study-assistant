from dataclasses import dataclass


class ExerciseKindError(ValueError):
    pass


ENGINE_CHAIN = "chain"
ENGINE_EXACT = "exact"
ENGINE_STRUCT = "struct"
ENGINE_FSRS = "fsrs"
ENGINE_RUBRIC = "rubric"


@dataclass(frozen=True)
class ExerciseKindDef:
    kind: str
    engine: str
    widget: str
    card: bool = False


MULTI_STEP = "multi_step"
CARD_BASIC = "card_basic"
CARD_REVERSE = "card_reverse"
CARD_CLOZE = "card_cloze"
MATCHING = "matching"
ORDERING = "ordering"
CATEGORIZE = "categorize"
FILL_BLANK = "fill_blank"
EXPLAIN = "explain"
ERROR_SPOT = "error_spot"
CORRECT_SOLUTION = "correct_solution"

KINDS: dict[str, ExerciseKindDef] = {
    MULTI_STEP: ExerciseKindDef(MULTI_STEP, ENGINE_CHAIN, "math"),
    CARD_BASIC: ExerciseKindDef(CARD_BASIC, ENGINE_FSRS, "reveal", card=True),
    CARD_REVERSE: ExerciseKindDef(CARD_REVERSE, ENGINE_FSRS, "reveal", card=True),
    CARD_CLOZE: ExerciseKindDef(CARD_CLOZE, ENGINE_FSRS, "reveal", card=True),
    MATCHING: ExerciseKindDef(MATCHING, ENGINE_STRUCT, "matching"),
    ORDERING: ExerciseKindDef(ORDERING, ENGINE_STRUCT, "ordering"),
    CATEGORIZE: ExerciseKindDef(CATEGORIZE, ENGINE_STRUCT, "categorize"),
    FILL_BLANK: ExerciseKindDef(FILL_BLANK, ENGINE_EXACT, "fill_blank"),
    EXPLAIN: ExerciseKindDef(EXPLAIN, ENGINE_RUBRIC, "essay"),
    ERROR_SPOT: ExerciseKindDef(ERROR_SPOT, ENGINE_RUBRIC, "lines"),
    CORRECT_SOLUTION: ExerciseKindDef(CORRECT_SOLUTION, ENGINE_RUBRIC, "math"),
}

STRUCTURAL_KINDS = (MATCHING, ORDERING, CATEGORIZE, FILL_BLANK)
RUBRIC_KINDS = (EXPLAIN, ERROR_SPOT, CORRECT_SOLUTION)
GENERATABLE_KINDS = (MULTI_STEP, *STRUCTURAL_KINDS, *RUBRIC_KINDS)

CARD_KINDS = tuple(kind for kind, definition in KINDS.items() if definition.card)
LEGACY_CARD_KIND_MAP = {"basic": CARD_BASIC, "cloze": CARD_CLOZE, "reverse": CARD_REVERSE}
DEFAULT_KIND = MULTI_STEP


def is_card_kind(kind: str) -> bool:
    return KINDS.get(kind, ExerciseKindDef("", "", "", card=False)).card


def card_kind_from_legacy(kind: str) -> str:
    mapped = LEGACY_CARD_KIND_MAP.get(kind)
    if mapped is None:
        raise ExerciseKindError(f"unknown card kind: {kind}")
    return mapped


def legacy_kind_from_card(kind: str) -> str:
    if not is_card_kind(kind):
        raise ExerciseKindError(f"not a card kind: {kind}")
    return kind.removeprefix("card_")
