"""WS adapter for the chat-turn graph (plan 10 Phase 5, §5.3).

Runs the graph on the process event loop (the checkpointer's aiosqlite
connection is bound there) while the `chat_turn` job handler blocks its
worker thread, and consumes the raw stable streaming API
`astream(stream_mode=["updates", "messages"])` (integrator ruling 2026-09-04;
`astream_events(version="v3")` stays beta on the pinned langgraph — swapping
it in later is a one-file change confined to this adapter):

- `messages` tuples (`AIMessageChunk`, metadata) → `stream_delta` WS events
  (text and reasoning deltas in exact arrival order, tool lines filtered by
  the same line grammar as the legacy engine, 30 ms flush throttle),
- `updates` (per-node state deltas) → round-boundary flush of the pending
  delta line, capture of the `finalize` node's persisted event payload, and
  the reserved `__interrupt__` mapping point,
- the captured payload is emitted after the stream ends so token deltas
  always precede `assistant_message` (and `stream_interrupted`) on the wire.

The external WS EventBus contract (`stream_start`, `phase`, `stream_delta`,
`tool_call`, `stream_interrupted`, `assistant_message`, `turn_error`) and the
AG-UI mapping on top of it are unchanged. `thread_id` is the chat session id.
"""

import asyncio
import time
from typing import Any

import structlog
from langchain_core.messages import AIMessageChunk

from ...core.events import EventBus
from ...domain.models import ChatMessage, ChatSession
from ...services.platform.chat import ChatError, ChatService, Emitter
from ..chat_models import reasoning_from_message, text_from_content
from ..gateway import LLMGateway
from ..tools import TOOL_LINE_RE
from .chat_turn import ChatTurnDeps, build_chat_turn_graph

logger = structlog.get_logger(__name__)

STREAM_DELTA_INTERVAL = 0.03
RECURSION_LIMIT = 60


class _DeltaPump:
    """Legacy-faithful delta throttling and tool-line filtering."""

    def __init__(self, emit: Emitter, started: float) -> None:
        self._emit = emit
        self._started = started
        self._text_buf: list[str] = []
        self._reason_buf: list[str] = []
        self._pending_line = ""
        self._last_flush = time.monotonic()

    def _elapsed_ms(self) -> int:
        return int((time.monotonic() - self._started) * 1000)

    def on_text(self, text: str) -> None:
        self._pending_line += text
        while "\n" in self._pending_line:
            line, self._pending_line = self._pending_line.split("\n", 1)
            if not TOOL_LINE_RE.match(line):
                self._text_buf.append(line + "\n")
        self._maybe_flush()

    def on_reasoning(self, text: str) -> None:
        self._reason_buf.append(text)
        self._maybe_flush()

    def _maybe_flush(self) -> None:
        if time.monotonic() - self._last_flush >= STREAM_DELTA_INTERVAL:
            self.flush()

    def flush(self) -> None:
        if self._reason_buf:
            self._emit(
                {
                    "type": "stream_delta",
                    "delta": "".join(self._reason_buf),
                    "kind": "reasoning",
                    "elapsed_ms": self._elapsed_ms(),
                }
            )
            self._reason_buf.clear()
        if self._text_buf:
            self._emit(
                {
                    "type": "stream_delta",
                    "delta": "".join(self._text_buf),
                    "elapsed_ms": self._elapsed_ms(),
                }
            )
            self._text_buf.clear()
        self._last_flush = time.monotonic()

    def flush_round_end(self) -> None:
        if self._pending_line and not TOOL_LINE_RE.match(self._pending_line):
            self._text_buf.append(self._pending_line)
        self._pending_line = ""
        self.flush()


class ChatTurnEngine:
    """Blocking facade the `chat_turn` job handler calls from its thread."""

    def __init__(self, checkpointer: Any, bus: EventBus) -> None:
        self._checkpointer = checkpointer
        self._bus = bus

    def run(
        self,
        session: Any,
        service: ChatService,
        gateway: LLMGateway,
        chat_session: ChatSession,
        user_message: ChatMessage,
        emit: Emitter,
        stop: asyncio.Event | None = None,
    ) -> ChatMessage:
        loop = self._bus.loop
        if loop is None or loop.is_closed():
            raise ChatError("graph engine requires the running app event loop")
        future = asyncio.run_coroutine_threadsafe(
            self._run(session, service, gateway, chat_session, user_message, emit, stop),
            loop,
        )
        return future.result()

    async def _run(
        self,
        session: Any,
        service: ChatService,
        gateway: LLMGateway,
        chat_session: ChatSession,
        user_message: ChatMessage,
        emit: Emitter,
        stop: Any,
    ) -> ChatMessage:
        deps = ChatTurnDeps(service, gateway, emit, stop, chat_session, user_message)
        graph = build_chat_turn_graph(deps, self._checkpointer)
        config: dict[str, Any] = {
            "configurable": {"thread_id": str(chat_session.id)},
            "recursion_limit": RECURSION_LIMIT,
        }
        pump = _DeltaPump(emit, deps.started)
        final_events: list[dict[str, Any]] = []
        message_id: int | None = None
        try:
            async for mode, payload in graph.astream(
                {"session_id": chat_session.id},
                config,
                stream_mode=["updates", "messages"],
            ):
                if mode == "messages":
                    self._on_messages_chunk(pump, payload)
                elif mode == "updates":
                    pump.flush_round_end()
                    update = payload.get("finalize") if isinstance(payload, dict) else None
                    if isinstance(update, dict):
                        captured = update.get("final_events") or []
                        final_events = list(captured)
                        message_id = update.get("message_id")
                    if isinstance(payload, dict) and "__interrupt__" in payload:
                        logger.info(
                            "chat_turn_interrupted",
                            session_id=chat_session.id,
                            thread_id=str(chat_session.id),
                        )
        finally:
            pump.flush()
        for event in final_events:
            emit(event)
        if message_id is None:
            raise ChatError("graph turn produced no message")
        message: ChatMessage | None = session.get(ChatMessage, int(message_id))
        if message is None:
            raise ChatError("graph turn message vanished")
        return message

    def _on_messages_chunk(self, pump: _DeltaPump, payload: Any) -> None:
        chunk = payload[0] if isinstance(payload, (list, tuple)) and payload else payload
        if not isinstance(chunk, AIMessageChunk):
            return
        reasoning = reasoning_from_message(chunk)
        if reasoning:
            pump.on_reasoning(reasoning)
        text = text_from_content(chunk.content)
        if text:
            pump.on_text(text)
