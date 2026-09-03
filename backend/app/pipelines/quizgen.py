import random
from typing import Any

from sqlalchemy.orm import Session

from ..ai.gateway import LLMGateway
from ..ai.runner import AuditRef, TaskRunner
from ..ai.skills import QUIZGEN_SYSTEM
from ..ai.structured import QuizgenOut
from ..domain.models import Activity, Question
from ..math.composite import validate_composite_answer
from ..math.equivalence import expressions_equivalent
from ..math.regions import validate_region_answer
from ..math.tables import validate_table_answer
from ..services.knowledge.context import ContextBundle

QUIZGEN_TASK = "quizgen"
QUIZGEN_SKILL = "quiz.generate"
MAX_REPAIR_ROUNDS = 2

QUESTION_TYPES = (
    "single",
    "multi",
    "truefalse",
    "text",
    "numeric",
    "equation",
    "numberline",
    "table_fill",
    "composite",
)
SKILLS = ("conceptual", "procedural", "applied", "notation")
BLOOMS = ("remember", "understand", "apply", "analyze", "evaluate", "create")


class QuizgenError(ValueError):
    pass


def _default_blueprint(count: int, question_types: list[str] | None = None) -> list[dict[str, Any]]:
    count = max(1, min(count, 30))
    if question_types:
        types = list(question_types)
        return [{"type": types[i % len(types)]} for i in range(count)]
    cycle = ["single", "single", "truefalse", "numeric", "multi", "text", "equation", "single"]
    return [{"type": cycle[i % len(cycle)]} for i in range(count)]


def validate_question(draft: dict[str, Any], index: int) -> list[str]:
    problems: list[str] = []
    qtype = draft.get("type")
    if qtype not in QUESTION_TYPES:
        problems.append(f"q{index}: unknown type '{qtype}'")
        return problems
    if not str(draft.get("stem_md", "")).strip():
        problems.append(f"q{index}: empty stem")
    answer = draft.get("answer")
    if not isinstance(answer, dict):
        problems.append(f"q{index}: missing answer object")
        answer = {}
    options = draft.get("options_md")
    if qtype in ("single", "multi"):
        if not isinstance(options, list) or len(options) < 2:
            problems.append(f"q{index}: needs at least 2 options")
        else:
            if qtype == "single":
                try:
                    choice = int(answer.get("index", -1))
                    if not 0 <= choice < len(options):
                        problems.append(f"q{index}: answer index out of range")
                except (TypeError, ValueError):
                    problems.append(f"q{index}: single answer needs integer index")
            else:
                indices = answer.get("indices")
                if not isinstance(indices, list) or not indices:
                    problems.append(f"q{index}: multi answer needs indices list")
                elif any(not 0 <= int(i) < len(options) for i in indices if str(i).isdigit()):
                    problems.append(f"q{index}: multi index out of range")
    elif qtype == "truefalse":
        if not isinstance(answer.get("value"), bool):
            problems.append(f"q{index}: truefalse answer must be true/false")
    elif qtype == "numeric":
        try:
            float(answer.get("value") or "not-a-number")
        except (TypeError, ValueError):
            problems.append(f"q{index}: numeric answer needs numeric value")
    elif qtype == "equation" and not str(answer.get("value", "")).strip():
        problems.append(f"q{index}: equation answer needs value")
    elif qtype == "numberline":
        problems.extend(
            f"q{index}: {problem}" for problem in validate_region_answer(answer)
        )
    elif qtype == "table_fill":
        problems.extend(
            f"q{index}: {problem}" for problem in validate_table_answer(answer)
        )
    elif qtype == "composite":
        problems.extend(
            f"q{index}: {problem}" for problem in validate_composite_answer(answer)
        )

    if not str(draft.get("explanation_md", "")).strip():
        problems.append(f"q{index}: missing explanation")
    concepts = draft.get("concepts")
    if not isinstance(concepts, list) or not concepts:
        problems.append(f"q{index}: missing concepts (required for diagnostics)")
    elif len(concepts) > 3:
        problems.append(f"q{index}: more than 3 concepts (atomic tagging)")
    if draft.get("skill") not in SKILLS:
        problems.append(f"q{index}: skill must be one of {SKILLS}")
    if draft.get("bloom") not in BLOOMS:
        problems.append(f"q{index}: bloom must be one of {BLOOMS}")
    try:
        difficulty = float(draft.get("difficulty", 0))
        if not 1 <= difficulty <= 5:
            problems.append(f"q{index}: difficulty must be 1-5")
    except (TypeError, ValueError):
        problems.append(f"q{index}: difficulty must be numeric")
    try:
        expected_time = int(draft.get("expected_time_sec", 0))
        if expected_time <= 0:
            problems.append(f"q{index}: expected_time_sec must be positive")
    except (TypeError, ValueError):
        problems.append(f"q{index}: expected_time_sec must be integer")

    if qtype == "equation" and isinstance(options, list) and len(options) >= 2:
        expected = str(answer.get("value", ""))
        for option_index, option in enumerate(options):
            if expressions_equivalent(str(option), expected):
                problems.append(f"q{index}: distractor {option_index} equals the answer")
    return problems


def _build_prompt(
    *,
    count: int,
    difficulty: int | None,
    topic: str | None,
    skill: str | None,
    context: ContextBundle | None,
    question_types: list[str] | None = None,
) -> str:
    blueprint = _default_blueprint(count, question_types)
    type_counts: dict[str, int] = {}
    for entry in blueprint:
        type_counts[entry["type"]] = type_counts.get(entry["type"], 0) + 1
    focus_lines = []
    if topic:
        focus_lines.append(
            f"FOCUS TOPIC: every question must target the concept '{topic}'."
        )
    if skill:
        focus_lines.append(
            f"SKILL FOCUS: questions must exercise {skill} ability "
            "(set each question's skill accordingly)."
        )
    if question_types:
        focus_lines.append(
            "QUESTION TYPES: use only these types: " + ", ".join(question_types) + "."
        )
    difficulty_note = f"target difficulty {difficulty}" if difficulty else "mixed difficulty"
    prompt = (
        ("\n".join(focus_lines) + "\n\n" if focus_lines else "")
        + f"Write exactly {count} questions with this type mix: "
        + ", ".join(f"{v} x {k}" for k, v in type_counts.items())
        + f". {difficulty_note}."
    )
    context_text = context.render_prompt() if context is not None else ""
    if context_text:
        prompt = f"{prompt}\n\n{context_text}"
    return prompt


class QuizgenService:
    def __init__(self, session: Session, gateway: LLMGateway) -> None:
        self._session = session
        self._gateway = gateway

    def generate(
        self,
        activity: Activity,
        *,
        count: int = 8,
        difficulty: int | None = None,
        context: ContextBundle | None = None,
        topic: str | None = None,
        skill: str | None = None,
        question_types: list[str] | None = None,
        shuffle: bool = False,
    ) -> tuple[list[Question], list[str]]:
        count = max(1, min(count, 30))
        prompt = _build_prompt(
            count=count,
            difficulty=difficulty,
            topic=topic,
            skill=skill,
            context=context,
            question_types=question_types,
        )

        def validate(draft: dict[str, Any]) -> list[str]:
            drafts = draft.get("questions")
            if not isinstance(drafts, list):
                return ["response missing questions list"]
            problems: list[str] = []
            for index, entry in enumerate(drafts[:count]):
                if question_types and entry.get("type") not in question_types:
                    problems.append(
                        f"q{index}: type '{entry.get('type')}' not in allowed set"
                    )
                problems.extend(validate_question(entry, index))
            if len(drafts) < count:
                problems.append(f"only {len(drafts)}/{count} questions returned")
            return problems

        runner = TaskRunner(self._session, self._gateway)
        result = runner.run_json(
            task=QUIZGEN_TASK,
            prompt=prompt,
            validate=validate,
            fallback_system=QUIZGEN_SYSTEM,
            skill_key=QUIZGEN_SKILL,
            course_id=activity.course_id,
            render_vars={"topic": topic or "", "count": str(count)},
            max_rounds=MAX_REPAIR_ROUNDS,
            error_type=QuizgenError,
            audit=AuditRef("quizgen", activity.id, "generate questions"),
            schema=QuizgenOut,
        )
        drafts = result.draft.get("questions", [])[:count]
        problems = result.problems
        registry = context.mentions() if context is not None else None

        questions: list[Question] = []
        for index, draft in enumerate(drafts):
            flag = "review" if validate_question(draft, index) else "ok"
            explanation_md = draft.get("explanation_md", "")
            explanation_block: dict[str, Any] = {"type": "text", "md": explanation_md}
            if registry is not None:
                used = registry.parse(str(explanation_md))
                if used:
                    explanation_block["mentions"] = [entry.as_dict() for entry in used]
            questions.append(
                Question(
                    activity_id=activity.id,
                    type=draft["type"],
                    stem=[{"type": "text", "md": draft.get("stem_md", "")}],
                    options=(
                        [{"type": "text", "md": option} for option in draft["options_md"]]
                        if draft.get("options_md")
                        else None
                    ),
                    answer=draft.get("answer", {}),
                    explanation=[explanation_block],
                    difficulty=float(draft.get("difficulty", 3) or 3),
                    bloom=draft.get("bloom"),
                    skill=draft.get("skill"),
                    concept_ids=[],
                    expected_time_sec=int(draft.get("expected_time_sec", 60) or 60),
                    source_refs=None,
                    distractor_misconceptions=draft.get("misconceptions"),
                    sympy_check=draft.get("sympy_check"),
                    tags=draft.get("concepts"),
                    provenance={"generator": "quizgen"},
                    flag=flag,
                )
            )
        if shuffle:
            self._shuffle_questions(questions, activity.id)
        self._session.add_all(questions)
        self._session.flush()
        return questions, problems

    def _shuffle_questions(self, questions: list[Question], seed: int) -> None:
        rng = random.Random(seed)
        rng.shuffle(questions)
        for question in questions:
            if question.type not in ("single", "multi") or not question.options:
                continue
            indexed = list(enumerate(question.options))
            rng.shuffle(indexed)
            remap = [old_index for old_index, _ in indexed]
            question.options = [option for _, option in indexed]
            answer = dict(question.answer or {})
            if question.type == "single":
                old = answer.get("index")
                if isinstance(old, int) and 0 <= old < len(remap):
                    answer["index"] = remap.index(old)
            else:
                indices = answer.get("indices")
                if isinstance(indices, list):
                    answer["indices"] = [
                        remap.index(old)
                        for old in indices
                        if isinstance(old, int) and 0 <= old < len(remap)
                    ]
            question.answer = answer
            misconceptions = question.distractor_misconceptions or {}
            if misconceptions:
                question.distractor_misconceptions = {
                    str(remap.index(int(old))): tag
                    for old, tag in misconceptions.items()
                    if str(old).isdigit() and 0 <= int(old) < len(remap)
                }
