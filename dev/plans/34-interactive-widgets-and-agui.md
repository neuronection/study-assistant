# 34 — Interactive widget blocks & the AG-UI state channel (ADR-071…073)

**Status:** COMPLETE (2026-08-24, user-approved) — 34A (ADR-071), 34B (ADR-072), 34C (ADR-073), 34D (ADR-074), 34E (ADR-075), 34F (ADR-076) all done ·
**Phase:** post-1.0 backlog — interactive visualization & generative UI (plan 34) ·
user-requested · **Suggested order:** A → B → C → D → E → F (C can run in parallel with B)

The block format gains a first-class **interactive widget** kind: exercises and the
tutor/chat can embed UI items — charts, 3D surfaces, interactive geometry, checklists,
sliders, coordinate grids — that are built from a **typed component library** (never raw
HTML), are fully interactive, and whose **state flows back to the backend** so the
deterministic graders *and* the LLM can read what the student did. The plumbing for all
of this is the **AG-UI protocol** (the open agent↔user interaction standard), adopted as
the app's internal agent↔UI contract so the feature has a robust, standard base instead of
ad-hoc wiring.

## Context

Honest findings that motivate the round:

1. **`chart` and `geo` are placeholders.** `BlockRenderer` dispatches on eight block
   types, but `ChartBlockView` and `GeoBlockView` render a dashed "not implemented" box
   (`frontend/src/components/blocks/BlockRenderer.tsx:152,216`); the `Block` union reserves
   `plotly`/`jsxgraph` payloads (`blocks/types.ts:29,52`) that nothing fills. G3 (Plotly)
   and G5 (JSXGraph) are P0/P1 in the vision catalog but have no implementation.
2. **The tutor cannot visualize or receive UI state.** Chat answers stream text through
   `BlockRenderer` (`features/chat/ChatPanel.tsx:88`), the tool catalog is deterministic
   text (`CALC`/`SYMPY`/`READ`, `backend/app/ai/tools.py:118`), and `STATUS.md` still lists
   "plot tool" as pending. There is no way for the model to *show* a chart, hand the
   student a self-check checklist, or *read back* what they ticked.
3. **There is no state channel at all.** Widgets that exist (drawing canvas, structural
   exercise inputs) write to their own one-off stores; nothing lets a grader or the LLM
   read a widget's live value in a uniform way. Every future answer kind that needs it —
   numberline/coordinate answers (C21), graph-sketch grading (G7), hotspot/diagram-label
   (C4), table/matrix completion (C19) — would re-solve this problem independently.
4. **AG-UI is the right base and we are effectively half-there.** The chat pipeline already
   streams the exact things AG-UI models: lifecycle, text deltas, tool calls/results, and
   job progress (`TaskRunner.stream_text`, tool-round phases, the `/ws` EventBus). Adopting
   AG-UI's *event + state vocabulary* as the internal contract is a mapping, not a rewrite,
   and it buys us a documented, interoperable state channel (snapshot + JSON-Patch delta)
   plus a standard generative-UI pattern — for the cost of a thin typed module.

Ordering rationale: the contract (A) must precede everything because the state channel and
generative UI both ride it; the widget layer (B, C) precedes the state channel (D) because
state is emitted by widgets; the surfaces (E, F) consume all three. Rendering (C) is
independent enough to parallelize with the registry (B).

**ADRs to record as slices start:** 071 (AG-UI contract) · 072 (widget layer) · 073
(renderers) — see table below.

### Reserved ADRs

| # | One-line decision |
|---|---|
| 071 | Adopt the AG-UI event + state vocabulary as the internal agent↔UI contract; implement as a thin typed module now, keep the `ag-ui-protocol` SDK as a deferred interop option |
| 072 | Generative UI = a typed widget grammar resolved against a frontend component registry (no raw HTML); widget state is first-class, deterministic-first, and readable by both graders and the LLM |
| 073 | `chart` and `geo` blocks are implemented by Plotly.js and JSXGraph, lazy-loaded; widgets reuse them |

## Part 1 — Foundation

## 34A — AG-UI event & state contract (backend)

**Problem.** The backend speaks three ad-hoc dialects — chat WS `stream_delta`/tool-round
phases, job-progress EventBus events, and structural exercise grading — and none of them
can carry a widget spec or a state delta. Any "LLM reads the UI" feature would bolt on a
fourth.

**Design.** Add `backend/app/agui/` as the single typed contract, mirroring the AG-UI
event vocabulary exactly (names + shapes + RFC-6902 JSON-Patch semantics) so the app is
AG-UI-compatible without inventing a private dialect:

- `agui/events.py` — Pydantic models for the subset we need: lifecycle
  (`RunStarted`/`RunFinished`/`RunError`, `StepStarted`/`StepFinished`), text
  (`TextMessageStart`/`Content`/`End`), tool (`ToolCallStart`/`Args`/`End`/`Result`), state
  (`StateSnapshot`/`StateDelta`/`MessagesSnapshot`), activity
  (`ActivitySnapshot`/`ActivityDelta`), and special (`Custom`).
- `agui/state.py` — `apply_patch(state, delta)` (RFC-6902) + `snapshot()` helpers, the one
  shared reducer for every state consumer.
- Map the existing stream onto it **without changing behavior**: `TaskRunner.stream_text`
  already emits last-round-only text (→ `TextMessageContent`), tool-round phases
  (→ `ToolCall*`), repair events (→ `Custom`); the `/ws` chat topic re-labels its frames
  to AG-UI event names additively (old `stream_delta` frames kept for one release so the
  frontend migration in 34D is decoupled).

Dependency decision (ADR-071): vendor the schema in `agui/` now — it is "just" a JSON event
schema, and `ag-ui-protocol` is pre-1.0 (0.1.x) with frequent releases; the module keeps the
shapes compatible so a later swap to the official SDK (for external AG-UI client interop) is
a mechanical import change. Revisit when interop is a real requirement.

**Accept.** A chat turn's WS frames can be losslessly expressed as AG-UI events
(`RunStarted` → `StepStarted(tool)` → `ToolCallStart/Args/End/Result` →
`TextMessageStart/Content/End` → `RunFinished`); `apply_patch` round-trips a snapshot
through a sequence of deltas to the same end state.

**Tests.** Backend: event model serialization (camelCase), stream→event mapping parity with
the current WS payloads (snapshot test), `apply_patch` over RFC-6902 vectors (add/replace/
remove/move), unknown-event fallthrough. Frontend: none yet (contract is backend-side).

**As-built (2026-08-24).** Delivered `app/agui/` — `events.py` (Pydantic v2 models, camelCase
wire aliases, `EventType` StrEnum, `serialize`/`serialize_many`), `state.py` (`apply_patch`
RFC-6902 add/remove/replace/move/copy/test + JSON-pointer escape handling, `apply_deltas`,
`StateStore.snapshot`/`apply`), `mapping.py` (`ChatStreamAdapter` + `map_stream` mapping the
live chat emit stream to AG-UI events with `Custom` fallthrough), `__init__.py` re-exports.
27 new tests (`test_agui_events.py`, `test_agui_state.py`, `test_agui_mapping.py`); backend
513 tests green. **Deviation:** live `/ws` additive re-labelling is deferred to 34D (the
channel) as noted in ADR-071 — 34A ships the contract + mapping adapter, not the live
re-wiring, so the frontend migration and re-labelling land together.

## Part 2 — Generative UI (widget layer)

## 34B — Widget registry + the `widget` block (frontend + contract engine)

**Problem.** The LLM needs a way to produce *any* interactive UI — but "any UI" as raw HTML
or React is unbounded, untestable, and unsafe. The app needs a **library** (not markup) that
the model can compose against, with the same validate-and-repair discipline every other
LLM artifact gets.

**Design.** Add a `widget` block type (`blocks/types.ts`) carrying
`{ widget, id, props, state }`, resolved against a frontend **component registry**
(`components/widgets/registry.tsx`): `chart`, `geo`, `checklist`, `slider`, `choice`,
`equation_input`, `numberline`. `BlockRenderer` dispatches `widget` to the registry; an
unknown `widget` name or invalid props falls back to the existing "unsupported" card (never
crashes). The widget **grammar** is versioned JSON per widget — the same contracts-engine
shape as quiz/exercise output — so the LLM's widget spec is validated + repaired by
`TaskRunner` before it reaches the renderer (ADR-072). No raw HTML/CSS injection anywhere:
widgets are React components; state is JSON; CSP is unchanged. Initial registry is the
foundation set above; `graph_sketch`, `table_fill`, and `code_runner` are later registrations
on the same mechanism (non-goals this round).

**Accept.** A widget spec the LLM emits renders as a real interactive component from the
registry; a malformed/unknown spec renders the safe fallback and is flagged (not a blank
screen); specs serialize into the block format so they persist, export, and round-trip like
any other block.

**Tests.** Frontend: registry dispatch, unknown-widget fallback, per-widget prop validation,
block serialization round-trip. Backend: widget-spec schema validation + repair loop
(fixtures: good, unknown-name, wrong-prop-type, oversized).

**As-built (2026-08-24).** Delivered the `widget` block type (`components/blocks/types.ts` +
`BlockRenderer` dispatch) and `components/widgets/`: `types.ts` (`WidgetComponentProps`),
`useWidgetState.ts` (local interactive state + optional `onStateChange` seam for 34D),
`ChecklistWidget`/`ChoiceWidget`/`SliderWidget`/`EquationInputWidget`/`NumberlineWidget`
(real, interactive), and `registry.tsx` (`getWidgetComponent`) with `chart`/`geo` as
placeholder entries pending 34C. Backend: `app/ai/widgets.py` (`validate_widget_block`/
`validate_widget_blocks` — name whitelist, per-widget prop typing, length/size caps). One new
i18n key (`widgets.numberlineHint`). 15 backend tests + 7 frontend tests; backend 528 green,
frontend 654 green. `chart`/`geo` real rendering is 34C's job, not 34B.

## 34C — `chart` (Plotly) + `geo` (JSXGraph) renderers, lazy-loaded

**Problem.** The two reserved blocks are the highest-value visuals (function/derivative
plots, data charts, 3D surfaces; draggable geometry) and the natural first widget
components, but nothing renders them.

**Design.** Implement `ChartBlockView` with **Plotly.js** (`plotly.js-dist-min` + a thin
typed wrapper, no `react-plotly.js` — the direct API avoids a deprecated wrapper) and
`GeoBlockView` with **JSXGraph** (a `jsxgraph` construction string executed against a bound
board; `view3d` for 3D). Both are lazy-loaded behind dynamic `import()` so they stay out of
the boot chunk (the existing tiptap/mermaid pattern). The `widget` registry's `chart`/`geo`
entries reuse these exact components, so exercise widgets and static blocks share one
renderer (ADR-073). Dark theme + reduced-motion follow the existing tokens.

**Accept.** A `{type:"chart",plotly:{...}}` block renders an interactive Plotly chart; a
`{type:"geo",jsxgraph:"..."}` block renders a draggable JSXGraph construction (e.g. a
function + draggable tangent line for the derivative case); both lazy-load and respect
theme/reduced-motion.

**Tests.** Frontend: both render (mocked libs in vitest, matching the mermaid mock pattern),
theme/reduced-motion props, lazy-load boundaries. Backend: none.

**As-built (2026-08-24).** Delivered `components/blocks/PlotlyChart.tsx` (direct
`plotly.js-dist-min` API, transparent backgrounds, reduced-motion → `transition:{duration:0}`)
and `components/blocks/JsxGraphBoard.tsx` (JSXGraph `initBoard` + `board.jc.parse(script)`
JessieCode, `freeBoard` on unmount), both lazy-loaded via dynamic `import()`. `ChartBlockView`/
`GeoBlockView` (empty geo → placeholder) and the registry's `chart`/`geo` widgets now render
through them (one renderer per visual). `src/types/plotly.d.ts` ambient module (the package
ships no types). 9 frontend tests (PlotlyChart/JsxGraphBoard/registry chart+geo); frontend 663
green. **Finding**: jsxgraph's bundled JessieCode/math eval uses `eval` internally (library
code) — flagged in STATUS. `view3d` 3D is available via JessieCode but not exercised yet.

## Part 3 — State channel

## 34D — Bidirectional widget state over the AG-UI channel (frontend + backend)

**Problem.** Widgets are interactive but dead-ended: their values live nowhere a grader or
the model can reach, which is the whole point the user asked for ("LLM get state of the UI
too").

**Design.** The registry wraps every widget in a state binding that, on interaction, emits an
AG-UI `StateDelta` (JSON-Patch) upstream over the existing `/ws` channel and applies
downstream `StateSnapshot`/`StateDelta` events through `agui/state.apply_patch`. Backend
reduces the deltas into a **per-surface state document**: for exercises the step's state
(`exercise_steps`/`step_attempts` gains a `state` JSON column — the one schema change of the
round), for chat the message/session state. **Deterministic-first** (ADR-072): structural
graders and the equivalence chain read state directly (a `numberline` answer, a `slider`
value, a `checklist` selection) before any LLM is involved. The LLM reads state two ways:
(a) a new `STATE <widget_id>` line in the chat tool catalog (deterministic fetch, same
budget/strip pattern as `READ`), and (b) the context resolver's manifest gains an optional
`widget_state` slot for the active attempt. Everything is audited like existing help events.

**Accept.** Ticking a checklist or dragging a slider in a widget updates the persisted state
document (visible via the API); a grader reads it without an LLM; a follow-up tutor turn can
`STATE w1` and tailor its answer to the student's actual selections.

**Tests.** Backend: state reduce over a delta sequence, `STATE` tool (present/missing/empty
budget), deterministic grader reads widget state, state column round-trip + migration.
Frontend: interaction → delta emission, snapshot apply re-renders the widget, state survives
a re-render/reconnect.

**As-built (2026-08-24, ADR-074 — one ADR beyond the reserved 071…073).** Migration 0033 adds
`chat_messages.state` + `step_attempts.state` (JSON). `PATCH /chat/messages/{id}/state`
reduces an RFC-6902 delta with `apply_patch` (deep-copies first — SQLAlchemy JSON
change-detection would swallow in-place mutation), 100 KB cap, audited `widget_state`, returns
the snapshot. `STATE <widget_id>` joins the chat tool catalog (`app/ai/tools.py`,
extract/strip/budget 3/turn) backed by `_read_widget_state` (chat service) +
`read_widget_state` (widgets.py). Frontend: `BlockRenderer.onWidgetStateChange` +
`lib/state.ts::diffState` (flat JSON-Patch diff). 7 backend tests + 6 frontend tests; backend
535 · frontend 669 green. **Deviations**: the context resolver's `widget_state` manifest slot
(34D plan) and the live WS `StateSnapshot` read path are deferred to 34E/34F (state is
persisted + readable via REST/STATE tool now); exercise-widget grading (numberline/etc.) and
the chat-panel PATCH wiring land in 34E/34F.

## Part 4 — Surfaces

## 34E — Widgets in exercise stems & steps

**Problem.** Exercises need "a question *plus* UI items" (a plot to read, a checklist of
scopes, a coordinate grid to mark) — today a stem is text/blocks only.

**Design.** Exercise stems and step prompts accept `widget` blocks alongside existing block
types (generation prompts learn the widget grammar; the `exgen` validators extend to widget
specs via 34B's schema). The player (`features/exercises/`) renders widget blocks through the
registry and binds each to 34D's state channel so the attempt's state is graded
deterministically where possible and rubric-graded where not.

**Accept.** A generated exercise can carry a chart to read and a checklist to complete; the
player renders both and the state lands on the step attempt for grading.

**Tests.** Backend: exgen emits a valid widget block, invalid widget repaired/rejected,
state recorded on attempt. Frontend: player renders a widget block and submits its state.

**As-built (2026-08-24, ADR-075 — one ADR beyond the reserved 071…074).** `EXGEN_SYSTEM`
teaches an optional `steps[].widgets` list; `_step_problems` validates each widget block via
`validate_widget_block`, and `ExgenService.generate` appends them after the `prompt_md` text
block — so a generated step's `prompt` can carry a chart + a checklist. `AnswerIn` gains
`state`; `submit_step_answer` persists it on `StepAttempt.state`. Frontend:
`submitStepAnswer` takes an optional `state` arg, and `Player.tsx` collects step-widget state
via `BlockRenderer.onWidgetStateChange` and submits it (resetting on step advance). 3 backend
tests (`test_exercise_widgets.py`) + 1 frontend test (`PlayerWidgets.test.tsx`); backend 538 ·
frontend 670 green. Widget-answer grading stays deferred (non-goal).

## 34F — Widgets in the tutor chat

**Problem.** The tutor should be able to *show* and *read*, not just tell — plot a function,
hand the student a self-check list, read the ticks and continue.

**Design.** Chat answers gain `widget` blocks (via a `Custom`/generative-UI event the
frontend maps to a registry render, and/or a `widget` block in the structured answer the
same way `chart`/`geo` blocks already render through `BlockRenderer`). A new `PLOT` tool is
added to `CHAT_TOOL_CATALOG` (SymPy computes sampled points server-side → `chart` block
data) — this closes the long-pending "plot tool" item deterministically rather than letting
the model author plot data. Widgets in chat bind to 34D so the next turn reads the state.

**Accept.** "Plot f(x)=sin(x)/x" renders an interactive chart in the chat; a tutor that asks
"which rule did you use?" renders a checklist and its next message reacts to the selection.

**Tests.** Backend: `PLOT` tool (valid/invalid expression, sampling bounds), chat answer with
a widget block validates + renders. Frontend: chat renders a widget block and streams its
state back.

**As-built (2026-08-24, ADR-076 — closes plan 34).** `PLOT <expr>` joins the catalog
(`plot_function`: SymPy `lambdify` sampling over [-10,10], 201 points, non-finite/oversized → null).
`parse_answer_blocks` (`app/ai/parsing.py`) splits the final answer on ` ```chart `/ ` ```widget `
fences into `ChatMessage.blocks` (returned in `MessageOut`, mentions attached to text blocks);
`CHAT_ANSWER_SYSTEM` teaches the fence convention. Frontend `MessageBubble` renders
`message.blocks` (fallback to text+mentions) and wires `onWidgetStateChange` → `diffState` →
`PATCH /chat/messages/{id}/state`. 10 backend tests (`test_chat_blocks.py`,
`test_chat_answer_blocks.py`) + 1 frontend test (`ChatPanel.test.tsx`); backend 548 · frontend
671 green. The long-pending "plot tool" item is closed.

**Post-completion follow-up (2026-08-24, user-requested).** Single-sourced the widget
grammar: `app/ai/widgets.py` gained `WIDGET_SPECS` + `build_widget_doc()` →
`CHAT_WIDGET_DOC`/`EXGEN_WIDGET_DOC` (injected into the chat system prompt via
`services/chat.py._build_messages` and the exgen prompt via `ExgenService._build_prompt`),
removing the hardcoded widget text from `CHAT_ANSWER_SYSTEM`/`EXGEN_SYSTEM`. The tutor now
knows every widget + its exact props, drift-free from the validator. Backend 552 tests.

## Non-goals (this round)

- **No CopilotKit** — AG-UI gives us the contract; we keep our own React surface and
  `TaskRunner`, not a second chat framework.
- **No arbitrary/raw-HTML UI** — generative UI is registry-typed components only (ADR-072);
  a free-form sandbox (FastMCP Apps' iframe/Pyodide model) is rejected outright.
- **No declarative A2UI spec, no external AG-UI clients** — we adopt the *event/state
  vocabulary*, not interop with third-party AG-UI hosts (deferred with the SDK decision).
- **No full grading of C21 numberline / G7 graph-sketch / C4 hotspot / C19 table-fill this
  round** — the state channel is the enabler; their graders are follow-on registrations.
- **No new storage beyond the one `state` column**; no Tauri, no plot persistence as
  materials, no analytics on widget interaction yet.

## Dependencies & suggested order

A (contract) is foundational. B (registry/grammar) and C (renderers) build on the block
renderer only and can run in parallel. D (state) needs A + B. E and F need B + C + D.
Migration (the `state` column) is D's concern and is the only schema change.

## Verification per slice

Standard suite before any commit (AGENTS.md): backend `ruff check . && mypy . && pytest`;
frontend `pnpm lint && pnpm typecheck && pnpm test && pnpm build`; docs synced via
`ca-docs-sync`; `ca-migration` for D's Alembic change; ADR rows appended to
`06-decisions-and-risks.md` as each slice starts.

## Alternatives rejected

- **FastMCP Apps / Prefab / Generative UI** — iframe-hosted UI, a second (non-React) design
  system, CDN-Pyodide (breaks local-first), and a sandbox without SymPy/NumPy. Rejected for
  the same reasons as the prior discussion; the *pattern* (typed component catalog + state)
  is adopted natively via AG-UI.
- **Ad-hoc private state protocol** instead of AG-UI — reinvents exactly what AG-UI already
  specifies well (snapshot/delta, tool-call events, generative UI); adopting the vocabulary
  is cheaper and interoperable.
- **Hard dependency on `ag-ui-protocol` today** — pre-1.0 churn for a JSON schema; vendoring
  keeps the contract while preserving a clean SDK swap path (ADR-071).
- **CopilotKit as the generative-UI framework** — replaces the chat state plumbing and the
  Python contract engine for a React-only framework; too heavy and off-stack.
- **Per-widget bespoke state wiring** (the status quo) — N divergent stores, no uniform
  grader/LLM read, which is the exact gap this round closes.
