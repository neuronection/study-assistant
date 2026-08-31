# 35 — Chat streaming performance, turn trace observability & the tool-call component system (ADR-077…079)

**Status:** COMPLETE (2026-08-25, user-requested) — 35A (ADR-079), 35B (ADR-077), 35C (ADR-078), 35D all done ·
**Phase:** post-1.0 backlog — chat UX & observability (plan 35) ·
**Suggested order:** A → B → C → D (A is the bug fix and unblocks the rest;
B and C are independent of each other after A; D consumes B + C)

**As-built (2026-08-25).** 35A: `useStreamBuffer` (rAF/33 ms-delta batching) +
`StreamingBubble` (plain-markdown live render, KaTeX deferred to the finalized message) +
`React.memo` `MessageBubble` + removed the `refetchInterval` 800 ms poll + rAF auto-scroll.
35B: migration 0036 `chat_messages.trace`; `answer_streaming` emits `run_id`/`elapsed_ms` on
every frame, `phase` frames (thinking/computing/reading/plotting/repairing) at each round/tool
transition, `tool_call` frames + persisted `tool_calls` carrying `status`/`start_ms`/
`duration_ms`, and a `trace` doc (run_id/model/latency/tokens/repair_rounds/rounds[] +
optional `thinking`); `Gateway.stream_events` captures provider reasoning
(`reasoning_content`/`thinking_delta`/`thought`), `stream()` filters text-only;
`ToolCallOut`/`MessageOut` extended. 35C: `features/chat/tools/registry.tsx`
(`getToolMeta` + per-tool result views + `formatDuration`), `ToolCallCard` is a registry-backed
shell with duration/status chips. 35D: `TurnTraceStatus` (live phase + elapsed) +
`TraceTimeline` (collapsible phase/tool timeline + reasoning disclosure) wired into
`ChatPanel` and `MessageBubble`. Backend 563 · frontend 701 tests green.

**Follow-up (2026-08-25, user-reported end-of-turn hang).** The finish event was still delayed
on the backend: `answer_streaming` emitted a per-token `stream_delta`, so `assistant_message`
queued behind thousands of WS `send_json` calls. Fixed by **server-side delta coalescing**
(`STREAM_DELTA_INTERVAL = 0.03`, `flush_deltas`), **commit-before-emit** (message committed
before `assistant_message` so the frontend refetch can't race the job-thread commit), and a
2 s `refetchInterval` safety net (replacing the removed 800 ms poll). Backend 564 tests.

**Follow-up 2 (2026-08-25, user-reported "no text generated / still processing").** The real
UX bug was that **only the first round streamed** — and round 0 is usually just a tool line,
so `CALC`/`SYMPY` text flashed as answer text while the actual final round used a silent
non-streaming `generate()`. Now **every round streams** (repair rounds emit `stream_start` to
reset), and a **tool-line filter** (`TOOL_LINE_RE` line split inside the coalescer) strips
tool lines from the stream so they only render as `ToolCallCard`s. `started` moved to the top
of `answer_streaming` (context assembly now counted) and `chat_turn_timing` structlog events
(`context`/`thinking`/`repairing`/`finalize`, per-phase ms) instrument the turn — the per-
message `trace` remains the persisted metric, shown in `TraceTimeline`. Backend 565 tests.


## Summary

The tutor chat is slow and opaque. One engineering bug makes long/math-heavy answers
freeze the UI for up to a minute, and — separately — the chat gives the user no visibility
into *what the assistant is doing*: which tools it called, how long each phase (thinking,
computing, reading, plotting, repair) took, total turn latency, token usage, or the model's
reasoning. This round fixes the performance bug and adds a **first-class turn trace** (a
persisted, streamed timeline of every phase and tool call with timings), rendered through a
**modular tool-call component system** (a per-tool registry, same discipline as the plan-34
widget registry) and a **calm, collapsible trace UI** that stays out of the way for casual
users but gives power users full observability.

## Context — honest findings

1. **Streaming rendering is O(n²) and blocks the main thread.** On every `stream_delta`
   (`ChatPanel.tsx:383`) the frontend appends the token to one growing string and re-renders
   the whole panel: the live bubble re-parses the **entire accumulated markdown** through
   `ReactMarkdown` + `remarkMath` + `rehypeKatex` (`BlockRenderer.tsx:110-117`), *and* every
   historical `MessageBubble` re-renders + re-parses its full markdown because `streamText`
   lives in `ChatPanel` and `MessageBubble` is not memoized (`ChatPanel.tsx:609-615`). KaTeX
   is expensive and this is a math tutor, so past a few hundred tokens each token's render
   saturates the main thread, WS frames queue, and the `assistant_message` "finished" event
   drains only after ~a minute. Symptom (user-reported): starts instantly, then freezes, then
   "finished" arrives late.
2. **The backend streams per-token with no coalescing.** `_stream_openai/_stream_anthropic/
   _stream_google` yield per SSE chunk (`gateway.py:444-533`) and `answer_streaming` forwards
   each one as a `stream_delta` WS frame (`services/chat.py:769-771`) — hundreds/thousands of
   frames per turn.
3. **There is no trace.** The only timing that exists is a single `latency_ms` on the
   `ai_interactions` audit row (`services/chat.py:890`), never surfaced. Tool calls carry
   `name/argument/result/title/phase` (`ToolCallOut`, `api/chat.py:84`) but no timings or
   status. There is no notion of a *round*, a *phase*, or a *run id* the frontend can key on.
4. **Tool calls render as one generic card.** `ToolCallCard.tsx` hard-codes icon+label for 5
   tools and dumps `argument`/`result` as monospace `<pre>`; there is no per-tool rendering
   (a `PLOT` result is plotly JSON shown as text, a `CALC` result isn't KaTeX-rendered) and
   no extensibility for future tools.
5. **Provider reasoning is discarded.** `_stream_openai` reads only `delta.content`
   (`gateway.py:461`), `_stream_anthropic` only `text_delta` (`gateway.py:493`), Google only
   `text` parts — o-series `reasoning_content`, Anthropic `thinking` blocks, and Google
   `thought` parts are dropped, so "show the thinking" has no source to show.

### Reserved ADRs

| # | One-line decision |
|---|---|
| 077 | A chat turn carries a **first-class turn trace** — a persisted, streamed timeline of phases (thinking / computing / reading / plotting / repairing) and tool calls with per-item timings, plus latency/token accounting — as the single source of truth for chat observability; no parallel instrumentation |
| 078 | Tool calls render through a **typed per-tool component registry** (same discipline as the ADR-072 widget registry): math results KaTeX-rendered, `PLOT` renders the actual chart, `READ`/`STATE` stay model-only; one extensible dispatch point, no raw HTML |
| 079 | Chat streaming rendering is **incremental and memoized**: deltas are batched to animation frames, the live bubble is isolated from history, history bubbles are memoized, and the full markdown/KaTeX re-parse is deferred to turn completion (or a coarse timer) — never per-token |

## Part 1 — Performance (the bug)

## 35A — Incremental, memoized streaming rendering (frontend)

**Problem.** Finding #1/#2: per-token full-tree re-render of markdown+KaTeX freezes the UI.

**Design.**

- **Batch deltas.** Add a small `useStreamBuffer` helper (or a local reducer in `ChatPanel`)
  that appends incoming `stream_delta`s to a ref buffer and flushes to state on a
  `requestAnimationFrame` (coalescing a whole frame's tokens into one commit), or on a
  ~60 ms timer when rAF is unavailable. A `flushStreamBuffer` call on `assistant_message` /
  `turn_error` ensures the tail is never lost.
- **Isolate the live bubble.** Extract the streaming bubble (currently inline at
  `ChatPanel.tsx:616-623`) into a `StreamingBubble` component that owns its own
  `streamText` state (via the buffer hook) and does **not** re-render `ChatPanel` or history.
  `ChatPanel` keeps only a `streaming` boolean to show/hide it and the thinking dots.
- **Memoize history.** Wrap `MessageBubble` in `React.memo` and make `onOpenGenerate` a
  stable `useCallback`; only the message object identity changes on refetch. Historical
  bubbles no longer re-render on stream updates.
- **Defer full math rendering.** While streaming, render the accumulated text through a
  **plain** markdown path (no `remarkMath`/`rehypeKatex`, or a light markdown renderer) so
  each flush is cheap; on `assistant_message` the finalized message renders through the full
  `BlockRenderer` (KaTeX) once. Where the stream must show math, only render *complete*
  `$…$`/`$$…$$` spans (a cheap heuristic), deferring incomplete trailing math.
- **Stop the redundant poll.** `refetchInterval: pending ? 800 : false` (`ChatPanel.tsx:314`)
  races the WS stream; drop it while streaming and rely on the `assistant_message`/`tool_call`
  WS events + a single `invalidateQueries` on completion (keep polling only as a WS-loss
  fallback with an exponential backoff, ≥2 s, and a "reconnecting" affordance later).
- **rAF scroll.** The auto-scroll effect (`ChatPanel.tsx:413-418`) moves to a
  `requestAnimationFrame`-scheduled handler so it doesn't run per delta.

**Accept.** A long math-heavy answer streams smoothly: deltas batch to ≤ ~60 renders/s,
history bubbles don't re-render during a turn, no 800 ms poll fires mid-stream, and the UI
reaches the "finished" state immediately when `assistant_message` lands.

**Tests.** Frontend: `useStreamBuffer`/batching (vitest fake timers + rAF mock) — N deltas →
≤ ceil(N / window) commits and the final flush on completion; `MessageBubble` is memoized
(skips re-render when unrelated state changes); the streaming bubble renders without
`remarkMath` while streaming and the finalized message renders via `BlockRenderer`; no
`refetchInterval` while `pending` and streaming. Backend: none.

## Part 2 — Turn trace (backend + contract)

## 35B — The turn trace: phases, rounds, timings, reasoning (backend)

**Problem.** Finding #3/#5: no run id, no phase/round timing, no reasoning capture.

**Design.**

- **Schema.** Migration **0036** adds `chat_messages.trace` (JSON, nullable) — one trace
  document per assistant message. Shape:

  ```json
  {
    "run_id": "hex",
    "model": "gpt-4o",
    "latency_ms": 8500,
    "input_tokens": 1234,
    "output_tokens": 456,
    "repair_rounds": 1,
    "rounds": [
      {
        "index": 0,
        "streamed": true,
        "start_ms": 0,
        "duration_ms": 2500,
        "phase": "thinking",
        "tool_calls": [
          {"name": "CALC", "argument": "sin(pi/6)", "result": "0.5",
           "start_ms": 2500, "duration_ms": 2}
        ]
      }
    ]
  }
  ```

- **Timing capture in `answer_streaming`.** Give the turn a monotonic `started` anchor
  (already present). Time each LLM round (`time.monotonic()` around the `stream`/`generate`
  call) and each tool execution (`run_tool_line`, `_read_handle`, `_read_widget_state`).
  Classify a phase per round/tool: `thinking` (LLM round), `computing` (CALC/SYMPY),
  `plotting` (PLOT), `reading` (READ/STATE), `repairing` (repair round). Assemble the
  `trace` dict and **persist it** on the message via `add_message(... trace=…)` and include
  it in the `assistant_message` WS payload + `MessageOut`.
- **Live events gain `elapsed_ms`.** Every emitted frame carries `elapsed_ms` (ms since turn
  start) so the frontend can render a live timeline without a local clock. `tool_call` frames
  gain `duration_ms`, `status` (`done`/`error`), and are emitted *after* execution (as today)
  so duration is known. `stream_start` gains `run_id`. A new `phase` frame
  (`{type:"phase", phase, elapsed_ms}`) is emitted at each phase transition.
- **Reasoning capture (best-effort, provider-dependent).** `Gateway.stream` grows an
  optional `yield ("reasoning", text)` channel: `_stream_openai` reads `delta.reasoning_content`
  (and `delta.reasoning`), `_stream_anthropic` reads `thinking` blocks, `_stream_google` reads
  `thought` parts. `answer_streaming` routes reasoning deltas into a `thinking` trace section
  (kept out of the visible answer text and out of the `ai_interactions` output token count) and
  emits them as `stream_delta` frames tagged `kind: "reasoning"`. Providers that don't emit
  reasoning simply produce none — nothing else changes.
- **Token accounting.** Reuse `_estimate_tokens` from `_log_interaction` to fill
  `input_tokens`/`output_tokens` in the trace (same numbers already audited).

**Accept.** After any turn, `GET /chat/sessions/{id}/messages` returns each assistant message
with a `trace` whose `rounds[].tool_calls[]` carry real start/duration timings; the WS stream
carries `elapsed_ms` on every frame and a `phase` frame at each transition; a provider that
streams reasoning surfaces it in the trace's `thinking` section while the visible answer
stays clean.

**Tests.** Backend: with a fake streaming gateway (subclass, scripted stream incl. tool lines
and a reasoning yield), assert `assistant_message.trace` round/tool structure + timings, that
`trace` persists, that `elapsed_ms`/`phase` frames are emitted, that reasoning content is
excluded from the final answer text, and migration 0036 is idempotent. Frontend: none (types
extended in 35C/35D).

## Part 3 — Tool-call component system + trace UI (frontend)

## 35C — Per-tool component registry (frontend)

**Problem.** Finding #4: one generic card can't render tool-specific output (chart for PLOT,
KaTeX for CALC/SYMPY, "read N chars" for READ), and can't be extended.

**Design.** Add `features/chat/tools/`:

- `registry.tsx` — `getToolMeta(name)` → `{ icon, labelKey, phase, render }` and
  `getToolRenderer(name)`; a typed `ToolRendererProps { tool, open }`; a `registerTool` seam
  (mirrors `components/widgets/registry.tsx`).
- Renderers: `MathToolResult` (CALC/SYMPY — result rendered with KaTeX / monospace math),
  `ReadToolResult` (READ — title + "read N chars" + summary; content stays model-only per the
  READ contract), `StateToolResult` (STATE — widget id + pretty JSON state),
  `PlotToolResult` (PLOT — parses the plotly-JSON `result` into a `chart` block and renders
  `PlotlyChart` so the user sees the actual graph), plus a generic fallback.
- **`ToolCallCard` becomes a shell** that dispatches to the registry: header row (icon, name,
  phase chip, duration, status), collapsible body that renders the tool-specific
  argument/result view. New `ChatToolCall` fields (`status`, `start_ms`, `duration_ms`) drive
  the status/duration display.

**Accept.** A `PLOT` tool call renders the actual chart; `CALC`/`SYMPY` show KaTeX-rendered
math; `READ`/`STATE` show model-only summaries; an unknown tool name falls back to the
generic card. Each card shows phase + duration + status. Adding a future tool = one registry
entry + one renderer, no changes to `ToolCallCard` or `MessageBubble`.

**Tests.** Frontend: registry dispatch (known/unknown), each renderer (mocked PlotlyChart for
PLOT), duration/status formatting, i18n keys present. Backend: none.

## 35D — Trace UI & live status line (frontend)

**Problem.** Even with the data in place (35B/35C), the user needs a *calm* surface: a live
sense of progress during the turn and full observability after, without overwhelming casual
users.

**Design.**

- **Live status line** (`TurnTraceStatus`) under the streaming bubble: a slim, non-blocking
  row showing the current phase as an icon + word (Thinking… / Computing… / Reading… /
  Plotting… / Repairing…) with a subtle animated indicator and a live elapsed timer
  (from `elapsed_ms`). Replaces/augments the bare `ThinkingDots`.
- **Trace summary** on completion: a compact chip (`8.5 s · 2 tools · gpt-4o · 1.2k tokens`)
  on the assistant message with an expandable **`TraceTimeline`** — a vertical list of
  phase/round rows with proportional duration bars, each tool call a nested row (name,
  argument, result, duration), and a header with total latency + token counts. Collapsed by
  default; i18n-clean; reduced-motion respects the token.
- **Reasoning display**: when the trace carries a `thinking` section, render it as a
  collapsible "Reasoning" disclosure (muted styling) so the model's thinking is inspectable
  but never in the user's face.
- **History**: messages loaded via `listChatMessages` render their `trace` through the same
  `TraceTimeline` (persisted in 35B), so past turns are equally inspectable.
- All labels via i18n (`chat.trace.*`, `chat.phase.*`); no hardcoded strings.

**Accept.** During a turn the user sees the current phase + elapsed time tick up; after it,
one click expands a timeline showing total time, each thinking round and tool call with its
duration, token usage, and (when available) the model's reasoning — with zero clicks the UI
stays as clean as today's.

**Tests.** Frontend: live status renders the correct phase per `phase` frame and counts up;
trace summary chip + timeline render round/tool durations and token counts; reasoning
disclosure renders only when a `thinking` section exists; history message renders its trace.

## Non-goals (this round)

- **No CopilotKit / Vercel AI SDK / LangChain migration** — the existing `TaskRunner` +
  `Gateway` + WS bus stay; this round is rendering + observability, not a chat-framework swap.
- **No per-token token-cost or $ display** — token *counts* yes; cost estimates stay in
  `ai_interactions`/settings.
- **No persisted full reasoning transcripts** — reasoning is captured in the trace but is not
  a new separately-searchable store; it lives on the message's `trace` JSON.
- **No AG-UI re-wiring** — the trace is *additive* to the existing `stream_delta`/`tool_call`
  frames; the plan-34 `ChatStreamAdapter` may later map the trace to AG-UI `ActivityDelta`
  events but that is deferred.
- **No analytics on tool/phase timing** (metrics rollups) this round — observability only.

## Dependencies & suggested order

A (perf) is the bug fix and must land first — it also makes B/C/D's new frames cheap to
render. B (trace) is backend-only and independent of C/D's code. C (tool registry) and D
(trace UI) consume B's types + frames. Migration 0036 is B's concern and is the only schema
change. Reasoning capture is a B sub-slice and can slip to the end of B without blocking C/D.

## Verification per slice

Standard suite before any commit (AGENTS.md): backend `ruff check . && mypy . && pytest`;
frontend `pnpm lint && pnpm typecheck && pnpm test && pnpm build`; docs synced via
`ca-docs-sync`; `ca-migration` for the 0036 Alembic change; ADR rows appended to
`06-decisions-and-risks.md` as each slice starts.

## Alternatives rejected

- **Throttle-only frontend fix (debounce the string, keep full re-render)** — still re-parses
  the whole markdown each flush and still re-renders history; memoization + deferral is the
  actual fix, batching is the enabler.
- **SSE instead of WS** — the WS bus already works and carries more than chat; switching
  transport doesn't fix the render strategy (ADR-079 addresses it directly).
- **A single rich `TraceView` component hard-coded for the 5 tools** — violates the
  registry discipline already established for widgets (ADR-072) and blocks future tools.
- **Streaming a bespoke `trace` event vs. persisting on the message** — persisting on the
  message is the single source of truth (history works for free); the streamed frames are a
  live projection of the same data.
- **Adopt the `ag-ui-protocol` SDK for traces now** — same pre-1.0 churn rationale as ADR-071;
  the trace shape is deliberately AG-UI-shaped (phases + tool calls + activity) so a later
  swap stays mechanical.
