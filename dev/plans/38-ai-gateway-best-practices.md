# 38 — AI gateway best-practices alignment: provider parity, structured-output accounting & capability-aware fast path (ADR-085…087)

**Status:** COMPLETE (2026-08-26, user-approved from an audit of `gateway.py`/`chat_models.py`
against the LangChain docs; slices A→D landed as a single `feat(ai)` change — ADR-085…087,
backend 620 · frontend 706 tests green; as-built notes under each slice) ·
**Phase:** post-1.0 — AI infrastructure (hardening follow-up to plan 37) ·
**Suggested order:** A → B → C → D (all small; A and D are pure cleanups, B and C are
independent improvements on the 37C path)

## Summary

Plan 37 adopted LangChain chat models behind the gateway; the audit that followed
compared `gateway.py`/`chat_models.py` against current LangChain guidance and the
installed versions (langchain-core 1.6.0, openai 1.6.0, anthropic 1.6.1,
google-genai 4.3.5) and found four tractable gaps:

- **Google silently drops `reasoning_effort`.** The docs list `ChatGoogleGenerativeAI`
  as supporting the standard `reasoning_effort` parameter (needs google-genai ≥ 4.3.1 —
  installed 4.3.5), but `_google_model` (`chat_models.py:223`) never forwards it while
  OpenAI and Anthropic both do. A user's effort setting on a Gemini model is ignored.
- **`generate_structured` bills token estimates, not real usage.** The docs' `include_raw`
  mode of `.with_structured_output()` returns the raw `AIMessage` (with `usage_metadata`)
  alongside the parsed object; the current call (`gateway.py:330`) discards it, so the
  ledger (`gateway.py:344`) falls back to `len//4` estimates for every structured task.
- **Capability detection leans on error-string sniffing.** `_is_schema_unsupported`
  (`gateway.py:471`) greps provider error text for `"schema"`/`"not supported"` etc. The
  docs recommend reading capability from the model's profile (`model.profile
  ["structured_output"]`, models.dev-backed) — a false-positive `tools` cap currently costs
  a guaranteed-failing round trip before the sniff even runs.
- **Cleanups.** Stale `# type: ignore[call-arg]` on `ChatAnthropic` (its `reasoning_effort`
  is now a typed field), redundant re-imports inside `gateway.py` methods, and
  `_http_client` not setting `follow_redirects` like LangChain's own default clients.

**Deliberately NOT touched** (see Non-goals): the permissive Pydantic schemas in
`structured.py` (ADR-083 explicitly rejected strict schemas — shape vs. correctness stays
split), the `retry_attempts` name (documented semantics), the Anthropic/Google private-
attribute transport injection (the plan-37 spike established these as the only supported
seams and they are covered by tests), and Google's native SDK retry when no transport is
injected (a mild double-retry on transients, accepted).

## Context — findings (audit 2026-08-26)

1. **Reasoning-effort asymmetry.** `_openai_model` forwards `reasoning_effort`
   (`chat_models.py:185`); `_anthropic_model` forwards it via a `model_kwargs` splat with a
   stale `# type: ignore[call-arg]` (`chat_models.py:199-211`); `_google_model` ignores it
   entirely. Installed google-genai's `reasoning_effort` is
   `Literal["minimal", "low", "medium", "high"]` (alias `thinking_level`); values outside
   that set raise a pydantic `ValidationError` at construction — so the fix must filter to
   the Google-accepted set, or an Anthropic/OpenAI-only value (`none`/`max`/`xhigh`) would
   break every turn at model build time.
2. **`with_structured_output(include_raw=True)`** returns `{"raw": AIMessage,
   "parsed": <schema>, "parsing_error": None}` (langchain-core 1.6.0). All three partner
   `with_structured_output` overrides accept `include_raw`. The gateway currently passes no
   `include_raw`, so `usage_from_message` can't run and the ledger estimates.
3. **`model.profile` is real but not universal.** Verified: profiles load for known model
   ids (`gemini-2.5-pro` → `structured_output: True`; `claude-haiku-4-5-20251001` →
   `structured_output: False`; `claude-sonnet-4-6` → `True`), and are `None`/empty for
   unknown or openai-compatible ids (Ollama, DeepSeek, local gateways — most of the app's
   real endpoints). So a profile check is a **conservative pre-gate** (skip the fast path
   only when the profile *confidently* says `False`), never a replacement for the runtime
   degrade.
4. **The docs warn on the `CaChatOpenAI` use case** ("Non-standard response fields from
   third-party providers — `reasoning_content` — are not extracted or preserved. Use a
   provider-specific subclass"). That is exactly what `CaChatOpenAI` is, so it stays; it is
   the sanctioned workaround for arbitrary OpenAI-compatible gateways and is verified +
   tested in plan 37A.

## Reserved ADRs

| # | One-line decision |
|---|---|
| 085 | **`reasoning_effort` reaches every provider, filtered to each provider's accepted vocabulary.** Google gets it too — but only values in its `Literal["minimal","low","medium","high"]` (alias `thinking_level`); out-of-set values (OpenAI/Anthropic-only `none`/`max`/`xhigh`) are dropped so a cross-provider setting can never fail model construction |
| 086 | **`generate_structured` accounts real usage.** Use `.with_structured_output(schema, include_raw=True)`; ledger from `raw.usage_metadata` (tokens + cache_read), `parsed` for output; a `parsing_error` (or `parsed is None`) degrades to the plain-`generate` path exactly like an unsupported error |
| 087 | **Structured-output capability is pre-gated on `model.profile["structured_output"]` when the profile is present.** A confidently-`False` profile skips `.with_structured_output()` and tries the fallback chain without a guaranteed-failing round trip; unknown/absent profiles attempt and keep the error-based runtime degrade as the safety net |

## Slice 38A — Reasoning-effort parity (chat_models.py)

**Problem.** Finding #1.

**Design.**

- Add `_GOOGLE_REASONING_EFFORT_LEVELS = frozenset({"minimal", "low", "medium", "high"})`.
- `_google_model`: `if resolved.reasoning_effort in _GOOGLE_REASONING_EFFORT_LEVELS: kwargs["reasoning_effort"] = resolved.reasoning_effort`.
  Any other stored value is silently dropped (provider default) — same non-fatal semantics as
  "empty clears it back to the provider default" (migration 0038 changelog). Filtering is
  mandatory: google-genai's field is a pydantic `Literal`, and an invalid value raises at
  construction (verified: `"none"`/`"max"`/`"xhigh"` → `ValidationError`).
- `_anthropic_model`: drop the `model_kwargs` splat + `# type: ignore[call-arg]`; pass
  `reasoning_effort=resolved.reasoning_effort` directly when set (it is a typed field on
  `ChatAnthropic` ≥ 1.5.3; installed 1.6.1). mypy-strict must stay clean.
- OpenAI is already correct — untouched.

**Accept.** `build_chat_model` yields a Google model whose `reasoning_effort` is set for
`low/medium/high/minimal`, unset for `none/max/xhigh` (no crash), and the OpenAI/Anthropic
paths behave exactly as today.

**As-built (38A).** Landed as planned, plus one scope widening: Anthropic is **also**
filtered to its own `Literal` set (`max/xhigh/high/medium/low`) — the original code
forwarded any stored value via an untyped `model_kwargs` splat, which carried the same
latent pydantic `Literal` crash for an OpenAI value (`none`) stored on a Claude model. Both
models now build kwargs dicts and splat; the stale `# type: ignore[call-arg]` is gone and
mypy-strict stays clean. OpenAI remains unfiltered (its field is `str | None`; invalid
values surface as a provider 400, matching prior behavior). Tests: `test_gateway.py`
additions for google/anthropic in-set forwarded + out-of-set dropped via
`build_chat_model` (`transport=None`, no network).

**Tests.** `test_gateway.py` additions, all via `build_chat_model` + `MockTransport` (no
network): (a) google `reasoning_effort="high"` → constructed model field is `"high"`;
(b) google `reasoning_effort="max"` → model builds, field is `None`; (c) anthropic
`reasoning_effort="high"` → field `"high"` (also guards the type-ignore removal under
mypy). Existing `test_openai_reasoning_effort_sent_when_set` unchanged.

## Slice 38B — Real usage in `generate_structured` (gateway.py)

**Problem.** Finding #2.

**Design.**

- `generate_structured`: `structured = chat_model.with_structured_output(schema, include_raw=True)`.
- After `invoke`: if the result isn't a `{"raw", "parsed", "parsing_error"}` dict or
  `parsed is None` → return `None` (degrade to plain `generate`, same contract as a
  schema-unsupported error — the repair loop/validators remain the gate).
- `usage = usage_from_message(raw)` when `raw` is an `AIMessage`; pass `usage=usage` to
  `_ledger` (real tokens + `cache_read` discount, 37D behavior, for free).
- `dump_structured(parsed)` for the persisted output snippet — unchanged shape.

**Accept.** A structured task with `usage` in the response lands real `input_tokens`/
`output_tokens`/`cached_input_tokens` on the `ai_interactions` row (no `len//4`); a
provider that returns an unparseable response still degrades to `generate`.

**As-built (38B).** Landed as planned with one empirical refinement: the `parsed is None`
guard is a **provider-dependent** safety net. Verified: OpenAI's `json_schema` method parses
the response inside the openai SDK (`response.parse()`), so malformed JSON raises a
`pydantic.ValidationError` *before* the output parser — `include_raw`'s `parsing_error` is
never populated on the OpenAI path (pre-existing behavior, unchanged by this plan; the error
surfaces as a `ProviderError`, not a silent degrade). On Anthropic (function-calling) and
Google (json_schema via the output parser) the parse is done by LangChain, so
`parsing_error`/`parsed: None` is populated and the guard degrades cleanly. The guard is
therefore a strict improvement for those paths and a no-op safety net for OpenAI. Tests:
scripted OpenAI response with `usage` → ledger records `input_tokens == 10`,
`output_tokens == 5`; a stubbed `{parsed: None}` include_raw result → returns `None`.

**Tests.** `test_gateway.py` (uses `_migrated_factory`): scripted OpenAI-compatible
chat/completions response with `usage: {"prompt_tokens": 10, "completion_tokens": 5}` and
valid JSON `content` → `generate_structured("chat", …, QuizgenOut)` → `ai_interactions`
row records `input_tokens == 10`, `output_tokens == 5` (not estimates). Plus a unit for
the degrade branch (parsed `None` → returns `None`, no crash).

## Slice 38C — Capability-aware structured-output pre-gate (chat_models.py + gateway.py)

**Problem.** Finding #3.

**Design.**

- New `chat_models.structured_output_supported(model: BaseChatModel) -> bool`:
  `profile = getattr(model, "profile", None)`; return `False` only when `profile` is a
  Mapping and `profile.get("structured_output") is False`; otherwise `True`
  (unknown → attempt; the runtime degrade is the safety net). Explicitly **not** a hard
  rejection when the profile says `False` wrongly — worst case the fast path is skipped and
  the plain path answers (safe degradation, never a break).
- `generate_structured`: after `build_chat_model`, before `.with_structured_output()`,
  `if not structured_output_supported(chat_model): continue` (next fallback model; if none
  support it, the existing `return None` terminal fires). This turns a guaranteed-failing
  round trip into an instant skip on known-unsupported profiles (e.g. models.dev lists
  `structured_output: False`), and lets a genuinely-capable fallback model answer instead of
  the primary's dead 400.
- `_is_schema_unsupported` stays as the runtime fallback for profile-unknown endpoints —
  now reached only when no profile said `False` (brittleness reduced by reach, not removed).

**Accept.** A `tools`-capped model whose profile says `structured_output: False` is skipped
without a request; a fallback with real support answers; unknown-profile models behave
exactly as today.

**As-built (38C).** Landed as planned. `structured_output_supported` lives in
`chat_models.py` (returns `True` unless `model.profile` is a dict with
`structured_output is False`; `profile` is a provider-specific attribute, not on
`BaseChatModel` in langchain-core 1.6.0 — guarded with `getattr`). Tests: unit over fake
objects (missing/empty/True/False profiles) + integration via monkeypatched
`gateway.build_chat_model` (profile `False` → returns `None`, `.with_structured_output`
never called).

**Tests.** (a) Unit: `structured_output_supported` over fakes — `profile` missing /
`None` / `{}` → `True`; `{"structured_output": False}` → `False`;
`{"structured_output": True}` → `True`. (b) Integration: monkeypatch
`gateway.build_chat_model` to return a stub model (profile `False`) and assert
`generate_structured` returns `None` and the stub's `.with_structured_output` was never
called.

## Slice 38D — Cleanups (gateway.py, chat_models.py)

**Design.**

- Hoist `chat_native_schemas` / `stream_message_chunks` to the top-level `from .chat_models
  import …` in `gateway.py` and delete the redundant local imports in `generate_structured`
  and `_stream_model` (no circular-import reason for them — `chat_models` is already imported
  at module top).
- `_http_client`: add `follow_redirects=True` (matches LangChain's own default httpx clients;
  harmless, more predictable behind proxies).

**Accept.** No behavior change; suite green.

**As-built (38D).** Landed as planned (no deviations).

## Non-goals (this round)

- **No strict Pydantic schemas in `structured.py`** — ADR-083 explicitly rejected strict
  schemas (unknown keys would fail and duplicate validator logic); the permissive shape gate
  + deterministic validators remain the split. The audit's "make fields required" suggestion
  is out of scope by standing decision.
- **No rename of `retry_attempts`** — it means "total attempts" (loop `range(retry_attempts)`);
  semantics are documented in plan 37A as-built; renaming is API churn for zero behavior gain.
- **No change to the Anthropic `_client` / Google `client` transport injection** — the plan-37
  spike verified these private seams are the only supported way to inject `httpx.MockTransport`
  and the tests cover them; no public constructor param exists for Anthropic, and Google's
  constructor overwrites a passed `client`.
- **No Google native-retry suppression when no transport is injected** — the SDK's default
  retries are a feature (plan 37's own loop layers on top; mild double-retry on transients,
  accepted in ADR-081).
- **No `retry_attempts`/`retry_wait` threading into Google** — same reasoning as above.

## Dependencies & suggested order

All four slices are contained to `app/ai/chat_models.py` + `app/ai/gateway.py` + tests.
A and D are independent cleanups (land in any order). B and C both touch `generate_structured`
and must land without conflicting — B changes the `with_structured_output` call shape, C adds
the pre-gate above it; trivial to land sequentially. Migration-free (no schema change).

## Verification per slice

Standard suite before any commit (AGENTS.md): backend `ruff check . && mypy . && pytest`;
frontend untouched (no frontend change) but run `pnpm lint && pnpm typecheck && pnpm test &&
pnpm build` once at the end to confirm nothing regressed via shared types. Docs synced via
`ca-docs-sync` (STATUS changelog + module row + this plan + ADR rows 085–087). Golden-set
evals (`pytest tests/evals/`) must not regress — 38B touches the `generate_structured` output
path only cosmetically (parsed object is identical). No live-model smoke required: these are
transport-shape and accounting changes with scripted-transport coverage; the plan-37 smoke
check already validated real-model behavior and nothing here changes request payloads
(A: Google gains an optional field when a value is set; B/C: internal only).

## Risks

- **Google reasoning-effort values drift** across gemini model generations (the docs note
  supported levels "vary by model"). The filter is the safe intersection; a future model
  accepting only `low/high` would just have `medium` dropped — still non-fatal.
- **Profile data can be wrong/stale** (models.dev heuristics; e.g. it can list
  `structured_output: False` for a model that actually supports it). Pre-gate is conservative
  by design: a wrong `False` loses an optimization, never breaks generation.
- **`include_raw` shape change is a silent contract shift** — mitigated by the `parsed is
  None`/non-dict guard and the same degrade path; existing 37C tests (`test_structured_output.py`)
  run unchanged through the `StructuredFake` subclass, which bypasses the gateway internals,
  so the real-path behavior is pinned by the new scripted-transport test in 38B.

## Alternatives rejected

- **Pass Google `reasoning_effort` through unfiltered** — a stored `none`/`max`/`xhigh` would
  raise a pydantic `ValidationError` at model construction and fail every turn (verified).
- **Strict schemas in `structured.py`** (the audit's item 5) — contradicts ADR-083's explicit
  rejection; would duplicate validator logic and reject valid drafts on unknown keys.
- **Replacing `_is_schema_unsupported` with profile-only detection** — profiles are `None` for
  most real endpoints (Ollama, DeepSeek, local gateways); the runtime degrade must stay.
- **Renaming `retry_attempts` / reworking Google retry parity** — pure churn or a behavior
  change (SDK retries are native), neither justified by the audit.