# 37 — AI gateway framework adoption: LangChain behind the gateway, native tool calling & reliability hardening (ADR-081…084)

**Status:** COMPLETE (2026-08-26, user-approved; slices A→D landed as committed
`feat(ai)`/`feat(chat)` changes — 37A ADR-081, 37B ADR-082, 37C ADR-083, 37D ADR-084 with
migration 0037. As-built notes under each slice; backend 596 · frontend 706 tests green) ·
**Phase:** post-1.0 backlog — AI infrastructure ·
**Suggested order:** pre-A spike → A → B → C → D (the spike gates A's dependency change; A is
the transport swap and unblocks B/C/D; B and C are independent of each other after A and
share the same cap-gating discipline; D is additive)

## Summary

The AI layer is deliberately hand-rolled (ADR-029): `LLMGateway` speaks three provider REST
families directly over `httpx`, tools are parsed out of the answer text with a regex
(`TOOL_LINE_RE`), and structured outputs rely on a JSON repair loop. That was the right call at
ADR-029's revisit point — the needed abstraction was thinner than LangChain. But the layer has
since grown (9 chat tools, streaming + reasoning, turn traces, budgets, cost ledger) and the
hand-rolled seams now cost more than they save. This round adopts **LangChain** — the framework
ADR-004 originally chose and ADR-029 deferred — surgically, not as a big-bang re-platforming:

- **LangChain chat models** replace the hand-rolled provider adapters + SSE parsers (transport:
  `ChatOpenAI`/`ChatAnthropic`/`ChatGoogleGenerativeAI`/`ChatOllama`, unified message format,
  `.invoke()`/`.stream()` with reasoning deltas, `.with_retry()` + `.with_fallbacks()`, real
  `usage_metadata` token counts). It does *not* replace task→model→provider resolution, the
  keyring, the budget gate, or the audit ledger — those stay CourseAssistant code.
- **Native function calling** via `.bind_tools()` replaces prompt-parsed tool lines, gated on
  the model's `tools` capability (text-only/local models keep the prompt grammar — ADR-006
  holds).
- **Structured outputs** via `.with_structured_output()` (LangChain's flagship feature) become a
  pre-validated optimization on top of the deterministic repair loop + validators, which stay
  the source of truth (ADR-021/022).
- **Prompt caching + real token/cost accounting** close the remaining cost observability gaps
  (`usage_metadata` tokens into the existing `_ledger`; caching where it's real — OpenAI
  prefix-cache accounting + Anthropic `cache_control` hints; Google's explicit cache-object
  lifecycle is descoped to a follow-up).

**LangGraph is not adopted here** — ADR-029's revisit clause still hasn't fired (no stateful
multi-node graph exists yet). But landing LangChain core is the prerequisite, so this round
removes the barrier and makes a later LangGraph adoption (tutor/quizgen graphs) a contained,
incremental step rather than a re-platforming.

## Context — honest findings

1. **Three hand-rolled provider families, three SSE parsers, one codebase to maintain.**
   `gateway.py` implements `_call_google/_call_openai/_call_anthropic` (generate) *and*
   `_stream_openai/_stream_anthropic/_stream_google` (SSE) with bespoke payload mapping and
   reasoning-delta extraction (`reasoning_content`/`thinking_delta`/`thought`). Every new
   provider or provider-API change is our code to write and test; LangChain's per-provider
   packages normalize all of this behind one `BaseChatModel` interface.
2. **No retries, backoff, or rate-limit handling.** `generate()`/`stream_events()` make one
   attempt and fail (`gateway.py:230-295`). A transient 429/5xx on the chat path surfaces as a
   `ProviderError` → 502 to the user; the repair loop can't help a transport failure. ADR-029
   itself records "retries/cost-table integration still pending". LangChain offers
   `.with_retry()` (with exponential-jitter backoff) and `.with_fallbacks()`; note its 429/
   rate-limit handling is *lighter* than a dedicated gateway's — see Risks.
3. **Tools are prompt-parsed text, not real tool calls.** The model is taught to emit
   `CALC …`/`SYMPY …`/`READ …`/`STATE …`/`PLOT …`/`COURSES …` lines that `TOOL_LINE_RE`
   (`tools.py:139`) extracts and `run_tool_line` (`tools.py:147`) executes. This is the source of
   the plan-36 `\s`-vs-`[ \t]` bug class, is fragile across model families, and consumes output
   tokens the user never sees. ADR-043 chose this explicitly ("no native function-calling
   migration"), but the tool surface has since grown from 0 → 9 tools with full timing/trace
   observability, which shifts the trade-off. LangChain's `.bind_tools()` normalizes tool
   calling across providers.
4. **Structured output is a repair loop, not a schema.** TaskRunner round-trips malformed JSON
   through "fix it" repair rounds (`runner.py`) with deterministic validators as the real gate.
   That's correct and must stay — but `.with_structured_output()` collapses repair rounds to
   near-zero on capable models, and the validators still run afterward.
5. **Cost/token accounting is an estimate, and there's no prompt caching.** `_estimate_tokens`
   is `len(text) // 4` (`gateway.py:110`); real `usage` numbers from providers are discarded.
   The tutor re-sends large context bundles every turn (system prompt + manifest + tool docs);
   Anthropic/Google/OpenAI all support prompt caching that would cut that cost materially, but
   nothing sets `cache_control`/`cachedContent`.
6. **Testability without network is a hard-won property.** `LLMGateway(…, transport=…)` +
   `httpx.MockTransport` powers `test_gateway.py`, `test_budgets.py`,
   `test_streaming_and_tools.py`. LangChain chat models accept an injected `http_client`/
   `http_async_client` (an `httpx.Client`/`AsyncClient` built on our transport), so the same
   no-network property is preservable — and it must be, or the suite regresses.

### Reserved ADRs

| # | One-line decision |
|---|---|
| 081 | Adopt **LangChain chat models** as the transport behind `LLMGateway` (`ChatOpenAI`/`ChatAnthropic`/`ChatGoogleGenerativeAI`/`ChatOllama`) — provider-agnostic invoke/stream with `.with_retry()` + `.with_fallbacks()`, unified reasoning deltas, and real `usage_metadata` token accounting — while **keeping** CourseAssistant's task→model→provider resolution, keyring read, budget gate, and `ai_interactions` ledger. This invokes ADR-029's revisit clause and lands ADR-004's original choice as an *implementation detail behind the existing `LLMGateway` surface*, not a new abstraction layer. LangGraph stays deferred (no stateful graph yet) |
| 082 | Chat tools migrate from **prompt-parsed tool lines to native function calling** via `.bind_tools()`, **cap-gated** (`tools` capability): the deterministic tool *implementations* (`run_tool_line` + `RESOURCE_TOOLS`) are unchanged and stay server-executed; the prompt-line grammar is retained as the fallback for text-only/local models (ADR-006). `TOOL_LINE_RE` extraction + tool-line stripping are removed from the native path |
| 083 | Structured generation gains an optional **`.with_structured_output()`** (Pydantic schema) pre-validation on top of the existing repair loop: capable providers emit schema-conformant drafts (fewer repair rounds), but the deterministic validators remain the single source of truth and every draft still passes them (ADR-021/022) |
| 084 | Enable **prompt caching where it's real** — OpenAI automatic prefix-cache **accounting** + Anthropic `cache_control` hints on the high-reuse chat/context prefixes; Google explicit `cachedContent` (cache-object lifecycle) descoped to a follow-up — and account **cache hits** in the cost ledger; real `usage_metadata` tokens (ADR-081) replace the `len//4` estimate everywhere |

## Spike findings (pre-A, 2026-08-26 — verified in a scratch venv)

- **Pinned set:** `langchain-core==1.6.0`, `langchain-openai==1.6.0`,
  `langchain-anthropic==1.6.1`, `langchain-google-genai==4.3.5` (pydantic 2.13.4,
  httpx 0.28.1 — both compatible with the backend). **`langchain-ollama` is dropped
  from the dependency set:** the app has no ollama provider type — Ollama runs via the
  `openai_compatible` preset (`providers.py` PRESETS), so `ChatOpenAI(base_url=…)` covers
  it (three provider packages, not four).
- **Injection:** `ChatOpenAI` takes `http_client` natively; `ChatAnthropic` has *no*
  http_client field — pre-seed its `_client` cached_property with
  `anthropic.Anthropic(http_client=…)`; `ChatGoogleGenerativeAI` — assign
  `model.client = google.genai.Client(http_options=HttpOptions(httpx_client=…))`
  post-init (`__init__` overwrites any passed client).
- **Reasoning deltas (the predicted drift, confirmed):** `ChatOpenAI` 1.6 **drops**
  nonstandard `delta.reasoning_content`/`reasoning` (docstring: use provider-specific
  subclasses). A small `CaChatOpenAI(ChatOpenAI)` override of
  `_convert_chunk_to_generation_chunk` restores them into
  `additional_kwargs["reasoning_content"]` (verified). Anthropic `thinking_delta` and
  Google `thought` parts both surface as content blocks `{"type": "thinking", "thinking":
  …}` — one extractor covers both.
- **Usage:** real `usage_metadata` on all three (incl. `input_token_details.cache_read`
  from OpenAI `prompt_tokens_details.cached_tokens` — 37D-ready).
- **Errors:** openai/anthropic raise SDK `APIStatusError` subclasses carrying
  `status_code`; Google raises `Google*Error` with the code only in the message — map
  all to our `ProviderError` (status from `status_code` attr, else parsed from text).
- **Retry:** `.with_retry(stop_after_attempt=2, wait_exponential_jitter=False)` verified
  against a stateful 500-then-200 MockTransport (2 attempts → success).
- **Fallback attribution:** `.with_fallbacks()` does not expose which branch answered —
  37A runs its own fallback loop over `[primary, fallback]` (each with `.with_retry()`),
  which gives the ledger/trace clean attribution to the *answering* model.

## Part 1 — Transport & reliability (LangChain chat models)

## 37A — LangChain behind the gateway (backend)

**Problem.** Findings #1/#2: hand-rolled adapters + no retry/backoff/fallback.

**Design.**

- **Dependency — gated by a pre-A spike.** Add to `backend/pyproject.toml`: `langchain-core`
  plus the provider packages we support — `langchain-openai`, `langchain-anthropic`,
  `langchain-google-genai`, `langchain-ollama` (Ollama's `openai_compatible` preset can also
  stay `ChatOpenAI` with `base_url`, but `ChatOllama` is the cleaner fit). Prefer the narrow
  `-provider` packages over the `langchain` umbrella (less transitive surface; matches modern
  LangChain guidance). "Pin reviewed versions" is a task, not a hope: a **pre-A research
  spike** (no code) verifies (a) one mutually compatible `langchain-core` + provider-package
  version set, (b) that all four packages still expose reasoning deltas in
  `additional_kwargs` on the pinned versions (`reasoning_content`/`thinking`/`thought` is
  itself a moving vocabulary across releases — the per-provider normalization we're deleting
  comes back as version-pinning discipline), and (c) that all four honor an injected
  `http_client`. The frontend is untouched.
- **Telemetry stays off.** LangChain/LangSmith tracing is never enabled — no `LANGSMITH_*` or
  `LANGCHAIN_TRACING_V2` env is set anywhere (local-first; enabling it would be its own
  explicit user decision). A settings/env test asserts the suite and the app never set them.
- **Keep the `LLMGateway` surface.** `resolve(task)`, `generate(task, messages, model)`,
  `stream(task, …)`, `stream_events(task, …)` signatures are **unchanged** — every caller
  (`services/chat.py`, `TaskRunner`, `ocr`, `embeddings`, `describe`) keeps working. LangChain
  is reached *inside* the adapter layer that currently holds `_call_*`/`_stream_*`. This is the
  key de-risking move: the swap is invisible above the gateway.
- **Model factory.** A `_chat_model(resolved) -> BaseChatModel` builds the right class from
  `resolved.provider_type` (google → `ChatGoogleGenerativeAI(model=external_id)`,
  openai_compatible → `ChatOpenAI(model=external_id, base_url=…)`, anthropic →
  `ChatAnthropic(model=external_id)`, ollama → `ChatOllama(model=…)`), reads the key from the
  keyring per call (ADR-009, unchanged), and composes `.with_retry(stop_after_attempt=2,
  wait_exponential_jitter=…)` and `.with_fallbacks([…])` using the existing
  `fallback_model_id` task assignment (this finally makes ADR-029's "fallback chain" real at
  the transport level). Keep `_check_budget` **before** the call exactly as today.
  **Fallback attribution:** when a fallback answers, the `_ledger` row and the chat `trace`
  record the model *that actually answered* (model id, tokens, cost, latency) — never the
  resolved primary — or Settings→Tasks spend and turn traces silently bill the wrong model.
- **Message mapping.** Map our typed `Message`/`Part` (`TextPart`/`ImagePart`) → LangChain
  `SystemMessage`/`HumanMessage`/`AIMessage`, reusing the existing `_split_system` logic and the
  multimodal content-block shapes (`{"type":"text"|"image_url"}`). Our typed `Part` vocabulary
  remains the in-repo canonical form.
- **Unified streaming + reasoning.** `generate()` → `.invoke()` (read `AIMessage.content`);
  `stream_events()` → `.stream()` over `AIMessageChunk`, mapping `chunk.content` → text and
  reasoning from the provider's reasoning deltas (`additional_kwargs["reasoning_content"]` /
  `"thinking"` / `"thought"`, normalized per provider) back to our
  `StreamChunk(kind: "text" | "reasoning", text)` — so `answer_streaming` and the plan-35
  `trace.thinking` path are untouched.
- **Streaming retry policy (explicit, because `.with_retry()` can't provide it).** Retries
  compose cleanly with `.invoke()`, but a `.stream()` that has already yielded deltas cannot
  be transparently replayed — the user saw text. Policy: retry/fallback apply only to
  failures **before the first emitted chunk** (connect, auth, first-token timeout); a
  mid-stream failure ends the turn honestly — error event out, the streamed prefix persisted
  and flagged in the trace — and never silently restarts the answer.
- **Real usage.** Read `AIMessage.usage_metadata` (`input_tokens`/`output_tokens`/`total_tokens`)
  and feed `_ledger` real token counts, computed against our existing `cost_in`/`cost_out` model
  columns (LangChain does not compute $ — our ledger already does, so this is a clean fit).
  Retire `_estimate_tokens` for everything except the offline/mock path.
- **No-network tests preserved.** Construct each chat model with an `http_client`/
  `http_async_client` built on the existing `httpx.MockTransport` (the same `transport=` param
  `test_gateway.py`/`test_streaming_and_tools.py`/`test_budgets.py` already pass). **The suite
  must not hit the network — a CI guard (fail on any live socket) is added.**
- **Error mapping.** Map LangChain/`httpx` exceptions back into our typed `ProviderError`
  (status + body snippet + the Settings→Providers hint on 401/403) so every AI route still
  returns 502, never 500 — the contract `test_chat_turn_error.py` and the gateway-wrapping
  tests depend on it.

**Accept.** A provider 5xx now retries (`.with_retry`) instead of failing the turn — on
`generate()` and on streams *before the first chunk* (a mid-stream failure keeps the partial
answer + a trace flag, never a silent restart); a `fallback_model_id` is used automatically on
primary failure, and the ledger/trace attribute the *answering* model; no LangSmith/telemetry
traffic ever leaves the machine; streaming/reasoning/trace behave identically to today;
`_ledger` records real token counts (× our cost table); the full backend suite passes with
zero network access; a 401 still surfaces as the friendly 502 message.

**Tests.** Backend: extend `test_gateway.py` with (a) 500-then-success via `MockTransport` →
retried once, (b) primary-fails → fallback model used *and billed/traced as the answering
model*, (c) reasoning deltas still yield `reasoning` chunks, (d) `usage_metadata`-derived
token counts land in `ai_interactions`, (e) network-fail CI guard, (f) mid-stream failure →
no replay: streamed prefix kept, failure flagged in the trace, WS error event still fires,
(g) no `LANGSMITH_*`/`LANGCHAIN_TRACING_V2` is ever set. Existing gateway/budget/streaming
tests stay green (surface-preserving swap). Frontend: none.

**As-built (37A, 2026-08-26).** Landed as planned with three recorded deviations:
(1) **Retry is a first-class loop, not `.with_retry()`** — `LLMGateway` runs its own
`retry_attempts`/`retry_wait` loop (default 2/0.5s) with one `is_transient_error()`
predicate (status ≥500 or 429, or an `httpx.HTTPError` in the cause chain). Reasoning:
`.with_retry()` cannot express Google-429 retry (type-based), and its stream retry would
replay already-emitted chunks — the exact failure the plan's streaming-retry policy forbids.
The stream path retries *only* the first-chunk acquisition; a mid-stream error raises
`ProviderError` (no replay, no fallback). (2) **Fallback is our own chain loop, not
`.with_fallbacks()`** — attribution requires knowing *which* model answered; `_resolve_chain`
returns `[primary, fallback]` from `TaskAssignment` and `generate`/`stream_events` try each
in order, so `_ledger` bills the answering model. (3) **`langchain-ollama` is not installed**
(spike finding — Ollama is an `openai_compatible` preset; `ChatOpenAI(base_url=…)` covers
it). Also: `ChatOpenAI` needed the `CaChatOpenAI` subclass to surface `reasoning_content`
deltas (spike-confirmed drift); Anthropic/Google reasoning arrives as `{"type":"thinking"}`
content blocks; keyless OpenAI endpoints send `Authorization: Bearer EMPTY` (was: no header);
Google auth moved from `?key=` param to `x-goog-api-key` header; the shared message
dataclasses moved to `app/ai/types.py` (re-exported by `gateway.py` for compat — breakable
circular import avoided). Mid-stream chat turns now persist the streamed prefix with
`trace.stream_interrupted` + an emitted `stream_interrupted` event (`services/chat.py`). The
no-network suite guard is a session-scoped conftest fixture that blocks `socket.connect*`;
backend 581 · frontend 706 tests green.

## Part 2 — Native tool calling

## 37B — Chat tools become real function calls (backend, cap-gated)

**Problem.** Finding #3: prompt-parsed tool lines are fragile and the plan-36 regex bug class
recurring.

**Design.**

- **One tool schema, one registry.** Declare the 9 chat tools (CALC, SYMPY, READ, STATE, PLOT,
  COURSES, NODE_OVERVIEW, NODE_QUIZZES, NODE_EXERCISES, NODE_NOTES) as `.bind_tools()` schemas
  (Pydantic args models) generated from the existing `CHAT_TOOL_DOC` /
  `build_resource_tool_doc()` source (single source of truth, no drift with the prompt doc).
- **Deterministic execution stays ours.** When `AIMessage.tool_calls` arrives, execute the
  *same* functions (`run_tool_line` semantics + `RESOURCE_TOOLS` functions) server-side, append
  `ToolMessage` results, and continue the agent loop. `MAX_TOOL_ROUNDS`,
  `MAX_RESOURCE_ROUNDS`, and the `tool_call` WS event + `chat_messages.tool_calls` persistence
  (plan 35) are unchanged — they now consume structured `tool_calls` instead of regex matches.
- **Cap-gated, prompt fallback.** `infer_caps` already computes a `tools` capability
  (`providers.py:63-68`). A `ResolvedModel` with `tools` uses `.bind_tools()`; one without
  (local/Ollama text models, ADR-006) keeps the exact current prompt grammar + `TOOL_LINE_RE`.
  One `use_native_tools(model) -> bool` decision point, both paths emitting identical
  `tool_call` events, so `ToolCallCard`/`TraceTimeline` don't know which ran.
- **Auto-degrade when the cap lies.** `infer_caps` is a *name heuristic* (substring matches
  like `"qwen"`/`"gpt-4"`, `providers.py:63-68`) — a false positive sends `.bind_tools()`
  payloads to an endpoint without function calling and every turn 400s. The native path
  therefore catches tool-unsupported API errors and falls back to the prompt grammar *for
  that turn* (immediate retry, same round budget), remembering the degradation in-memory per
  provider+model so later turns skip straight to the prompt path; the Settings `tools`
  capability override remains the durable fix (and a one-line log points at it).
- **Remove the stripping hack on the native path.** Tool lines no longer appear in streamed
  text (the model emits structured `tool_calls`, not text), so `TOOL_LINE_RE`-based stripping
  and the plan-35 `TOOL_LINE_RE` stream filter become native-path dead code (retained only in
  the fallback branch).
- **Prompt teaching updated.** `CHAT_ANSWER_SYSTEM` stops instructing "emit one tool line" when
  native calling is active (schema descriptions carry the contract); the fallback prompt text
  is untouched.

**Accept.** "solve sin(pi/6)" → a native `CALC` tool call executes server-side, the result
round-trips, and a `ToolCallCard` renders it — with no `CALC …` text leaking into the stream;
a `tools`-capable and a non-capable model produce byte-equivalent `tool_call` events and the
same final answer contract; a mis-capped model (cap says `tools`, endpoint rejects tool
payloads) degrades to the prompt grammar transparently — the turn still answers, and the
next turn in the session doesn't retry the dead path; `MAX_TOOL_ROUNDS` still bounds the loop.

**Tests.** Backend: fake gateway/scripted `tool_calls` responses → native `CALC`/`SYMPY`
executed + result fed back + stripped from answer + `tool_call` event; cap-gate flips the path
(`tools` vs not); budget/round caps honored on the native path; scripted tool-unsupported 400
→ auto-degrade to the prompt grammar, turn succeeds, degradation remembered (the second turn
goes straight to the prompt path); prompt-fallback branch still passes the existing
`test_streaming_and_tools.py` cases. Frontend: none (cards already generic).

**As-built (37B, 2026-08-26).** Landed with two recorded deviations from the reserved text:
(1) **The agent loop stays in `ChatService.answer_streaming`, not the gateway.** The plan left
the loop owner open ("continue the agent loop"); budgets, READ/STATE registries, WS `tool_call`
events, and the trace are chat-service concerns, so the gateway exposes *native tool calls as
stream events* and chat.py stays the round-loop owner — mirroring the existing prompt-round
structure (one `stream_events` call per round). (2) **Tool execution is unified, not a new
native branch.** Native calls are flattened to the same `(kind, argument)` shape as the prompt
grammar (`_native_call_args`), so the *same* deterministic execution body runs for both paths
(budgets, `tool_call` events, `_tool_result_summary` all identical); the only difference is the
source of `tool_calls` (structured `tool_call` StreamChunks vs `TOOL_LINE_RE`) and the
feedback channel (real `ToolMessage`s appended to the round vs the "Verified tool results"
system message). Native path is cap-gated by `"tools" in resolved.caps`
(`use_native_tools`); the native system prompt drops the tool-line grammar (schemas carry the
contract) while the fallback prompt is untouched. Tool schemas for `.bind_tools()` are
generated from the same catalogs as the prompt (`tools.py:native_tool_schemas` +
`mcp_resources.py:resource_native_schemas`, combined in `chat_models.chat_native_schemas`).
The gateway emits a `tool_call` StreamChunk per complete call at end-of-stream (merged
`AIMessage.tool_calls`), so streaming granularity is unchanged. `Message` gained optional
`tool_calls`/`tool_call_id` (backward-compatible) for native round history. **Auto-degrade on
tool-unsupported errors LANDED (2026-08-26, follow-up):** a `tools`-capped model whose endpoint
rejects the bound-tools payload (real case: OpenAI "Function tools with reasoning_effort are
not supported for gpt-5.6-luna") degrades to the prompt grammar *for that turn* — the round is
immediately retried on the prompt path and the provider+model is remembered in-memory
(`chat_models._NATIVE_TOOLS_DEGRADED` / `use_native_tools`) so later turns skip straight to
the prompt path; the Settings `tools` override remains the durable fix. A **pre-stream provider
failure no longer persists an empty assistant message** — it re-raises so the frontend shows
the `turn_error` banner (mid-stream failures still persist the partial + `trace.stream_interrupted`).
Backend 602 tests green (+2).

## Part 3 — Structured outputs

## 37C — `.with_structured_output()` as a pre-validation layer (backend)

**Problem.** Finding #4: repair rounds are the only guard on JSON shape; capable providers can
enforce the schema natively and skip most repair.

**Design.**

- **Add `.with_structured_output(...)` to `TaskRunner`'s LLM call** (quizgen/exgen/flashcards/
  material compose) with Pydantic models mirroring the existing validator expectations, **only**
  when the model supports structured output (cap/`response_format` probe via LangChain's
  `supported` checks). LangChain picks the right mode per provider (JSON-schema, function
  calling, or tool calling) automatically.
- **Validators still run, always.** The schema guarantees shape; the deterministic validators
  (`parsing.py` + per-task `validate_*`) still run on every draft and the repair loop still
  exists for content-level failures (wrong math, distractor==answer, out-of-range mentions).
  The schema is a *fast path to the validators*, never a substitute (ADR-021/022).
- **Repair loop unchanged, just shorter.** On a schema-capable model the first round should be
  conformant; the loop's round cap and audit stay identical so the observability contract
  (repair_rounds in the trace) is comparable across models.
- **Fallback.** No-schema-support models keep the current parse+repair path verbatim.

**Accept.** On a schema-capable model, quizgen returns a conformant draft in round 0 (repair_rounds
≈ 0) yet still fails validation on content errors (a distractor equal to the answer still trips
the chain check); on a non-capable model nothing changes.

**Tests.** Backend: scripted responses → structured output requested when capable, not when not;
a content-invalid-but-schema-valid draft still enters repair and is rejected if unfixable;
audit/repair_rounds recorded identically. Frontend: none.

**As-built (37C, 2026-08-26).** Landed with two recorded deviations: (1) **The Pydantic
schemas are permissive, not strict.** The plan's "Pydantic models mirroring validator
expectations" is implemented as root wrappers with the known list key + element models with
`extra="allow"` and the known fields optional (`app/ai/structured.py`) — the schema guarantees
*shape* (a JSON object with the right root key) and *field-name guidance*, while the
deterministic validators remain the sole gate on content. A strict schema would reject unknown
keys and duplicate validator logic, risking valid drafts (per ADR-083/021/022 the schema checks
shape, validators check correctness). (2) **Scope is the `run_json` tasks, not material
compose** — compose is `run_text` (free-form markdown), which has no JSON schema to enforce;
37C lands for quizgen/exgen/flashcards/pattern.discover/rubric (all `run_json`).
`LLMGateway.generate_structured(task, messages, schema)` is cap-gated (`"tools" in caps`),
uses the same retry loop, and **degrades to plain `generate` on schema-unsupported errors**
(400/404/415/422 + schema-ish message → returns `None`; `TaskUnassigned` → `None`), so a
false-positive or an API that rejects `response_format`/function-calling never breaks
generation — it silently keeps today's behavior. `run_json(..., schema=)` calls it first and
falls back to `generate`+`extract_json_object` when it returns `None`; the repair loop, audit,
and round caps are untouched. Backend 595 tests green (+6).

## Part 4 — Cost observability & prompt caching

## 37D — Prompt caching + real token accounting (backend)

**Problem.** Finding #5: no caching, cost is an estimate.

**Design.**

- **Cache the stable prefix — provider-honestly, not as one fake-uniform feature.** The three
  caching models differ materially: OpenAI's prefix caching is **automatic** (nothing to
  enable — only cache-read tokens to account); Anthropic's `cache_control: {type:"ephemeral"}`
  is an **inline message kwarg** with breakpoint/min-token constraints (via `ChatAnthropic`
  `extra_body`/`model_kwargs`); Google's `cachedContent` is an **explicit cache-object
  lifecycle** (create/manage/TTL) with thinner LangChain support. D lands in that order —
  OpenAI cache-read accounting + Anthropic hints first; **Google explicit caching is descoped
  to a follow-up** (see Non-goals) rather than half-shipped behind a kwargs flag.
  `TaskRunner` skills and the resolver manifest get the same treatment where the provider
  bills cache reads.
- **Account cache hits.** `_ledger` records cached input tokens from
  `usage_metadata.input_token_details.cache_read` (normalized per provider) and discounts cost
  accordingly; the Settings→Tasks spend figures reflect the real number.
- **Retire the estimate.** `_estimate_tokens` is deleted everywhere except the offline/mock path
  (ADR-081 already threads real `usage_metadata` through). The `ai_interactions` token columns
  become real provider numbers.

**Accept.** A back-to-back tutor turn in the same session reports `cached_input_tokens > 0` and
lower cost on the second turn; spend in Settings→Tasks matches provider-reported usage.

**Tests.** Backend: scripted responses carrying cache-read usage → ledger records them and
cost discounts; cache hint params present on the chat/runner payloads (asserted via the
transport). Frontend: none.

**As-built (37D, 2026-08-26).** Landed as planned (provider-honest scoping): **OpenAI cache
accounting** + **Anthropic `cache_control` hints**; Google explicit `cachedContent` remains
descoped (non-goal). `to_langchain_messages(messages, cache_prefix=)` adds
`{"cache_control": {"type": "ephemeral"}}` to the *first* system content block only when the
task is in `_CACHED_TASK_NAMES` ({"chat"}) and the provider is anthropic — feedback/tool-result
system messages stay outside the cache (the invariant prefix is the first system block).
OpenAI prefix caching is automatic; its `prompt_tokens_details.cached_tokens` → `Usage.cache_read`
(threaded in 37A). The ledger now persists **`ai_interactions.cached_input_tokens`** (migration
**0037**) and discounts cost: cached input bills at `CACHE_READ_RATE = 0.1` × `cost_in`
(Anthropic's cache-read discount; a reasonable approximation for OpenAI's free/cheap cached
prefixes — Settings→Tasks spend reflects the discounted number). `_estimate_tokens` remains
only for the offline/mock path. Chat turns already carry the invariant prefix (system_base +
tool docs + context manifest) as the first system message, so back-to-back turns hit the cache.
Backend 596 tests green (+2).

## Non-goals (this round)

- **No LangGraph adoption** — reaffirmed: no stateful multi-node graph exists yet;
  `TaskRunner`'s linear repair loop and the chat's agent loop are not graph-shaped problems.
  ADR-029's revisit clause stays open for LangGraph; this round only removes the LangChain-core
  barrier so a later graph adoption is incremental (the risk-register "LangGraph churn" row
  stays).
- **No LiteLLM / no dedicated LLM proxy** — per user decision, LangChain is the framework; no
  extra process, no virtual keys, no proxy admin UI.
- **No CopilotKit / Vercel AI SDK / Pydantic AI swap** — the frontend React/WS streaming and the
  backend `TaskRunner` are not replaced; this round is transport + tool-call + schema + cost
  hardening *behind* the existing surfaces.
- **No provider auto-selection / smart routing / load balancing** — the single assigned model
  + optional `fallback_model_id` remain the routing model (user-owned engines, ADR-031).
- **No change to contract validators or the equivalence chain** — those are deterministic and
  framework-independent (ADR-021/022/008).
- **No new agentic behaviors, no autonomous tool execution** — tools stay deterministic,
  server-executed, read-only where they are today; HITL proposals (ADR-043) unchanged.
- **No embeddings migration** — the `embeddings` task keeps its current gateway path
  (`google batchEmbedContents` / openai `/embeddings`); migrating to `OpenAIEmbeddings` /
  `GoogleGenerativeAIEmbeddings` is a follow-on, not this round.
- **No Google explicit prompt caching (`cachedContent`)** — D lands OpenAI cache-read
  accounting + Anthropic `cache_control` hints only; Google's cache-object lifecycle
  (create/TTL/manage, weaker LangChain coverage) is a contained follow-up once the
  accounting lands, not a silently half-shipped kwargs flag.
- **No AG-UI re-wiring** — the plan-35/36 event vocabulary is untouched.

## Dependencies & suggested order

A short **pre-A spike** (research only — pick the pinned version set, verify reasoning-delta
kwargs + injected `http_client` on all four provider packages) gates A's dependency change;
nothing it produces is code yet. A is the transport swap and everything sits on it; land it
first, verify the suite is surface-preserving, then B/C can proceed independently (they both
consume A's `bind_tools`/`with_structured_output`/`usage_metadata` and share the cap-gating
helper). D needs A's real usage and can land last or in parallel with C. Only A touches the
dependency list; B/C/D are pure in-repo changes. Migration-free (no schema change) unless
`ai_interactions` needs a `cached_input_tokens` column (D — that would be a `ca-migration`
Alembic change, likely additive/non-blocking).

## Verification per slice

Standard suite before any commit (AGENTS.md): backend `ruff check . && mypy . && pytest`;
frontend `pnpm lint && pnpm typecheck && pnpm test && pnpm build`; docs synced via
`ca-docs-sync`; `ca-migration` only if D adds a column. ADR rows 081–084 appended to
`06-decisions-and-risks.md` as each slice starts (or all four at A's start, as the decisions are
made up front). Golden-set evals (`pytest tests/evals/`) must not regress — especially
`quizgen`/`exgen` content quality, which 37C touches indirectly.

**Live-model smoke check per slice (blocking, like a red suite).** The no-network suite —
correctly — cannot validate real-model behavior: native tool-calling quality, reasoning-delta
shapes, cache headers on real payloads; and the golden evals cover quizgen/exgen content,
not the chat tool path. Before a slice is called done, run its smoke against one real cloud
model *and* one local/Ollama model: **A** one streamed tutor turn with reasoning + a
wrong-key 401 (friendly 502) + confirm zero non-provider network egress; **B** "solve
sin(pi/6)" native `CALC` round-trip + the same prompt on a no-tools local model via the
prompt path; **C** one quizgen run (repair_rounds ≈ 0 on a schema-capable model) + one on a
non-capable model (unchanged path); **D** two back-to-back tutor turns — the second reports
cached input tokens and lower cost. Findings go into the plan's as-built notes; a failed
smoke blocks the slice exactly like a failing test.

## Risks

- **Dependency footprint & churn.** LangChain's split packages move fast and `langchain-core`
  has had breaking changes across majors, and the reasoning-delta kwargs vocabulary
  (`reasoning_content`/`thinking`/`thought`) itself drifts across provider-package releases.
  Mitigation: the pre-A spike pins a verified, mutually compatible version set; prefer the
  narrow `-provider` packages (not the `langchain` umbrella), CI lockfile audit, and the
  no-network CI guard. The `LLMGateway` surface is unchanged, so a revert to the hand-rolled
  gateway is a contained change (the escape hatch is the point).
- **Resilience is thinner than a dedicated gateway.** `.with_retry()`/`.with_fallbacks()` cover
  retries and fallback, but LangChain's 429/rate-limit backoff is *lighter* than LiteLLM's
  Router — no per-key RPM/TPM throttling, no circuit breaking. Mitigation: the exponential-jitter
  retry covers transient 429s; if real rate-limit pressure appears, add a small retry-after
  wrapper around the chat model (contained, inside the factory). Accepted trade-off vs the
  rejected LiteLLM route (recorded in ADR-081 alternatives).
- **Behavioral drift from a transport swap.** Streaming granularity, reasoning-delta timing, or
  error text could subtly change. Mitigation: surface-preserving swap + the existing gateway/
  streaming/budget/error tests as the regression gate, run *before* anything else in A.
- **Tool-calling quality varies by model.** Native calling may be worse than the prompt grammar
  on some mid-tier models. Mitigation: cap-gating + fallback path retained; a model can be
  pinned to the prompt grammar per-model if needed (a `tools` capability override already
  exists in Settings).
- **PyInstaller/packaging size.** LangChain's transitive deps may bloat the desktop bundle.
  Mitigation: check `scripts/` build output size in A; if unacceptable, defer to the packaging
  phase and note it as an open item rather than silently shipping a bloated bundle.

## Alternatives rejected

- **LiteLLM (SDK)** — a stronger, purpose-built gateway/transport (richer retry/rate-limit/
  fallback, built-in $ cost tables), and the author's original recommendation. Rejected per
  user preference for LangChain: the user wants the ADR-004 framework, its richer
  tool-calling + `with_structured_output()` story, and a one-step-away LangGraph path; the
  resilience gap is accepted and mitigated with `.with_retry()`/`.with_fallbacks()` + our own
  `cost_in`/`cost_out` ledger.
- **Big-bang LangGraph migration now** — replaces far more than the transport, adds a graph
  model none of the pipelines need yet, and contradicts ADR-029's own revisit clause
  ("when the first stateful graph lands"). LangChain-core first; LangGraph stays a contained
  follow-on.
- **Keep hand-rolled, add retries/backoff/rate-limit myself** — the ADR-029 continuation,
  smaller dependency-wise, but it re-implements, per provider, exactly what the LangChain
  `-provider` packages already do well (message normalization, streaming/reasoning, tool
  calling, structured output). The maintenance burden is the finding being fixed, not a
  feature. Honest caveat: plain retry/backoff is provider-agnostic and ~20 lines — if this
  round slips, closing finding #2's user-facing retry gap standalone is cheap and worth
  doing; it's the normalization surface that justifies the framework, not the retries.
- **`langchain` umbrella package** — pulls the whole integration surface for one app; the narrow
  `langchain-core` + four `-provider` packages give the same capability with less transitive
  surface.
- **Remove the prompt-tool fallback entirely** — violates ADR-006 (text-only models run every
  pipeline); local/Ollama models and some mid-tier models still need it.
- **Replace the deterministic validators with structured-output enforcement** — rejects
  ADR-021/022/008; the schema checks *shape*, the validators check *correctness* (equivalence
  chain, leak guard). The two are complementary, and the validators must always run.
