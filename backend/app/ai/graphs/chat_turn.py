"""Chat-turn graph (plan 10 Phase 5, ADR-0008).

Mirrors `ChatService.answer_streaming` as a checkpointed StateGraph:

    retrieve → contract_guard → agent_round ⇄ (tool rounds) → validate_repair → finalize

A custom StateGraph instead of `create_agent`: the turn interleaves two tool
modes (native `.bind_tools()` plus the degraded prompt-line grammar), enforces
per-kind budgets (math 2 / READ 3 / STATE 3 / resource 5 per turn), emits
legacy WS progress events, and runs the deterministic contract repair loop —
none of which agent middleware can host (the plan-10 §5.2 decision point).

Nodes call the gateway only for model I/O; retrieval, tools, contracts, and
persistence are the same plain code the legacy engine uses
(`ChatService.prepare_turn_context` / `prepare_turn_contract` /
`finalize_turn`), so the two engines cannot drift. `stream_start`, `phase`,
and `tool_call` WS events are emitted from nodes through the injected
`Emitter` (legacy-semantic payloads with no LangGraph projection); token
deltas flow through the raw `astream(stream_mode=["updates", "messages"])`
messages mode and are mapped onto `stream_delta` by `chat_turn_adapter`.

Fault tolerance is layered over the gateway's own retries: the graph retries
only raw transport leaks (`httpx.HTTPError`) — `ProviderError` has already
been retried inside the gateway — and each node carries a hang-guard timeout
well above the gateway's per-request limit. Node timeouts require async
nodes, so every node body runs via `asyncio.to_thread` (which also preserves
the callback context that feeds the `messages` stream).
"""

import asyncio
import json
import threading
import time
from collections.abc import Callable
from typing import Any, cast
from uuid import uuid4

import httpx
import structlog
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, TimeoutPolicy
from typing_extensions import TypedDict

from ...domain.models import ChatMessage, ChatSession
from ...mcp_resources import RESOURCE_TOOL_BY_KEYWORD
from ...services.platform.chat import (
    CHAT_TASK,
    MAX_READ_ROUNDS,
    MAX_REPAIR_ROUNDS,
    MAX_RESOURCE_ROUNDS,
    MAX_STATE_ROUNDS,
    MAX_TOOL_ROUNDS,
    ChatService,
    Emitter,
    TurnPrep,
    _native_call_args,
    _tool_result_summary,
    flatten_prompt,
)
from ..chat_models import degrade_native_tools
from ..contracts.contracts import ValidationResult, validate
from ..gateway import LLMGateway, Message, ProviderError, is_tool_unsupported_error
from ..tools import extract_tool_calls, run_tool_line, strip_tool_lines

logger = structlog.get_logger(__name__)

MAX_ROUND_BUDGET = MAX_TOOL_ROUNDS + MAX_READ_ROUNDS + 1
NODE_RUN_TIMEOUT_SEC = 600

STOP_MESSAGE = "generation stopped by user"
DEGRADED = "@degraded"

READISH_TOOLS = frozenset({"READ", "STATE", *RESOURCE_TOOL_BY_KEYWORD})


class ChatTurnState(TypedDict, total=False):
    session_id: int
    attempt: int
    round_index: int
    run_id: str
    model_name: str | None
    prompt_snapshot: str
    tool_log: str
    native_tools: bool
    native_round: list[dict[str, Any]]
    math_rounds: int
    read_used: int
    state_used: int
    resource_used: int
    reads: list[dict[str, Any]]
    tool_calls_seen: list[dict[str, Any]]
    trace_rounds: list[dict[str, Any]]
    reasoning_parts: list[str]
    round_had_tools: bool
    repair_pending: bool
    degraded: bool
    stream_interruption: str | None
    output: str
    feedback_text: str
    validation_ok: bool
    final_tool_calls: list[dict[str, Any]]
    final_events: list[dict[str, Any]]
    message_id: int
    finalized: bool


class ChatTurnDeps:
    """Per-turn collaborators closed over by the node functions."""

    def __init__(
        self,
        service: ChatService,
        gateway: LLMGateway,
        emit: Emitter,
        stop: threading.Event | None,
        chat_session: ChatSession,
        user_message: ChatMessage,
        on_round_stream_end: Callable[[], None] | None = None,
    ) -> None:
        self.service = service
        self.gateway = gateway
        self.emit = emit
        self.stop = stop
        self.chat_session = chat_session
        self.user_message = user_message
        self.started = time.monotonic()
        self.prep: TurnPrep | None = None
        self.validation: ValidationResult | None = None
        self.on_round_stream_end = on_round_stream_end

    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self.started) * 1000)

    def stopped(self) -> bool:
        return self.stop is not None and self.stop.is_set()


def _fresh_round_scope() -> dict[str, Any]:
    return {
        "round_index": 0,
        "tool_log": "",
        "native_round": [],
        "math_rounds": 0,
        "read_used": 0,
        "state_used": 0,
        "resource_used": 0,
        "reads": [],
        "tool_calls_seen": [],
        "round_had_tools": False,
    }


def _retrieve(deps: ChatTurnDeps, _state: ChatTurnState) -> dict[str, Any]:
    prep = deps.service.prepare_turn_context(deps.chat_session, deps.user_message)
    deps.prep = prep
    return {
        "session_id": deps.chat_session.id,
        "attempt": 0,
        "run_id": uuid4().hex,
        "model_name": None,
        "prompt_snapshot": "",
        "native_tools": deps.service.native_tools_enabled(deps.chat_session.course_id),
        "reasoning_parts": [],
        "trace_rounds": [],
        "degraded": False,
        "stream_interruption": None,
        "output": "",
        "feedback_text": "",
        "validation_ok": False,
        "final_tool_calls": [],
        "final_events": [],
        "finalized": False,
        **_fresh_round_scope(),
    }


def _contract_guard(deps: ChatTurnDeps, _state: ChatTurnState) -> dict[str, Any]:
    assert deps.prep is not None
    deps.service.prepare_turn_contract(deps.chat_session, deps.prep)
    return {}


def _round_messages(
    deps: ChatTurnDeps, prep: TurnPrep, state: ChatTurnState
) -> list[Message]:
    attempt = state["attempt"]
    feedback = state["feedback_text"] if attempt > 0 else None
    if state["native_tools"]:
        base = deps.service._build_messages(
            prep.history,
            deps.user_message,
            prep.sources_block,
            "",
            feedback,
            prep.system_base,
            guard_rule_text=prep.guard_rule_text,
            proposals_enabled=prep.proposals_enabled,
            dismissal_note=prep.dismissal_note,
            native_tools=True,
        )
        native_round = [
            Message(
                role=entry["role"],
                content=entry["content"],
                tool_calls=tuple(entry.get("tool_calls") or ()),
                tool_call_id=entry.get("tool_call_id"),
            )
            for entry in state["native_round"]
        ]
        return [*base, *native_round]
    return deps.service._build_messages(
        prep.history,
        deps.user_message,
        prep.sources_block,
        state["tool_log"],
        feedback,
        prep.system_base,
        guard_rule_text=prep.guard_rule_text,
        proposals_enabled=prep.proposals_enabled,
        dismissal_note=prep.dismissal_note,
    )


def _consume_stream(
    deps: ChatTurnDeps, state: ChatTurnState, messages: list[Message]
) -> tuple[list[str], list[dict[str, Any]], list[str], str | None]:
    buffer: list[str] = []
    native_raw: list[dict[str, Any]] = []
    reasoning: list[str] = []
    try:
        for part in deps.gateway.stream_events(
            CHAT_TASK, messages, course_id=deps.chat_session.course_id
        ):
            if deps.stopped():
                return buffer, native_raw, reasoning, STOP_MESSAGE
            if part.kind == "tool_call":
                native_raw.append(json.loads(part.text))
            elif part.kind == "reasoning":
                reasoning.append(part.text)
            else:
                buffer.append(part.text)
    except ProviderError as error:
        if buffer:
            return buffer, native_raw, reasoning, str(error)[:200]
        if state["native_tools"] and is_tool_unsupported_error(error):
            degrade_native_tools(
                deps.gateway.resolve(CHAT_TASK, deps.chat_session.course_id)
            )
            return buffer, native_raw, reasoning, DEGRADED
        raise
    if deps.on_round_stream_end is not None:
        deps.on_round_stream_end()
    return buffer, native_raw, reasoning, None


def _tool_entry(
    deps: ChatTurnDeps,
    kind: str,
    argument: str,
    phase: str,
    tool_start_ms: int,
    content: str,
    result_summary: str | None,
    title: str | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": kind,
        "argument": argument,
        "phase": phase,
        "status": "done",
        "start_ms": tool_start_ms,
        "duration_ms": deps.elapsed_ms() - tool_start_ms,
    }
    if result_summary:
        entry["result"] = result_summary
    if title is not None:
        entry["title"] = title
    return entry


def _execute_tools(
    deps: ChatTurnDeps,
    state: ChatTurnState,
    tool_calls: list[tuple[str, str]],
    native_raw: list[dict[str, Any]],
    phase: str,
) -> dict[str, Any]:
    assert deps.prep is not None
    registry = deps.prep.registry
    results: list[str] = []
    executed_math = False
    read_used = state["read_used"]
    state_used = state["state_used"]
    resource_used = state["resource_used"]
    reads = list(state["reads"])
    tool_calls_seen = list(state["tool_calls_seen"])
    for kind, argument in tool_calls:
        tool_start_ms = deps.elapsed_ms()
        tool_phase = (
            "reading"
            if kind in READISH_TOOLS
            else "plotting"
            if kind == "PLOT"
            else "computing"
        )
        deps.emit({"type": "phase", "phase": tool_phase, "elapsed_ms": tool_start_ms})
        if kind == "READ":
            if read_used >= MAX_READ_ROUNDS:
                results.append(
                    f"READ {argument} -> error: READ budget for this "
                    "turn is spent; answer from what you already have"
                )
                continue
            read_used += 1
            content = deps.service._read_handle(argument, registry)
            results.append(f"READ {argument} -> {content}")
            entry = registry.get(argument)
            if entry is not None and not (
                content.startswith("error:") or content.startswith("note:")
            ):
                reads.append(
                    {
                        "ref": entry.ref,
                        "kind": entry.kind,
                        "id": entry.id,
                        "title": entry.title,
                        "course_id": entry.course_id,
                        "chars": len(content),
                    }
                )
            tool_calls_seen.append(
                _tool_entry(
                    deps,
                    "READ",
                    argument,
                    phase,
                    tool_start_ms,
                    content,
                    _tool_result_summary("READ", content),
                    title=entry.title if entry is not None else None,
                )
            )
            deps.emit({"type": "tool_call", **tool_calls_seen[-1]})
        elif kind == "STATE":
            if state_used >= MAX_STATE_ROUNDS:
                results.append(
                    f"STATE {argument} -> error: STATE budget for this "
                    "turn is spent; answer from what you already have"
                )
                continue
            state_used += 1
            content = deps.service._read_widget_state(deps.chat_session, argument)
            results.append(f"STATE {argument} -> {content}")
            tool_calls_seen.append(
                _tool_entry(
                    deps,
                    "STATE",
                    argument,
                    phase,
                    tool_start_ms,
                    content,
                    _tool_result_summary("STATE", content),
                )
            )
            deps.emit({"type": "tool_call", **tool_calls_seen[-1]})
        elif kind in RESOURCE_TOOL_BY_KEYWORD:
            if resource_used >= MAX_RESOURCE_ROUNDS:
                results.append(
                    f"{kind} {argument} -> error: resource tool budget "
                    "for this turn is spent; answer from what you already have"
                )
                continue
            resource_used += 1
            content = deps.service._run_resource_tool(
                kind, argument, deps.chat_session, registry
            )
            results.append(f"{kind} {argument} -> {content}")
            tool_calls_seen.append(
                _tool_entry(
                    deps,
                    kind,
                    argument,
                    phase,
                    tool_start_ms,
                    content,
                    _tool_result_summary(kind, content),
                )
            )
            deps.emit({"type": "tool_call", **tool_calls_seen[-1]})
        else:
            if state["math_rounds"] >= MAX_TOOL_ROUNDS:
                results.append(
                    f"{kind} {argument} -> error: math tool budget "
                    "for this turn is spent"
                )
                continue
            executed_math = True
            result = run_tool_line(kind, argument)
            results.append(f"{kind} {argument} -> {result}")
            tool_calls_seen.append(
                _tool_entry(
                    deps,
                    kind,
                    argument,
                    phase,
                    tool_start_ms,
                    result,
                    _tool_result_summary(kind, result),
                )
            )
            deps.emit({"type": "tool_call", **tool_calls_seen[-1]})
    updates: dict[str, Any] = {
        "read_used": read_used,
        "state_used": state_used,
        "resource_used": resource_used,
        "reads": reads,
        "tool_calls_seen": tool_calls_seen,
        "math_rounds": state["math_rounds"] + (1 if executed_math else 0),
    }
    if state["native_tools"]:
        native_round = list(state["native_round"])
        native_round.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": tuple(
                    {
                        "id": call.get("id"),
                        "name": call["name"],
                        "args": call.get("arguments") or {},
                    }
                    for call in native_raw
                ),
            }
        )
        for index, call in enumerate(native_raw):
            native_round.append(
                {
                    "role": "tool",
                    "content": results[index].partition(" -> ")[2],
                    "tool_call_id": call.get("id") or "",
                }
            )
        updates["native_round"] = native_round
    else:
        results_text = "\n".join(results)
        updates["tool_log"] = (
            f"{state['tool_log']}\n{results_text}"
            if state["tool_log"]
            else results_text
        )
    return updates


def _agent_round(deps: ChatTurnDeps, state: ChatTurnState) -> dict[str, Any]:
    prep = deps.prep
    assert prep is not None
    if state.get("degraded"):
        reset: dict[str, Any] = dict(state)
        reset.update(_fresh_round_scope())
        reset["attempt"] = state["attempt"] + 1
        reset["native_tools"] = False
        reset["degraded"] = False
        state = cast(ChatTurnState, reset)
    if deps.stopped():
        return {"stream_interruption": STOP_MESSAGE}
    round_index = state["round_index"]
    attempt = state["attempt"]
    round_start_ms = deps.elapsed_ms()
    if round_index == 0:
        deps.emit(
            {
                "type": "stream_start",
                "run_id": state["run_id"],
                "elapsed_ms": round_start_ms,
            }
        )
    round_phase = "repairing" if attempt > 0 else "thinking"
    deps.emit({"type": "phase", "phase": round_phase, "elapsed_ms": round_start_ms})
    messages = _round_messages(deps, prep, state)
    buffer, native_raw, reasoning, interruption = _consume_stream(
        deps, state, messages
    )
    trace_rounds = list(state["trace_rounds"])
    reasoning_parts = list(state["reasoning_parts"])
    reasoning_parts.extend(reasoning)
    if interruption == DEGRADED:
        return {"degraded": True, "reasoning_parts": reasoning_parts}
    output = "".join(buffer)
    round_duration_ms = deps.elapsed_ms() - round_start_ms
    logger.info(
        "chat_turn_timing",
        session_id=deps.chat_session.id,
        phase=round_phase,
        duration_ms=round_duration_ms,
    )
    trace_rounds.append(
        {
            "index": len(trace_rounds),
            "streamed": True,
            "start_ms": round_start_ms,
            "duration_ms": round_duration_ms,
            "phase": round_phase,
        }
    )
    try:
        model_name: str | None = deps.gateway.resolve(
            CHAT_TASK, deps.chat_session.course_id
        ).label
    except Exception:
        model_name = None
    base_updates: dict[str, Any] = {
        "output": output,
        "trace_rounds": trace_rounds,
        "reasoning_parts": reasoning_parts,
        "model_name": model_name,
        "prompt_snapshot": flatten_prompt(messages),
        "stream_interruption": interruption,
    }
    if interruption is not None:
        return base_updates
    if state["native_tools"]:
        tool_calls = [
            (call["name"], _native_call_args(call["name"], call.get("arguments") or {}))
            for call in native_raw
        ]
    else:
        tool_calls = extract_tool_calls(output)
    if not tool_calls:
        return {**base_updates, "round_had_tools": False}
    call_kinds = {kind for kind, _argument in tool_calls}
    if call_kinds and call_kinds <= READISH_TOOLS:
        phase = "read"
    elif call_kinds & READISH_TOOLS:
        phase = "mixed"
    else:
        phase = "math"
    tool_updates = _execute_tools(deps, state, tool_calls, native_raw, phase)
    return {
        **base_updates,
        **tool_updates,
        "round_index": round_index + 1,
        "round_had_tools": True,
    }


def _validate_repair(deps: ChatTurnDeps, state: ChatTurnState) -> dict[str, Any]:
    assert deps.prep is not None
    output = strip_tool_lines(state["output"])
    if state.get("stream_interruption") is not None:
        return {"output": output}
    validation = validate(output, deps.prep.contract, deps.prep.context)
    deps.validation = validation
    if validation.ok:
        return {
            "output": output,
            "validation_ok": True,
            "repair_pending": False,
            "final_tool_calls": list(state["tool_calls_seen"]),
        }
    updates: dict[str, Any] = {
        "output": output,
        "feedback_text": validation.feedback(),
        "repair_pending": state["attempt"] < MAX_REPAIR_ROUNDS,
    }
    if state["attempt"] < MAX_REPAIR_ROUNDS:
        return {**updates, "attempt": state["attempt"] + 1, **_fresh_round_scope()}
    return updates


def _finalize(deps: ChatTurnDeps, state: ChatTurnState) -> dict[str, Any]:
    assert deps.prep is not None
    captured: list[dict[str, Any]] = []
    message = deps.service.finalize_turn(
        deps.chat_session,
        deps.user_message,
        deps.prep,
        started=deps.started,
        run_id=state["run_id"],
        model_name=state["model_name"],
        prompt_snapshot=state["prompt_snapshot"],
        final_output=state["output"],
        final_tool_calls=state["final_tool_calls"],
        reads=state["reads"],
        repair_rounds=state["attempt"],
        trace_rounds=state["trace_rounds"],
        reasoning_parts=state["reasoning_parts"],
        stream_interruption=state.get("stream_interruption"),
        validation=deps.validation,
        emit=captured.append,
    )
    return {"finalized": True, "final_events": captured, "message_id": message.id}


class ChatTurnNodes:
    """Async node adapters: timeouts require async nodes; `asyncio.to_thread`
    keeps blocking work off the loop and preserves the callback context that
    feeds the `messages` stream."""

    def __init__(self, deps: ChatTurnDeps) -> None:
        self._deps = deps

    async def retrieve(self, state: ChatTurnState) -> dict[str, Any]:
        return await asyncio.to_thread(_retrieve, self._deps, state)

    async def contract_guard(self, state: ChatTurnState) -> dict[str, Any]:
        return await asyncio.to_thread(_contract_guard, self._deps, state)

    async def agent_round(self, state: ChatTurnState) -> dict[str, Any]:
        return await asyncio.to_thread(_agent_round, self._deps, state)

    async def validate_repair(self, state: ChatTurnState) -> dict[str, Any]:
        return await asyncio.to_thread(_validate_repair, self._deps, state)

    async def finalize(self, state: ChatTurnState) -> dict[str, Any]:
        return await asyncio.to_thread(_finalize, self._deps, state)


def _route_after_round(state: ChatTurnState) -> str:
    if state.get("stream_interruption") is not None:
        return "validate_repair"
    if state.get("round_had_tools") and state["round_index"] < MAX_ROUND_BUDGET:
        return "agent_round"
    return "validate_repair"


def _route_after_validation(state: ChatTurnState) -> str:
    if (
        state.get("stream_interruption") is not None
        or state.get("validation_ok")
        or not state.get("repair_pending")
    ):
        return "finalize"
    return "agent_round"


def build_chat_turn_graph(deps: ChatTurnDeps, checkpointer: Any) -> Any:
    builder = StateGraph(ChatTurnState)
    builder.set_node_defaults(
        retry_policy=RetryPolicy(max_attempts=2, retry_on=(httpx.HTTPError,)),
        timeout=TimeoutPolicy(run_timeout=NODE_RUN_TIMEOUT_SEC),
    )
    nodes = ChatTurnNodes(deps)
    builder.add_node("retrieve", nodes.retrieve)
    builder.add_node("contract_guard", nodes.contract_guard)
    builder.add_node("agent_round", nodes.agent_round)
    builder.add_node("validate_repair", nodes.validate_repair)
    builder.add_node("finalize", nodes.finalize)
    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "contract_guard")
    builder.add_edge("contract_guard", "agent_round")
    builder.add_conditional_edges(
        "agent_round", _route_after_round, ["agent_round", "validate_repair"]
    )
    builder.add_conditional_edges(
        "validate_repair", _route_after_validation, ["agent_round", "finalize"]
    )
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer)
