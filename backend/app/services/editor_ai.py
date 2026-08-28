import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from ..ai.gateway import LLMGateway, ProviderError, TaskUnassigned
from ..ai.runner import AuditRef, TaskRunner
from ..ai.skills import EDITOR_TRANSFORM_SYSTEM
from ..core.events import EventBus

EDITOR_TASK = "editor_transform"
EDITOR_SKILL = "editor.transform"
MAX_REPAIR_ROUNDS = 2
MAX_OUTPUT_CHARS = 8000
MAX_TEXT_CHARS = 12000
MAX_INSTRUCTION_CHARS = 1000
MAX_CONTEXT_CHARS = 6000
JOB_TOPIC = "ai-editor:{}"

EDITOR_PRESETS: dict[str, str] = {
    "explain": (
        "Explain the selected text clearly and in depth, using examples where they help. "
        "Keep any mathematics as LaTeX."
    ),
    "answer": "Answer the question posed by the selected text, directly and accurately.",
    "compact": (
        "Rewrite the selected text to be significantly more compact while keeping all "
        "essential meaning. The result must be shorter than the input."
    ),
    "expand": (
        "Expand the selected text with more detail, explanation, and context while "
        "keeping its intent."
    ),
    "rewrite": (
        "Rewrite the selected text to be clearer and more polished, preserving its "
        "meaning exactly."
    ),
    "simplify": (
        "Rewrite the selected text in simpler, plainer language while preserving its "
        "meaning."
    ),
    "grammar": (
        "Fix grammar, spelling, punctuation, and phrasing errors in the selected text. "
        "Do not change the meaning."
    ),
    "structure": (
        "Reorganize the selected text with clear headings, paragraphs, and structure. "
        "Keep all the content."
    ),
    "bullets": (
        "Convert the selected text into a clean bulleted or numbered list. Keep the "
        "content."
    ),
    "markdown": (
        "Format the selected text as well-structured GitHub-flavored markdown: headings, "
        "lists, and tables where they help; mathematics as LaTeX."
    ),
    "translate": (
        "Translate the selected text to English, or to the language named in the "
        "instruction if one is given."
    ),
}

PREAMBLE_RE = re.compile(
    r"^\s*(sure[,!. ]|certainly[,!. ]|of course[,!. ]|absolutely[,!. ]|"
    r"here(?:'s| is)|ok(?:ay)?[,!. ]|alright[,!. ]|no problem[,!. ])",
    re.IGNORECASE,
)
SENTENCE_RE = re.compile(r"[.!?](?:\s|$)")
RAW_HTML_RE = re.compile(r"<[a-zA-Z][^>]*>")


def _has_preamble(text: str) -> bool:
    return PREAMBLE_RE.match(text) is not None


def _has_sentence(text: str) -> bool:
    return SENTENCE_RE.search(text) is not None


def _dollar_count(text: str) -> int:
    return len(re.findall(r"(?<!\\)\$", text))


def _markdown_sanity(markdown: str) -> list[str]:
    problems: list[str] = []
    fence_lines = [line for line in markdown.splitlines() if line.startswith("```")]
    if len(fence_lines) % 2 != 0:
        problems.append("unbalanced code fences")
    if _dollar_count(markdown) % 2 != 0:
        problems.append("unbalanced math delimiters ($)")
    if RAW_HTML_RE.search(markdown):
        problems.append("raw HTML tags are not allowed")
    return problems


def validate_output(text: str, input_text: str, preset: str | None) -> list[str]:
    problems: list[str] = []
    stripped = text.strip()
    if not stripped:
        return ["empty output"]
    if len(stripped) > MAX_OUTPUT_CHARS:
        problems.append(
            f"output too long ({len(stripped)} chars, limit {MAX_OUTPUT_CHARS})"
        )
    if _has_preamble(stripped):
        problems.append(
            "output starts with a chatty preamble (e.g. 'Sure', 'Here is') — "
            "output only the transformed text"
        )
    if preset == "compact" and len(stripped) > len(input_text.strip()):
        problems.append("compacted output is not shorter than the input")
    if preset == "answer" and not _has_sentence(stripped):
        problems.append("answer contains no complete sentence")
    if preset == "markdown":
        problems.extend(_markdown_sanity(stripped))
    return problems


def build_prompt(
    *,
    text: str,
    instruction: str,
    mode: str,
    context_document: str | None,
    context_material: str | None,
) -> str:
    lines: list[str] = []
    if mode == "transform":
        lines.append("Transform the text below exactly as instructed.")
    else:
        lines.append("Write new markdown text as instructed.")
    if instruction and instruction.strip():
        lines.append(f"Instruction: {instruction.strip()}")
    if context_document and context_document.strip():
        lines.append(
            "Surrounding document context (reference only — use it to inform the "
            "result, do not repeat it unless asked):\n" + context_document.strip()
        )
    if context_material and context_material.strip():
        lines.append(
            "Course material context (reference only — ground factual claims in it "
            "when relevant):\n" + context_material.strip()
        )
    lines.append("TEXT:")
    lines.append(text.strip() if text.strip() else "(no text provided — write fresh content)")
    return "\n\n".join(lines)


def _effective_instruction(instruction: str, preset: str | None) -> str:
    preset_key = preset if preset in EDITOR_PRESETS else None
    effective = (instruction or "").strip()
    if preset_key is not None and not effective:
        effective = EDITOR_PRESETS[preset_key]
    return effective


@dataclass
class EditorTransformResult:
    output_md: str
    problems: list[str]
    rounds: int
    model_label: str | None


@dataclass
class EditorTransformJob:
    id: int
    status: str = "queued"
    result_md: str = ""
    error: str | None = None
    model_label: str | None = None
    problems: list[str] = field(default_factory=list)
    rounds: int = 0
    cancelled: bool = False


class EditorTransformService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        gateway: LLMGateway,
    ) -> None:
        self._session_factory = session_factory
        self._gateway = gateway
        self._jobs: dict[int, EditorTransformJob] = {}
        self._jobs_lock = threading.Lock()
        self._next_job_id = 1

    def _publish(self, bus: EventBus | None, job_id: int, payload: dict[str, Any]) -> None:
        if bus is not None:
            bus.publish_threadsafe(JOB_TOPIC.format(job_id), payload)

    def transform(
        self,
        *,
        text: str,
        instruction: str,
        preset: str | None,
        mode: str,
        context_document: str | None = None,
        context_material: str | None = None,
        course_id: int | None = None,
    ) -> EditorTransformResult:
        prompt = build_prompt(
            text=text,
            instruction=_effective_instruction(instruction, preset),
            mode=mode,
            context_document=context_document,
            context_material=context_material,
        )
        preset_key = preset if preset in EDITOR_PRESETS else None
        with self._session_factory() as session:
            runner = TaskRunner(session, self._gateway)
            result = runner.run_text(
                task=EDITOR_TASK,
                prompt=prompt,
                validate=lambda out: validate_output(out, text, preset_key),
                fallback_system=EDITOR_TRANSFORM_SYSTEM,
                skill_key=EDITOR_SKILL,
                course_id=course_id,
                max_rounds=MAX_REPAIR_ROUNDS,
                audit=AuditRef("editor_transform", course_id, f"editor {preset_key or 'write'}"),
            )
            session.commit()
        return EditorTransformResult(
            output_md=result.output_text.strip(),
            problems=result.problems,
            rounds=result.rounds,
            model_label=result.model_label,
        )

    def start_transform(
        self,
        *,
        text: str,
        instruction: str,
        preset: str | None,
        mode: str,
        context_document: str | None = None,
        context_material: str | None = None,
        course_id: int | None = None,
        bus: EventBus | None = None,
    ) -> EditorTransformJob:
        with self._jobs_lock:
            job = EditorTransformJob(id=self._next_job_id)
            self._next_job_id += 1
            self._jobs[job.id] = job
        thread = threading.Thread(
            target=self._run_job,
            args=(
                job,
                text,
                instruction,
                preset,
                mode,
                context_document,
                context_material,
                course_id,
                bus,
            ),
            name=f"editor-ai-{job.id}",
            daemon=True,
        )
        thread.start()
        return job

    def _run_job(
        self,
        job: EditorTransformJob,
        text: str,
        instruction: str,
        preset: str | None,
        mode: str,
        context_document: str | None,
        context_material: str | None,
        course_id: int | None,
        bus: EventBus | None,
    ) -> None:
        preset_key = preset if preset in EDITOR_PRESETS else None
        prompt = build_prompt(
            text=text,
            instruction=_effective_instruction(instruction, preset),
            mode=mode,
            context_document=context_document,
            context_material=context_material,
        )
        job.status = "running"
        self._publish(bus, job.id, {"type": "editor_start", "job_id": job.id})
        try:
            with self._session_factory() as session:
                runner = TaskRunner(session, self._gateway)

                def stopped() -> bool:
                    return job.cancelled

                for kind, value in runner.stream_text(
                    task=EDITOR_TASK,
                    prompt=prompt,
                    validate=lambda out: validate_output(out, text, preset_key),
                    fallback_system=EDITOR_TRANSFORM_SYSTEM,
                    skill_key=EDITOR_SKILL,
                    course_id=course_id,
                    max_rounds=MAX_REPAIR_ROUNDS,
                    audit=AuditRef(
                        "editor_transform", course_id, f"editor {preset_key or 'write'}"
                    ),
                    stop=stopped,
                ):
                    if kind == "delta":
                        job.result_md += str(value)
                        self._publish(
                            bus, job.id, {"type": "editor_delta", "job_id": job.id, "text": value}
                        )
                    elif kind == "repair":
                        self._publish(
                            bus,
                            job.id,
                            {
                                "type": "editor_repair",
                                "job_id": job.id,
                                "problems": value,
                            },
                        )
                    elif kind == "result":
                        job.problems = value.problems
                        job.rounds = value.rounds
                        job.model_label = value.model_label
                session.commit()
        except (TaskUnassigned, ProviderError) as error:
            job.status = "error"
            job.error = str(error)
            self._publish(
                bus, job.id, {"type": "editor_error", "job_id": job.id, "message": str(error)}
            )
            return
        except Exception as error:
            job.status = "error"
            job.error = str(error)
            self._publish(
                bus, job.id, {"type": "editor_error", "job_id": job.id, "message": str(error)}
            )
            return
        if job.cancelled:
            job.status = "cancelled"
            self._publish(
                bus,
                job.id,
                {
                    "type": "editor_done",
                    "job_id": job.id,
                    "result_md": job.result_md,
                    "cancelled": True,
                },
            )
        elif job.problems:
            job.status = "error"
            job.error = "; ".join(job.problems[:6])
            self._publish(
                bus, job.id, {"type": "editor_error", "job_id": job.id, "message": job.error}
            )
        else:
            job.status = "done"
            self._publish(
                bus, job.id, {"type": "editor_done", "job_id": job.id, "result_md": job.result_md}
            )

    def get_job(self, job_id: int) -> EditorTransformJob | None:
        with self._jobs_lock:
            return self._jobs.get(job_id)

    def cancel_job(self, job_id: int) -> bool:
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            job.cancelled = True
            return True


def wait_for_job(
    get_job: Callable[[], EditorTransformJob | None], timeout: float = 5.0
) -> EditorTransformJob | None:
    deadline = time.monotonic() + timeout
    job = get_job()
    while job is not None and job.status in ("queued", "running") and time.monotonic() < deadline:
        time.sleep(0.05)
        job = get_job()
    return job
