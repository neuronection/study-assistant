import json
import re
import time
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import httpx
import structlog
from langchain_core.messages import AIMessage, AIMessageChunk
from sqlalchemy.orm import Session, sessionmaker

from ..core import secrets
from ..domain.models import AiModel, Provider
from .chat_models import (
    build_chat_model,
    chat_native_schemas,
    reasoning_from_message,
    stream_message_chunks,
    structured_output_supported,
    text_from_content,
    to_langchain_messages,
    usage_from_message,
)
from .structured import dump_structured
from .transcribe import (
    TranscriptionResult,
    TranscriptionUnsupported,
    transcribe_with,
)
from .types import (
    ImagePart as ImagePart,
)
from .types import (
    Message as Message,
)
from .types import (
    ResolvedModel as ResolvedModel,
)
from .types import (
    StreamChunk as StreamChunk,
)
from .types import (
    TextPart as TextPart,
)
from .types import Usage, UsageHolder

logger = structlog.get_logger(__name__)


class TaskUnassigned(RuntimeError):
    def __init__(self, task: str) -> None:
        super().__init__(
            f"task '{task}' is unassigned — connect a provider and assign a model in Settings"
        )
        self.task = task


class ProviderError(RuntimeError):
    def __init__(self, resolved: ResolvedModel, reason: str) -> None:
        auth_hint = (
            " — check the API key in Settings → Providers"
            if "401" in reason or "403" in reason
            else ""
        )
        super().__init__(
            f"provider request for model '{resolved.label}' failed: {reason}"
            f"{auth_hint}"
        )
        self.model_label = resolved.label


_STATUS_RE = re.compile(r"\b([45]\d\d)\b")


def _error_status(error: BaseException) -> int | None:
    status = getattr(error, "status_code", None)
    if isinstance(status, int):
        return status
    match = _STATUS_RE.search(str(error))
    return int(match.group(1)) if match else None


def _provider_failure(resolved: ResolvedModel, error: Exception) -> ProviderError:
    status = getattr(error, "status_code", None)
    if isinstance(status, int):
        body = str(error).replace("\n", " ")[:200]
        reason = f"HTTP {status} {body}".strip()
    else:
        root: BaseException = error
        while root.__cause__ is not None:
            root = root.__cause__
        if root is not error:
            reason = f"{type(root).__name__}: {root}"
        elif (found := _error_status(error)) is not None:
            reason = f"HTTP {found} {str(error)[:200]}".strip()
        else:
            reason = f"{type(error).__name__}: {error}"
    return ProviderError(resolved, reason)


def is_transient_error(error: BaseException) -> bool:
    status = _error_status(error)
    if status is not None:
        return status >= 500 or status == 429
    cause: BaseException | None = error
    while cause is not None:
        if isinstance(cause, httpx.HTTPError):
            return True
        cause = cause.__cause__
    return False


class BudgetExceeded(RuntimeError):
    def __init__(self, task: str, spent: float, cap: float) -> None:
        super().__init__(
            f"monthly budget for task '{task}' exceeded: ${spent:.2f} spent of "
            f"${cap:.2f} cap — raise the cap in Settings → Tasks"
        )
        self.task = task
        self.spent = spent
        self.cap = cap


_CACHED_TASK_NAMES = frozenset({"chat"})
CACHE_READ_RATE = 0.1


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _resolve_model(session: Session, model_id: int) -> tuple[AiModel, Provider]:
    model = session.get(AiModel, model_id)
    if model is None:
        raise TaskUnassigned("model-missing")
    provider = session.get(Provider, model.provider_id)
    if provider is None or not provider.enabled:
        raise TaskUnassigned(model.external_id)
    return model, provider


class LLMGateway:
    def __init__(
        self,
        session_factory: sessionmaker[Session] | None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 180.0,
        retry_attempts: int = 2,
        retry_wait: float = 0.5,
    ) -> None:
        self._session_factory = session_factory
        self._transport = transport
        self._timeout = timeout
        self._retry_attempts = max(1, retry_attempts)
        self._retry_wait = retry_wait

    def _check_budget(self, task: str) -> None:
        if self._session_factory is None:
            return
        from datetime import UTC, datetime

        from sqlalchemy import func, select

        from ..domain.models import AiInteraction, TaskAssignment

        month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        with self._session_factory() as session:
            assignment = session.get(TaskAssignment, task)
            cap = ((assignment.params or {}) if assignment else {}).get("monthly_cap_usd")
            if cap is None:
                return
            spent = (
                session.execute(
                    select(func.coalesce(func.sum(AiInteraction.cost_usd), 0.0)).where(
                        AiInteraction.context_type == "gateway",
                        AiInteraction.task == task,
                        AiInteraction.created_at >= month_start,
                    )
                ).scalar_one()
                or 0.0
            )
            if spent >= float(cap):
                raise BudgetExceeded(task, float(spent), float(cap))

    def _ledger(
        self,
        task: str,
        resolved: ResolvedModel | None,
        prompt: str,
        output: str,
        latency_ms: int,
        usage: Usage | None = None,
    ) -> None:
        if self._session_factory is None:
            return
        from ..domain.models import AiInteraction

        tokens_in = usage.tokens_in if usage is not None else _estimate_tokens(prompt)
        tokens_out = usage.tokens_out if usage is not None else _estimate_tokens(output)
        cached_in = usage.cache_read if usage is not None else 0
        cost: float | None = None
        if resolved is not None and resolved.cost_in is not None:
            rate_out = resolved.cost_out if resolved.cost_out is not None else 0.0
            billed_in = max(0, tokens_in - cached_in) * resolved.cost_in
            billed_cache = cached_in * resolved.cost_in * CACHE_READ_RATE
            cost = round(
                (billed_in + billed_cache) / 1_000_000
                + tokens_out / 1_000_000 * rate_out,
                6,
            )
        try:
            with self._session_factory() as session:
                session.add(
                    AiInteraction(
                        context_type="gateway",
                        task=task,
                        model=resolved.label if resolved else None,
                        input_tokens=tokens_in,
                        output_tokens=tokens_out,
                        cached_input_tokens=cached_in or None,
                        cost_usd=cost,
                        latency_ms=latency_ms,
                    )
                )
                session.commit()
        except Exception as error:
            logger.warning(
                "ai_interaction_ledger_failed",
                task=task,
                error=str(error)[:300],
            )

    def _resolve_chain(
        self, task: str, model: ResolvedModel | None, course_id: int | None = None
    ) -> list[ResolvedModel]:
        if model is not None:
            return [model]
        if self._session_factory is None:
            raise TaskUnassigned(task)
        with self._session_factory() as session:
            from ..ai.tasks import TASKS_BY_NAME
            from ..domain.models import (
                CourseDefaultTaskAssignment,
                CourseTaskAssignment,
                DefaultTaskAssignment,
                TaskAssignment,
            )

            assignment = session.get(TaskAssignment, task)
            task_def = TASKS_BY_NAME.get(task)
            default: DefaultTaskAssignment | None = None
            if task_def is not None:
                default = session.get(DefaultTaskAssignment, task_def.requires)

            global_model_id = default.model_id if default is not None else None
            global_fallback_id = (
                default.fallback_model_id if default is not None else None
            )
            if assignment is not None:
                if assignment.model_id is not None:
                    global_model_id = assignment.model_id
                if assignment.fallback_model_id is not None:
                    global_fallback_id = assignment.fallback_model_id

            course_default: CourseDefaultTaskAssignment | None = None
            if course_id is not None and task_def is not None:
                course_default = session.get(
                    CourseDefaultTaskAssignment,
                    (course_id, task_def.requires),
                )
                if course_default is not None:
                    if course_default.model_id is not None:
                        global_model_id = course_default.model_id
                    if course_default.fallback_model_id is not None:
                        global_fallback_id = course_default.fallback_model_id

            if course_id is not None:
                course_override = session.get(CourseTaskAssignment, (course_id, task))
                if course_override is not None:
                    if course_override.model_id is not None:
                        global_model_id = course_override.model_id
                    if course_override.fallback_model_id is not None:
                        global_fallback_id = course_override.fallback_model_id

            model_id = global_model_id
            fallback_id = global_fallback_id
            candidates = (model_id, fallback_id)
            chain: list[ResolvedModel] = []
            for model_id in candidates:
                if model_id is None:
                    continue
                try:
                    db_model, provider = _resolve_model(session, model_id)
                except TaskUnassigned:
                    continue
                chain.append(
                    ResolvedModel(
                        provider_id=provider.id,
                        provider_type=provider.type,
                        base_url=provider.base_url,
                        external_id=db_model.external_id,
                        label=db_model.label,
                        caps=list(db_model.caps or []),
                        api_key=secrets.get_secret(provider.keyring_ref),
                        cost_in=db_model.cost_in,
                        cost_out=db_model.cost_out,
                        reasoning_effort=db_model.reasoning_effort,
                        temperature=db_model.temperature,
                        max_tokens=db_model.max_tokens,
                    )
                )
            if chain:
                return chain
        raise TaskUnassigned(task)

    def resolve(self, task: str, course_id: int | None = None) -> ResolvedModel:
        return self._resolve_chain(task, None, course_id)[0]

    def _sleep_backoff(self, attempt: int) -> None:
        time.sleep(min(self._retry_wait * (2**attempt), 5.0))

    def _invoke_model(
        self, resolved: ResolvedModel, messages: list[Message]
    ) -> tuple[str, Usage | None]:
        chat_model = build_chat_model(resolved, self._transport, self._timeout)
        langchain_messages = to_langchain_messages(messages)
        response: AIMessage | None = None
        for attempt in range(self._retry_attempts):
            try:
                response = chat_model.invoke(langchain_messages)
                break
            except Exception as error:
                if attempt + 1 >= self._retry_attempts or not is_transient_error(error):
                    raise _provider_failure(resolved, error) from error
                self._sleep_backoff(attempt)
        if response is None:
            raise _provider_failure(resolved, RuntimeError("no response"))
        return text_from_content(response.content).strip(), usage_from_message(response)

    def generate(
        self,
        task: str,
        messages: list[Message],
        model: ResolvedModel | None = None,
        course_id: int | None = None,
    ) -> str:
        self._check_budget(task)
        chain = self._resolve_chain(task, model, course_id)
        started = time.monotonic()
        last_error: ProviderError | None = None
        for resolved in chain:
            try:
                output, usage = self._invoke_model(resolved, messages)
            except ProviderError as error:
                last_error = error
                continue
            self._ledger(
                task,
                resolved,
                _flatten(messages),
                output,
                int((time.monotonic() - started) * 1000),
                usage=usage,
            )
            return output
        assert last_error is not None
        raise last_error

    def generate_structured(
        self,
        task: str,
        messages: list[Message],
        schema: type[Any],
        course_id: int | None = None,
    ) -> dict[str, Any] | None:

        self._check_budget(task)
        started = time.monotonic()
        last_error: ProviderError | None = None
        try:
            chain = self._resolve_chain(task, None, course_id)
        except TaskUnassigned:
            return None
        for resolved in chain:
            if "tools" not in resolved.caps:
                continue
            try:
                chat_model = build_chat_model(resolved, self._transport, self._timeout)
                if not structured_output_supported(chat_model):
                    continue
                structured = chat_model.with_structured_output(schema, include_raw=True)
                langchain_messages = to_langchain_messages(messages)
                result: Any = None
                for attempt in range(self._retry_attempts):
                    try:
                        result = structured.invoke(langchain_messages)
                        break
                    except Exception as error:
                        if (
                            attempt + 1 >= self._retry_attempts
                            or not is_transient_error(error)
                        ):
                            raise _provider_failure(resolved, error) from error
                        self._sleep_backoff(attempt)
                if not isinstance(result, dict) or result.get("parsed") is None:
                    return None
                raw = result.get("raw")
                usage = usage_from_message(raw) if isinstance(raw, AIMessage) else None
                data = dump_structured(result["parsed"])
                self._ledger(
                    task,
                    resolved,
                    _flatten(messages),
                    json.dumps(data, ensure_ascii=False)[:2000],
                    int((time.monotonic() - started) * 1000),
                    usage=usage,
                )
                return data
            except ProviderError as error:
                if _is_schema_unsupported(error):
                    return None
                last_error = error
                continue
        if last_error is not None:
            raise last_error
        return None

    def transcribe(
        self,
        data: bytes,
        mime: str,
        *,
        language: str | None = None,
        instruction: str | None = None,
        task: str = "transcribe",
        model: ResolvedModel | None = None,
        course_id: int | None = None,
    ) -> TranscriptionResult:
        self._check_budget(task)
        chain = self._resolve_chain(task, model, course_id)
        started = time.monotonic()
        last_error: ProviderError | None = None
        for resolved in chain:
            try:
                text, usage = self._invoke_transcription(
                    resolved, data, mime, language, instruction
                )
            except ProviderError as error:
                last_error = error
                continue
            self._ledger(
                task,
                resolved,
                f"[audio {len(data)} bytes {mime or 'unknown'}]",
                text,
                int((time.monotonic() - started) * 1000),
                usage=usage,
            )
            return TranscriptionResult(text=text, model=resolved.label)
        assert last_error is not None
        raise last_error

    def _invoke_transcription(
        self,
        resolved: ResolvedModel,
        data: bytes,
        mime: str,
        language: str | None,
        instruction: str | None,
    ) -> tuple[str, Usage | None]:
        for attempt in range(self._retry_attempts):
            try:
                with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                    return transcribe_with(
                        client, resolved, data, mime, language, instruction
                    )
            except TranscriptionUnsupported as error:
                raise ProviderError(resolved, str(error)) from error
            except Exception as error:
                if attempt + 1 >= self._retry_attempts or not is_transient_error(error):
                    raise _provider_failure(resolved, error) from error
                self._sleep_backoff(attempt)
        raise _provider_failure(resolved, RuntimeError("no response"))

    def stream(
        self,
        task: str,
        messages: list[Message],
        model: ResolvedModel | None = None,
        course_id: int | None = None,
    ) -> Iterator[str]:
        for chunk in self.stream_events(task, messages, model, course_id):
            if chunk.kind == "text":
                yield chunk.text

    def _stream_model(
        self,
        resolved: ResolvedModel,
        messages: list[Message],
        holder: UsageHolder,
        cache_prefix: bool = False,
    ) -> Iterator[StreamChunk]:
        chat_model = build_chat_model(resolved, self._transport, self._timeout)
        if "tools" in resolved.caps:
            streamable = chat_model.bind_tools(chat_native_schemas())
        else:
            streamable = chat_model
        langchain_messages = to_langchain_messages(
            messages,
            cache_prefix=cache_prefix and resolved.provider_type == "anthropic",
        )
        try:
            chunks: Iterator[AIMessage] | None = None
            first: AIMessage | None = None
            for attempt in range(self._retry_attempts):
                try:
                    chunks = stream_message_chunks(streamable, langchain_messages)
                    first = next(chunks, None)
                    break
                except Exception as error:
                    if attempt + 1 >= self._retry_attempts or not is_transient_error(error):
                        raise _provider_failure(resolved, error) from error
                    self._sleep_backoff(attempt)
            if chunks is not None:
                merged: AIMessage | None = None
                if first is not None:
                    merged = first
                    yield from _chunk_events(first, holder)
                for chunk in chunks:
                    if (
                        merged is not None
                        and isinstance(merged, AIMessageChunk)
                        and isinstance(chunk, AIMessageChunk)
                    ):
                        merged = merged + chunk
                    yield from _chunk_events(chunk, holder)
                if merged is not None:
                    yield from _tool_call_events(merged)
        except ProviderError:
            raise
        except Exception as error:
            raise _provider_failure(resolved, error) from error

    def stream_events(
        self,
        task: str,
        messages: list[Message],
        model: ResolvedModel | None = None,
        course_id: int | None = None,
    ) -> Iterator[StreamChunk]:
        self._check_budget(task)
        chain = self._resolve_chain(task, model, course_id)
        started = time.monotonic()
        buffer: list[str] = []
        last_error: ProviderError | None = None
        completed: ResolvedModel | None = None
        active: ResolvedModel | None = None
        usage: Usage | None = None
        try:
            for resolved in chain:
                holder = UsageHolder()
                active = resolved
                emitted = False
                try:
                    for chunk in self._stream_model(
                        resolved,
                        messages,
                        holder,
                        cache_prefix=task in _CACHED_TASK_NAMES,
                    ):
                        if chunk.kind == "text":
                            buffer.append(chunk.text)
                        emitted = True
                        yield chunk
                except ProviderError as error:
                    if emitted:
                        raise
                    last_error = error
                    continue
                completed = resolved
                usage = holder.usage
                return
        finally:
            self._ledger(
                task,
                completed if completed is not None else active,
                _flatten(messages),
                "".join(buffer),
                int((time.monotonic() - started) * 1000),
                usage=usage,
            )
        if last_error is not None:
            raise last_error


def _is_schema_unsupported(error: ProviderError) -> bool:
    message = str(error).lower()
    status = _error_status(error)
    if status is not None and status not in (400, 404, 415, 422):
        return False
    return any(
        token in message
        for token in (
            "response_format",
            "json_schema",
            "schema",
            "structured output",
            "function calling",
            "not supported",
            "unsupported",
            "invalid parameter",
        )
    )


def is_tool_unsupported_error(error: ProviderError) -> bool:
    return _is_schema_unsupported(error)


def _chunk_events(chunk: AIMessage, holder: UsageHolder) -> Iterator[StreamChunk]:
    usage = usage_from_message(chunk)
    if usage is not None:
        holder.usage = usage
    reasoning = reasoning_from_message(chunk)
    if reasoning:
        yield StreamChunk("reasoning", reasoning)
    text = text_from_content(chunk.content)
    if text:
        yield StreamChunk("text", text)


def _tool_call_events(message: AIMessage) -> Iterator[StreamChunk]:
    for call in message.tool_calls:
        name = call.get("name")
        arguments = call.get("args")
        call_id = call.get("id")
        if not isinstance(name, str) or not isinstance(arguments, dict):
            continue
        yield StreamChunk(
            "tool_call",
            json.dumps(
                {"id": call_id, "name": name, "arguments": arguments},
                ensure_ascii=False,
            ),
        )


def _flatten(messages: list[Message]) -> str:
    parts: list[str] = []
    for message in messages:
        if isinstance(message.content, str):
            parts.append(message.content)
        else:
            for part in message.content:
                parts.append(getattr(part, "text", ""))
    return "\n".join(parts)


def new_id() -> str:
    return uuid4().hex
