from typing import Any

from sqlalchemy.orm import Session

from ..ai.gateway import LLMGateway
from ..ai.runner import AuditRef, TaskRunner
from ..ai.skills import EXGEN_SYSTEM
from ..ai.structured import ExerciseOut
from ..ai.widgets import EXGEN_WIDGET_DOC, validate_widget_block
from ..domain.models import Exercise, ExerciseStep
from ..math.equivalence import expressions_equivalent, parse_math
from ..math.regions import validate_region_answer
from ..services.knowledge.context import ContextBundle
from ..services.study.exercise_kinds import RUBRIC_KINDS, STRUCTURAL_KINDS
from ..services.study.exercise_rubric import validate_rubric_payload
from ..services.study.exercise_structs import validate_structural_payload

EXGEN_TASK = "exgen"
EXGEN_SKILL = "exercise.generate"
MAX_REPAIR_ROUNDS = 2
MAX_STEPS = 8

STRUCTURAL_SCHEMAS: dict[str, str] = {
    "matching": (
        '{"title": str, "kind": "matching", "prompt_md": str (instructions), '
        '"payload": {"pairs": [{"left": str, "right": str}, ...]}} — 3-6 pairs, '
        "each left matches exactly one right; unique labels"
    ),
    "ordering": (
        '{"title": str, "kind": "ordering", "prompt_md": str (instructions), '
        '"payload": {"items": [str, ...]}} — 4-6 items listed in the CORRECT '
        "canonical order (the student will reorder them)"
    ),
    "categorize": (
        '{"title": str, "kind": "categorize", "prompt_md": str (instructions), '
        '"payload": {"categories": [str, ...], "items": [{"label": str, '
        '"category": 0-based index}, ...]}} — 2-4 categories, 4-8 items'
    ),
    "fill_blank": (
        '{"title": str, "kind": "fill_blank", "prompt_md": str (instructions), '
        '"payload": {"prompt_md": str with {{1}}, {{2}}, ... blanks, '
        '"answers": [str or [alt1, alt2], ...]}} — 2-5 numbered blanks, '
        "answers aligned to blank numbers (a list entry gives accepted alternatives)"
    ),
    "explain": (
        '{"title": str, "kind": "explain", "prompt_md": str (the question asking the '
        "student to explain a concept in their own words), "
        '"payload": {"prompt_md": str, "rubric": [{"id": str, "text": str}, ...]}} — '
        "2-5 rubric rows a good answer must cover"
    ),
    "error_spot": (
        '{"title": str, "kind": "error_spot", "prompt_md": str (instructions), '
        '"payload": {"prompt_md": str, "lines": [str, ...] (a worked solution with '
        "EXACTLY ONE flawed line), "
        '"flaw_index": 0-based index of the flawed line, '
        '"rubric": [{"id": str, "text": str}, ...] (what identifies the flaw)}}'
    ),
    "correct_solution": (
        '{"title": str, "kind": "correct_solution", "prompt_md": str (instructions), '
        '"payload": {"prompt_md": str (presenting the flawed line from a worked '
        "solution), "
        '"fix": str (the expected corrected line the student must type), '
        '"rubric": [{"id": str, "text": str}, ...]}}'
    ),
}


def _structural_problems(draft: dict[str, Any], kind: str) -> list[str]:
    problems: list[str] = []
    if not str(draft.get("title", "")).strip():
        problems.append("empty title")
    if draft.get("kind") != kind:
        problems.append(f"kind must be {kind}")
        return problems
    if not str(draft.get("prompt_md", "")).strip():
        problems.append("empty prompt_md")
    payload = draft.get("payload")
    if not isinstance(payload, dict):
        problems.append("payload object required")
        return problems
    if kind in RUBRIC_KINDS:
        problems.extend(validate_rubric_payload(kind, payload))
    else:
        problems.extend(validate_structural_payload(kind, payload))
    return problems

class ExgenError(ValueError):
    pass


def _step_problems(step: dict[str, Any], index: int) -> list[str]:
    problems: list[str] = []
    label = f"step {index}"
    if not str(step.get("prompt_md", "")).strip():
        problems.append(f"{label}: empty prompt")
        return problems
    kind = step.get("expected_kind")
    value = step.get("expected_value")
    if kind not in ("math", "numeric", "numberline"):
        problems.append(f"{label}: expected_kind must be math, numeric or numberline")
        return problems
    if value is None or not str(value).strip():
        problems.append(f"{label}: missing expected_value")
        return problems
    if kind == "math":
        try:
            parse_math(str(value))
        except Exception:
            problems.append(f"{label}: expected_value does not parse as math ({value!r})")
    elif kind == "numberline":
        if not isinstance(value, dict):
            problems.append(
                f"{label}: numberline expected_value must be the answer object "
                "{domain, points, intervals}"
            )
        else:
            problems.extend(
                f"{label}: {problem}" for problem in validate_region_answer(value)
            )
    else:
        try:
            float(str(value))
        except ValueError:
            problems.append(f"{label}: numeric expected_value is not a number ({value!r})")
            return problems
        tolerance = step.get("tolerance")
        if tolerance is not None:
            try:
                if float(tolerance) < 0:
                    problems.append(f"{label}: negative tolerance")
            except (TypeError, ValueError):
                problems.append(f"{label}: tolerance must be numeric")
    widgets = step.get("widgets")
    if widgets is not None:
        if not isinstance(widgets, list):
            problems.append(f"{label}: widgets must be a list")
        else:
            for widget_block in widgets:
                problems.extend(
                    f"{label}: {problem}" for problem in validate_widget_block(widget_block)
                )
    return problems


def validate_exercise_draft(draft: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if not str(draft.get("title", "")).strip():
        problems.append("empty title")
    steps = draft.get("steps")
    if not isinstance(steps, list) or not steps:
        problems.append("at least one step is required")
        return problems
    if len(steps) > MAX_STEPS:
        problems.append(f"more than {MAX_STEPS} steps")
        return problems
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            problems.append(f"step {index}: not an object")
            continue
        problems.extend(_step_problems(step, index))
    try:
        difficulty = float(draft.get("difficulty", 3))
        if not 1 <= difficulty <= 5:
            problems.append("difficulty must be 1-5")
    except (TypeError, ValueError):
        problems.append("difficulty must be numeric")
    return problems


def validate_variant(
    draft: dict[str, Any], source_steps: list[dict[str, Any]]
) -> list[str]:
    problems: list[str] = []
    steps = draft.get("steps")
    if isinstance(steps, list) and source_steps:
        if len(steps) != len(source_steps):
            problems.append(
                f"variant must keep the step structure ({len(source_steps)} steps)"
            )
            return problems
        changed = False
        for index, (step, source) in enumerate(zip(steps, source_steps, strict=False)):
            if str(step.get("prompt_md", "")).strip() == str(source["prompt_md"]).strip():
                problems.append(f"step {index}: prompt is identical to the source")
            if not expressions_equivalent(
                str(step.get("expected_value", "")), str(source["expected"])
            ):
                changed = True
        if not changed and not problems:
            problems.append("variant answers are all equivalent to the source — not a variant")
    return problems


class ExgenService:
    def __init__(self, session: Session, gateway: LLMGateway) -> None:
        self._session = session
        self._gateway = gateway

    def generate(
        self,
        profile_id: int,
        *,
        course_id: int | None = None,
        node_id: int | None = None,
        topic: str | None = None,
        difficulty: float | None = None,
        step_count: int = 4,
        kind: str = "multi_step",
        context: ContextBundle | None = None,
        source: Exercise | None = None,
        pattern: str | None = None,
        pattern_description: str | None = None,
        pattern_example: str | None = None,
        subject: str | None = None,
    ) -> tuple[Exercise, list[str]]:
        if kind in STRUCTURAL_KINDS and source is None and pattern is None:
            return self._generate_structural(
                profile_id,
                course_id=course_id,
                node_id=node_id,
                topic=topic,
                difficulty=difficulty,
                kind=kind,
                context=context,
            )
        if kind in RUBRIC_KINDS and source is None and pattern is None:
            return self._generate_structural(
                profile_id,
                course_id=course_id,
                node_id=node_id,
                topic=topic,
                difficulty=difficulty,
                kind=kind,
                context=context,
            )
        step_count = max(1, min(step_count, MAX_STEPS))
        prompt = self._build_prompt(
            topic=topic,
            difficulty=difficulty,
            step_count=step_count,
            context=context,
            source=source,
            pattern=pattern,
            pattern_description=pattern_description,
            pattern_example=pattern_example,
            subject=subject,
        )
        source_steps: list[dict[str, Any]] = []
        if source is not None:
            for step in source.steps:
                source_steps.append(
                    {
                        "prompt_md": self._steps_md([step]),
                        "expected": str((step.expected or {}).get("value", "")),
                    }
                )

        def validate(draft: dict[str, Any]) -> list[str]:
            problems = validate_exercise_draft(draft)
            if source is not None:
                problems.extend(validate_variant(draft, source_steps))
            return problems

        resolved_course_id = course_id if source is None else source.course_id
        if source is not None:
            direction = f"similar to exercise {source.id}"
        elif pattern is not None:
            direction = f"drill pattern {pattern}"
        else:
            direction = "exercise generation"
        runner = TaskRunner(self._session, self._gateway)
        result = runner.run_json(
            task=EXGEN_TASK,
            prompt=prompt,
            validate=validate,
            fallback_system=EXGEN_SYSTEM,
            skill_key=EXGEN_SKILL,
            course_id=resolved_course_id,
            render_vars={"topic": topic or "", "count": str(step_count)},
            max_rounds=MAX_REPAIR_ROUNDS,
            error_type=ExgenError,
            audit=AuditRef("exgen", None, direction),
            schema=ExerciseOut,
        )
        draft = result.draft
        problems = result.problems
        if problems:
            raise ExgenError(
                "exercise did not pass validation after repairs: " + "; ".join(problems[:10])
            )

        if source is not None:
            created_from: dict[str, Any] = {"source": "similar", "from_exercise_id": source.id}
        elif pattern is not None:
            created_from = {"source": "drill", "pattern": pattern}
        else:
            created_from = {"generator": "exgen"}
        registry = context.mentions() if context is not None else None

        def _text_block(markdown: str) -> dict[str, Any]:
            block: dict[str, Any] = {"type": "text", "md": markdown}
            if registry is not None:
                used = registry.parse(str(markdown))
                if used:
                    block["mentions"] = [entry.as_dict() for entry in used]
            return block

        exercise = Exercise(
            profile_id=profile_id,
            course_id=course_id if source is None else source.course_id,
            node_id=node_id if source is None else source.node_id,
            title=str(draft.get("title", "Exercise")).strip()[:300],
            context=(
                [_text_block(draft["context_md"])]
                if str(draft.get("context_md", "")).strip()
                else None
            ),
            difficulty=float(draft.get("difficulty", 3) or 3),
            created_from=created_from,
        )
        self._session.add(exercise)
        self._session.flush()
        for index, step in enumerate(draft.get("steps", [])):
            expected: dict[str, Any] = {
                "kind": step.get("expected_kind"),
                "value": (
                    step.get("expected_value")
                    if step.get("expected_kind") == "numberline"
                    else str(step.get("expected_value", ""))
                ),
            }
            if step.get("tolerance") is not None:
                expected["tolerance"] = step.get("tolerance")
            prompt_blocks: list[dict[str, Any]] = [_text_block(str(step.get("prompt_md", "")))]
            for widget_block in step.get("widgets") or []:
                if isinstance(widget_block, dict):
                    prompt_blocks.append(widget_block)
            self._session.add(
                ExerciseStep(
                    exercise_id=exercise.id,
                    order_idx=index,
                    prompt=prompt_blocks,
                    expected=expected,
                )
            )
        self._session.flush()
        return exercise, problems

    def _generate_structural(
        self,
        profile_id: int,
        *,
        course_id: int | None,
        node_id: int | None,
        topic: str | None,
        difficulty: float | None,
        kind: str,
        context: ContextBundle | None,
    ) -> tuple[Exercise, list[str]]:
        prompt = self._build_structural_prompt(
            topic=topic, difficulty=difficulty, kind=kind, context=context
        )

        def validate(draft: dict[str, Any]) -> list[str]:
            return _structural_problems(draft, kind)

        runner = TaskRunner(self._session, self._gateway)
        result = runner.run_json(
            task=EXGEN_TASK,
            prompt=prompt,
            validate=validate,
            fallback_system=EXGEN_SYSTEM,
            skill_key=EXGEN_SKILL,
            course_id=course_id,
            render_vars={"topic": topic or "", "count": "1"},
            max_rounds=MAX_REPAIR_ROUNDS,
            error_type=ExgenError,
            audit=AuditRef("exgen", None, f"generate {kind} exercise"),
            schema=ExerciseOut,
        )
        if result.problems:
            raise ExgenError(
                "exercise did not pass validation after repairs: "
                + "; ".join(result.problems[:10])
            )
        draft = result.draft
        registry = context.mentions() if context is not None else None

        def _text_block(markdown: str) -> dict[str, Any]:
            block: dict[str, Any] = {"type": "text", "md": markdown}
            if registry is not None:
                used = registry.parse(str(markdown))
                if used:
                    block["mentions"] = [entry.as_dict() for entry in used]
            return block

        exercise = Exercise(
            profile_id=profile_id,
            course_id=course_id,
            node_id=node_id,
            title=str(draft.get("title", "Exercise")).strip()[:300],
            kind=kind,
            difficulty=(
                float(draft.get("difficulty", 3) or 3)
                if draft.get("difficulty") is not None
                else difficulty
            ),
            created_from={"generator": "exgen", "kind": kind},
        )
        self._session.add(exercise)
        self._session.flush()
        expected = {"kind": kind, **(draft.get("payload") or {})}
        self._session.add(
            ExerciseStep(
                exercise_id=exercise.id,
                order_idx=0,
                prompt=[_text_block(str(draft.get("prompt_md", "")))],
                expected=expected,
            )
        )
        self._session.flush()
        return exercise, []

    def _build_structural_prompt(
        self,
        *,
        topic: str | None,
        difficulty: float | None,
        kind: str,
        context: ContextBundle | None,
    ) -> str:
        sections: list[str] = [
            f"Create ONE {kind.replace('_', ' ')} practice exercise.",
            f"Return a JSON object with exactly this shape: {STRUCTURAL_SCHEMAS[kind]}",
        ]
        if topic:
            sections.append(f"Topic: {topic}")
        if difficulty is not None:
            sections.append(f"Target difficulty: {difficulty} of 5.")
        if context is not None:
            context_text = context.render_prompt()
            if context_text:
                sections.append(context_text)
        return "\n\n".join(sections)

    @staticmethod
    def _steps_md(steps: list[ExerciseStep]) -> str:
        parts: list[str] = []
        for step in steps:
            for block in step.prompt or []:
                if block.get("type") == "text" and block.get("md"):
                    parts.append(str(block["md"]))
        return "\n".join(parts)

    def _build_prompt(
        self,
        *,
        topic: str | None,
        difficulty: float | None,
        step_count: int,
        context: ContextBundle | None,
        source: Exercise | None,
        pattern: str | None,
        pattern_description: str | None = None,
        pattern_example: str | None = None,
        subject: str | None = None,
    ) -> str:
        sections: list[str] = []
        if source is not None:
            source_steps = "\n".join(
                f"  {index + 1}. {self._steps_md([step])} → expected: "
                f"{(step.expected or {}).get('value', '')}"
                for index, step in enumerate(source.steps)
            )
            sections.append(
                "Create an ISOMORPHIC VARIANT of the exercise below: same skills and step "
                "structure, but different numbers, functions, or context so the answers "
                f"change.\nTitle: {source.title}\nSteps:\n{source_steps}"
            )
        elif pattern is not None:
            subject_word = subject or "course"
            description = pattern_description or pattern
            example_line = f" Example: {pattern_example}" if pattern_example else ""
            sections.append(
                f"Create a short ERROR-PATTERN DRILL (2-4 steps) targeting this common "
                f"{subject_word} error: {description}.{example_line} Design the steps so "
                "that a student making this exact error would get a wrong (checkable) "
                "intermediate result, and the final step confirms the correct result."
            )
        else:
            sections.append(
                f"Create a multi-step guided exercise with exactly {step_count} steps."
            )
        if topic:
            sections.append(f"Topic: {topic}")
        if difficulty is not None:
            sections.append(f"Target difficulty: {difficulty} of 5.")
        if context is not None:
            context_text = context.render_prompt()
            if context_text:
                sections.append(context_text)
        sections.append(EXGEN_WIDGET_DOC)
        return "\n\n".join(sections)
