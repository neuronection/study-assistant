import json
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from ..domain.models import AiInteraction
from ..services.skills import SkillService
from .gateway import LLMGateway, Message
from .parsing import estimate_tokens, extract_json_object

DEFAULT_MAX_ROUNDS = 2


@dataclass(frozen=True)
class AuditRef:
    context_type: str
    context_id: int | None
    direction: str


@dataclass
class TaskRunResult:
    draft: dict[str, Any]
    problems: list[str]
    rounds: int
    prompt: str
    system_prompt: str
    skill_version_id: int | None
    model_label: str | None
    latency_ms: int
    output_text: str


class TaskRunner:
    def __init__(self, session: Session, gateway: LLMGateway) -> None:
        self._session = session
        self._gateway = gateway

    def model_label(self, task: str, course_id: int | None = None) -> str | None:
        try:
            return self._gateway.resolve(task, course_id).label
        except Exception:
            return None

    def resolve_system(
        self,
        *,
        skill_key: str,
        course_id: int | None,
        fallback_system: str,
        render_vars: dict[str, Any] | None = None,
    ) -> tuple[str, int | None]:
        version = SkillService(self._session).resolve(skill_key, course_id=course_id)
        if version is not None:
            system, _user = SkillService(self._session).render(version, render_vars or {})
            return system, version.id
        return fallback_system, None

    def run_json(
        self,
        *,
        task: str,
        prompt: str,
        validate: Callable[[dict[str, Any]], list[str]],
        fallback_system: str,
        skill_key: str | None = None,
        course_id: int | None = None,
        render_vars: dict[str, Any] | None = None,
        max_rounds: int = DEFAULT_MAX_ROUNDS,
        error_type: type[ValueError] = ValueError,
        audit: AuditRef | None = None,
        schema: type[Any] | None = None,
    ) -> TaskRunResult:
        if skill_key is not None:
            system_prompt, skill_version_id = self.resolve_system(
                skill_key=skill_key,
                course_id=course_id,
                fallback_system=fallback_system,
                render_vars=render_vars,
            )
        else:
            system_prompt, skill_version_id = fallback_system, None
        started = time.monotonic()
        draft: dict[str, Any] = {}
        problems: list[str] = []
        feedback: str | None = None
        rounds = 0
        text = ""
        for round_index in range(max_rounds + 1):
            rounds = round_index + 1
            messages = [Message(role="system", content=system_prompt)]
            if feedback:
                messages.append(
                    Message(
                        role="system",
                        content=f"Your previous attempt had these problems: {feedback}. "
                        "Regenerate the complete output fixing every one.",
                    )
                )
            messages.append(Message(role="user", content=prompt))
            if schema is not None:
                structured_draft = self._gateway.generate_structured(
                    task, messages, schema, course_id
                )
                if structured_draft is not None:
                    draft = structured_draft
                    text = json.dumps(draft, ensure_ascii=False)
                    problems = validate(draft)
                    if not problems:
                        break
                    feedback = "; ".join(str(problem) for problem in problems[:12])
                    continue
            text = self._gateway.generate(task, messages, course_id=course_id)
            draft = extract_json_object(text, error_type)
            problems = validate(draft)
            if not problems:
                break
            feedback = "; ".join(str(problem) for problem in problems[:12])
        latency_ms = int((time.monotonic() - started) * 1000)
        label = self.model_label(task, course_id)
        if audit is not None:
            self._session.add(
                AiInteraction(
                    context_type=audit.context_type,
                    context_id=audit.context_id,
                    direction=audit.direction,
                    task=task,
                    model=label,
                    skill_version_id=skill_version_id,
                    input_tokens=estimate_tokens(prompt),
                    output_tokens=estimate_tokens(text),
                    latency_ms=latency_ms,
                )
            )
        return TaskRunResult(
            draft=draft,
            problems=problems,
            rounds=rounds,
            prompt=prompt,
            system_prompt=system_prompt,
            skill_version_id=skill_version_id,
            model_label=label,
            latency_ms=latency_ms,
            output_text=text,
        )

    def run_text(
        self,
        *,
        task: str,
        prompt: str,
        validate: Callable[[str], list[str]],
        fallback_system: str,
        skill_key: str | None = None,
        course_id: int | None = None,
        render_vars: dict[str, Any] | None = None,
        max_rounds: int = DEFAULT_MAX_ROUNDS,
        audit: AuditRef | None = None,
    ) -> TaskRunResult:
        if skill_key is not None:
            system_prompt, skill_version_id = self.resolve_system(
                skill_key=skill_key,
                course_id=course_id,
                fallback_system=fallback_system,
                render_vars=render_vars,
            )
        else:
            system_prompt, skill_version_id = fallback_system, None
        started = time.monotonic()
        problems: list[str] = []
        feedback: str | None = None
        rounds = 0
        text = ""
        for round_index in range(max_rounds + 1):
            rounds = round_index + 1
            messages = [Message(role="system", content=system_prompt)]
            if feedback:
                messages.append(
                    Message(
                        role="system",
                        content=f"Your previous attempt had these problems: {feedback}. "
                        "Regenerate the complete output fixing every one.",
                    )
                )
            messages.append(Message(role="user", content=prompt))
            text = self._gateway.generate(task, messages, course_id=course_id)
            problems = validate(text)
            if not problems:
                break
            feedback = "; ".join(str(problem) for problem in problems[:12])
        latency_ms = int((time.monotonic() - started) * 1000)
        label = self.model_label(task, course_id)
        if audit is not None:
            self._session.add(
                AiInteraction(
                    context_type=audit.context_type,
                    context_id=audit.context_id,
                    direction=audit.direction,
                    task=task,
                    model=label,
                    skill_version_id=skill_version_id,
                    input_tokens=estimate_tokens(prompt),
                    output_tokens=estimate_tokens(text),
                    latency_ms=latency_ms,
                )
            )
        return TaskRunResult(
            draft={},
            problems=problems,
            rounds=rounds,
            prompt=prompt,
            system_prompt=system_prompt,
            skill_version_id=skill_version_id,
            model_label=label,
            latency_ms=latency_ms,
            output_text=text,
        )

    def stream_text(
        self,
        *,
        task: str,
        prompt: str,
        validate: Callable[[str], list[str]],
        fallback_system: str,
        skill_key: str | None = None,
        course_id: int | None = None,
        render_vars: dict[str, Any] | None = None,
        max_rounds: int = DEFAULT_MAX_ROUNDS,
        audit: AuditRef | None = None,
        stop: Callable[[], bool] | None = None,
    ) -> Iterator[tuple[str, Any]]:
        """Yield stream events; the final event is ("result", TaskRunResult).

        Events: ("delta", chunk_text) per stream chunk, ("repair", [problems])
        before each repair re-run, and finally ("result", TaskRunResult). The
        result carries only the *last* round's text (repair rounds replace, not
        append). When `stop()` returns True the stream breaks early and the
        result carries the partial text.
        """
        if skill_key is not None:
            system_prompt, skill_version_id = self.resolve_system(
                skill_key=skill_key,
                course_id=course_id,
                fallback_system=fallback_system,
                render_vars=render_vars,
            )
        else:
            system_prompt, skill_version_id = fallback_system, None
        started = time.monotonic()
        problems: list[str] = []
        feedback: str | None = None
        rounds = 0
        text = ""
        stopped = False
        for round_index in range(max_rounds + 1):
            rounds = round_index + 1
            messages = [Message(role="system", content=system_prompt)]
            if feedback:
                messages.append(
                    Message(
                        role="system",
                        content=f"Your previous attempt had these problems: {feedback}. "
                        "Regenerate the complete output fixing every one.",
                    )
                )
            messages.append(Message(role="user", content=prompt))
            round_parts: list[str] = []
            for chunk in self._gateway.stream(task, messages, course_id=course_id):
                if stop is not None and stop():
                    stopped = True
                    break
                round_parts.append(chunk)
                yield ("delta", chunk)
            text = "".join(round_parts)
            if stopped:
                break
            problems = validate(text)
            if not problems:
                break
            feedback = "; ".join(str(problem) for problem in problems[:12])
            yield ("repair", list(problems))
        latency_ms = int((time.monotonic() - started) * 1000)
        label = self.model_label(task, course_id)
        if audit is not None:
            self._session.add(
                AiInteraction(
                    context_type=audit.context_type,
                    context_id=audit.context_id,
                    direction=audit.direction,
                    task=task,
                    model=label,
                    skill_version_id=skill_version_id,
                    input_tokens=estimate_tokens(prompt),
                    output_tokens=estimate_tokens(text),
                    latency_ms=latency_ms,
                )
            )
        yield (
            "result",
            TaskRunResult(
                draft={},
                problems=problems,
                rounds=rounds,
                prompt=prompt,
                system_prompt=system_prompt,
                skill_version_id=skill_version_id,
                model_label=label,
                latency_ms=latency_ms,
                output_text=text,
            ),
        )
