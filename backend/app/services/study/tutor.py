import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...ai.contracts.contracts import Constraint, validate
from ...ai.gateway import LLMGateway, Message
from ...domain.models import (
    AiInteraction,
    Attempt,
    ExerciseSession,
    ExerciseStep,
    Question,
    StepAttempt,
)
from ...math.equivalence import equivalent
from ..platform.skills import SkillService

TUTOR_TASK = "tutor"
MAX_REPAIR_ROUNDS = 2

LADDER_WORDS = {1: 50, 2: 70, 3: 100, 4: 140, 5: 400}

TUTOR_SKILL = "tutor.hint"
QUIZ_HELP_SKILL = "quiz.help_hint"

LADDER = {
    1: "restate the problem and clarify what is being asked; do not use any math from the solution",
    2: "give one nudge: name the relevant property or theorem only; no formulas from the solution",
    3: "outline the strategy as short steps; still no worked math",
    4: "show a partial solution: the setup and first move, then stop before the final computation",
    5: "give the full worked solution with explanations",
}


class TutorError(ValueError):
    pass


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _blocks_md(blocks: list[dict[str, Any]] | None) -> str:
    if not blocks:
        return ""
    parts = []
    for block in blocks:
        if block.get("type") == "text" and block.get("md"):
            parts.append(str(block["md"]))
        elif block.get("latex"):
            parts.append(f"${block['latex']}$")
    return "\n".join(parts)


def quiz_guard_context(question: Question) -> dict[str, Any]:
    answer = question.answer or {}
    expected: str | None = None
    candidates: list[str] = []
    forbidden: list[str] = []
    if question.type in ("equation", "numeric"):
        value = answer.get("value")
        expected = str(value) if value not in (None, "") else None
    elif question.type == "text":
        value = answer.get("value")
        if value:
            forbidden.append(str(value))
    elif question.type in ("single", "multi"):
        options = question.options or []
        indices = (
            [answer.get("index")]
            if question.type == "single"
            else list(answer.get("indices") or [])
        )
        for index in indices:
            if isinstance(index, int) and 0 <= index < len(options):
                text = _blocks_md([options[index]])
                if text.strip():
                    forbidden.append(text)
                    candidates.append(text)
    return {"expected": expected, "expected_candidates": candidates, "forbidden_texts": forbidden}


def classify_error(response: str, expected: str, skill: str | None) -> str:
    result = equivalent(response, expected)
    if result.stage == "parse":
        return "misread"
    if result.equivalent:
        return ""
    return "procedural" if skill == "procedural" else "conceptual"


class TutorService:
    def __init__(self, session: Session, gateway: LLMGateway) -> None:
        self._session = session
        self._gateway = gateway

    def check_step(
        self,
        step: ExerciseStep,
        response: str,
        skill: str | None = None,
    ) -> tuple[bool, str, str]:
        expected_spec = step.expected or {}
        expected = expected_spec.get("value")
        if expected is None:
            raise TutorError("step has no expected answer configured")
        tolerance = expected_spec.get("tolerance")
        if tolerance is not None and not expected_spec.get("sympy"):
            try:
                ok = abs(float(response) - float(expected)) <= float(tolerance)
                return ok, "numeric", "correct" if ok else "incorrect"
            except (TypeError, ValueError):
                pass
        result = equivalent(response, str(expected))
        if result.equivalent:
            return True, result.stage, "correct"
        error_class = classify_error(response, str(expected), skill)
        return False, result.stage, error_class

    def hint(
        self,
        exercise_session: ExerciseSession,
        step: ExerciseStep,
        level: int,
        last_response: str | None,
    ) -> dict[str, Any]:
        if not 1 <= level <= 5:
            raise TutorError("hint level must be 1-5")
        if level < 5:
            previous = list(
                self._session.scalars(
                    select(StepAttempt)
                    .where(
                        StepAttempt.session_id == exercise_session.id,
                        StepAttempt.step_idx == exercise_session.current_step_idx,
                    )
                    .order_by(StepAttempt.id.desc())
                )
            )
            highest_used = max(
                (attempt.hint_level_used or 0 for attempt in previous), default=0
            )
            if level > highest_used + 1:
                raise TutorError(
                    "the ladder does not skip levels — request the next level first"
                )

        expected_spec = step.expected or {}
        expected = expected_spec.get("value")
        if level == 5 or expected is None:
            context: dict[str, Any] = {"expected": None}
        else:
            context = {"expected": str(expected)}

        prompt = (
            f"Step prompt:\n{_blocks_md(step.prompt)}\n\n"
            + (f"Student's latest attempt:\n{last_response}\n\n" if last_response else "")
            + f"Hint level requested: {level} ({LADDER[level]}).\n"
            + (
                "Socratic mode is ON: your entire reply must be a guiding question "
                "(end with '?').\n"
                if exercise_session.socratic and level < 5
                else ""
            )
        )

        skills = SkillService(self._session)
        version = skills.resolve(TUTOR_SKILL, course_id=exercise_session.exercise.course_id)
        if version is None:
            from ...ai.skills import TUTOR_SYSTEM

            system_prompt = TUTOR_SYSTEM
            constraints = [
                        Constraint("no_answer_reveal"),
                        Constraint("max_words", {"n": LADDER_WORDS[level]}),
                    ]
            skill_version_id = None
        else:
            system_prompt, _user = skills.render(
                version,
                    {
                        "hint_level": str(level),
                        "step_prompt": _blocks_md(step.prompt),
                        "last_response": last_response or "",
                    }
            )
            constraints = skills.constraints(version, {"hint_level": level})
            skill_version_id = version.id

        output = ""
        feedback = ""
        started = time.monotonic()
        model_name: str | None = None
        for _attempt in range(MAX_REPAIR_ROUNDS + 1):
            messages = [Message(role="system", content=system_prompt)]
            if feedback:
                messages.append(
                    Message(
                        role="system",
                        content=f"Your previous hint broke the rules ({feedback}). "
                        "Rewrite it obeying every rule.",
                    )
                )
            messages.append(Message(role="user", content=prompt))
            output = self._gateway.generate(
                TUTOR_TASK,
                messages,
                course_id=exercise_session.exercise.course_id,
            )
            try:
                model_name = self._gateway.resolve(
                    TUTOR_TASK, exercise_session.exercise.course_id
                ).label
            except Exception:
                model_name = None
            validation = validate(output, constraints, context)
            if validation.ok:
                feedback = ""
                break
            feedback = validation.feedback()
        latency_ms = int((time.monotonic() - started) * 1000)

        self._session.add(
            AiInteraction(
                context_type="tutor",
                context_id=exercise_session.id,
                direction=f"hint level {level}",
                model=model_name,
                skill_version_id=skill_version_id,
                input_tokens=_estimate_tokens(prompt),
                output_tokens=_estimate_tokens(output),
                latency_ms=latency_ms,
            )
        )
        self._session.flush()
        return {"level": level, "markdown": output, "violations": feedback or None}

    def quiz_hint(
        self,
        attempt: Attempt,
        question: Question,
        level: int,
        last_response: Any = None,
    ) -> dict[str, Any]:
        if not 1 <= level <= 5:
            raise TutorError("hint level must be 1-5")
        context = quiz_guard_context(question)
        prompt = f"Quiz question:\n{_blocks_md(question.stem)}\n\n"
        if question.options:
            option_lines = [
                f"  {chr(65 + index)}. {_blocks_md([option])}"
                for index, option in enumerate(question.options)
            ]
            prompt += "Options:\n" + "\n".join(option_lines) + "\n\n"
        if last_response not in (None, "", []):
            prompt += f"Student's current answer: {last_response}\n\n"
        prompt += f"Hint level requested: {level} ({LADDER[level]}).\n"

        skills = SkillService(self._session)
        activity = attempt.activity
        version = skills.resolve(
            QUIZ_HELP_SKILL, course_id=activity.course_id if activity else None
        )
        if version is None:
            from ...ai.skills import QUIZ_HELP_SYSTEM

            system_prompt = QUIZ_HELP_SYSTEM
            constraints = [
                        Constraint("no_answer_reveal"),
                        Constraint("max_words", {"n": LADDER_WORDS[level]}),
                    ]
            skill_version_id = None
        else:
            system_prompt, _user = skills.render(
                version,
                {
                    "hint_level": str(level),
                    "question_stem": _blocks_md(question.stem),
                },
            )
            constraints = skills.constraints(version, {"hint_level": level})
            skill_version_id = version.id
        if level == 5:
            guard_context: dict[str, Any] = {"expected": None}
        else:
            guard_context = context

        output = ""
        feedback = ""
        started = time.monotonic()
        model_name: str | None = None
        for _attempt in range(MAX_REPAIR_ROUNDS + 1):
            messages = [Message(role="system", content=system_prompt)]
            if feedback:
                messages.append(
                    Message(
                        role="system",
                        content=f"Your previous hint broke the rules ({feedback}). "
                        "Rewrite it obeying every rule.",
                    )
                )
            messages.append(Message(role="user", content=prompt))
            output = self._gateway.generate(
                TUTOR_TASK,
                messages,
                course_id=activity.course_id if activity else None,
            )
            try:
                model_name = self._gateway.resolve(
                    TUTOR_TASK, activity.course_id if activity else None
                ).label
            except Exception:
                model_name = None
            validation = validate(output, constraints, guard_context)
            if validation.ok:
                feedback = ""
                break
            feedback = validation.feedback()
        latency_ms = int((time.monotonic() - started) * 1000)

        self._session.add(
            AiInteraction(
                context_type="quiz_help",
                context_id=attempt.id,
                direction=f"hint level {level} q{question.id}",
                model=model_name,
                skill_version_id=skill_version_id,
                input_tokens=_estimate_tokens(prompt),
                output_tokens=_estimate_tokens(output),
                latency_ms=latency_ms,
            )
        )
        self._session.flush()
        return {"level": level, "markdown": output, "violations": feedback or None}

    @staticmethod
    def independence_score(session_attempts: list[StepAttempt]) -> float:
        penalty = 0.0
        for attempt in session_attempts:
            if attempt.hint_level_used:
                penalty += attempt.hint_level_used * 0.05
            if attempt.correct is False:
                penalty += 0.02
        return round(max(0.0, 1.0 - penalty), 4)
