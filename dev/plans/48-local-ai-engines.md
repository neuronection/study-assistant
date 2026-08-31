# Plan 48 — Local-first AI engines: llama.cpp / LM Studio presets, local embeddings, onboarding detection (user request 2026-08-31)

Status: planned (2026-08-31, user-approved) · Phase: post-1.0 · Suggested order: A → B → C → D

## Context

neuronection's family principles are *privacy-first, self-hostable, offline-capable
where possible*. Today the study assistant is **unusable until the user configures a
cloud API key**: Ollama is the only local preset, the onboarding wizard doesn't help
discover local engines, embeddings on Ollama are undocumented, and the open issue
"local-embeddings default (ADR-011: sentence-transformers/bge-m3) is not wired" has sat
open since Phase 1.

**User decision (2026-08-31):** local AI comes from **OpenAI-compatible engines the
user already runs** (llama.cpp server, LM Studio, Ollama, whisper.cpp server) — not
from bundling in-process models. This is architecturally right and I fully agree:

- The app is **already** provider-first (ADR-006/015, plan 37): every AI call resolves
  through a provider model. In-process torch/PaddleOCR/sentence-transformers would be a
  second, parallel model system — packaging pain (PyInstaller + torch ≈ +2 GB),
  GPU/driver support matrix, and a second cost ledger. OpenAI-compatible engines give
  the same offline result for **zero new heavy deps**.
- llama.cpp's `llama-server`, LM Studio and Ollama all expose `/v1/chat/completions`
  (incl. vision `image_url` parts), `/v1/embeddings`, and whisper.cpp/speaches expose
  `/v1/audio/transcriptions` — every capability the gateway needs, exactly the
  `openai_compatible` surface we already speak.
- This **permanently retires** the ADR-011 sentence-transformers clause: local
  embeddings = any local embeddings server via the `embeddings` task. No torch, ever.

**ADRs recorded as slices start:**

| # | Decision |
|---|---|
| 105 | Local AI = OpenAI-compatible engines only; **no in-process ML models, ever** (supersedes ADR-011's sentence-transformers/bge-m3 clause and closes its open issue) — local capability comes from presets + discovery + docs, not bundled runtimes |

## A — Provider presets for local engines (ADR-105)

**Problem.** `PRESETS` (`backend/app/ai/providers.py:29`) knows Google/OpenAI/
Anthropic/Ollama; llama.cpp and LM Studio users must hand-type base URLs and guess
key handling.

**Design.**

- Add presets: `llama_cpp` (`http://localhost:8080/v1`, name "llama.cpp (local)"),
  `lm_studio` (`http://localhost:1234/v1`, name "LM Studio (local)"); Ollama stays.
  Local presets: API key optional (empty allowed — keyring write skipped when blank;
  today a blank key on openai_compatible may already work — pin it with a test).
- `infer_caps` already detects `-vl`/`llava`/`gemma3` vision names and whisper STT
  names — extend hints with common local vision families (`qwen`+`vl` covers qwen-vl;
  add `minicpm-v`, `moondream`) and embeddings names (`nomic`, `minilm`, `gte`) so
  discovery labels local models correctly.
- Frontend: provider-create preset picker (shared `useProviderCreate` /
  `ProviderCreateFields`) gains the two presets — this is data, not new UI.
- **Provider "Test connection" row** (revision 2026-08-31): the Settings provider
  card gains a test action riding the library's `ConnectionTestRow` module (idle /
  testing / ok / fail + latency): probes `GET /v1/models`, and — when the
  discovered models include an embeddings-capable one — a single tiny embedding
  round-trip. Local engines are exactly where stale ports and wrong paths bite;
  a one-click probe beats a failed chat turn as the first signal.

**Accept.** Settings → Add provider → "llama.cpp (local)" with the prefilled URL and
empty key → models discover, caps look right.

**Tests.** Backend: preset registry contents, blank-key provider create + gateway
resolve without keyring entry, `infer_caps` additions. Frontend: preset picker shows
the new entries.

## B — Local engine detection in onboarding + settings (ADR-105)

**Problem.** A new user with Ollama/llama.cpp running still has to know what a "base
URL" is.

**Design.**

- `GET /providers/detect-local` (backend): probes candidate ports per preset
  (Ollama `:11434`, llama.cpp `:8080` **and `:8081`**, LM Studio `:1234`) —
  collision-prone ports, so a hit must **validate, not just answer** (revision
  2026-08-31): `GET /v1/models` must return an OpenAI-shaped `{data: […]}` list
  within ≤300 ms before it counts as a hit. Returns matches with the preset id +
  discovered model names. **localhost only, read-only, best-effort** — never
  blocks, never leaves the machine, result not persisted; the wizard calls it once,
  non-blocking, when the provider step opens.
- Onboarding **Provider step**: a "Detect local engines" button (and auto-probe once,
  silently, when the step opens) → one-click "Add llama.cpp" for each hit, flowing
  through the existing `useProviderCreate` advance-on-success path.
- Settings → Providers empty state gets the same button.
- The wizard's **Defaults step** already assigns capability defaults — its copy gains
  a local-mode hint when the only providers are local (`docs/usage/local-ai.md` link).

**Accept.** On a machine running llama-server with a vision model, the wizard's
provider step offers it by name; clicking it lands on the models step with the model
discovered and `vision` pre-checked.

**Tests.** Backend: probe happy/timeout/refused paths with a stub httpx transport
(socket-blocking suite guard stays intact — httpx mock, not real sockets). Frontend:
wizard step renders detection results and adds the provider.

## C — Verify the vision-OCR + embeddings paths against local engines (ADR-105)

**Problem.** The OCR path sends WebP `image_url` parts (plan 46) and embeddings use
`/v1/embeddings` — both must be *proven* against the local engines, not assumed.

**Design.**

- Manual verification matrix on this machine (llama-server with a `-vl` model, LM
  Studio, Ollama): scanned-page OCR, drawing OCR, dictation (whisper via
  openai_compatible), chat streaming + tool degradation, embeddings → hybrid search.
  Results recorded in STATUS; any breakage fixed in this slice (suspects: image mime
  handling, empty-Bearer auth header, `/v1/embeddings` shape differences — all
  gateway-local fixes).
- Settings → Tasks already shows per-task spend; local engines make it ~0 — add
  nothing, just verify the ledger rows read sensibly.

**Accept.** The "fully local setup" table in `docs/usage/local-ai.md` is checked off
per engine/feature with the versions used.

**Tests.** No new suites; regression coverage only if C finds and fixes a bug (each
fix lands with its test, as always).

## D — `docs/usage/local-ai.md` + positioning (ADR-105)

**Problem.** The "works offline / bring your own model" story is scattered across
README and chat docs; a newcomer can't assemble it.

**Design.**

- New `docs/usage/local-ai.md`: engine setup (Ollama, llama.cpp `llama-server` with a
  vision model, LM Studio, whisper.cpp server), recommended models per capability
  (text/vision/embeddings/audio), the wizard path from zero, cost = zero, limitations
  (tool-calling quality varies → the prompt-grammar fallback; vision OCR quality
  depends on the model).
- README "What's different" gets a "Runs fully local" bullet linking the guide; the
  hub brochure page (neuronection repo) already advertises local-first — leave it.
- STATUS open-issues: the ADR-011 local-embeddings entry is rewritten as **resolved by
  ADR-105** (superseded; see plan 48).

**Accept.** A reader follows the guide on a clean machine and reaches a working,
keyless app.

**Tests.** None (docs slice); translation-readiness not touched (English keys only).

## Non-goals (this round)

- Bundling/starting local engines from the app (the user owns engine lifecycle).
- In-process embeddings/OCR models (ADR-105: never; the open issue closes).
- Ollama-native `/api/embed` (non-OpenAI shape) — `/v1/embeddings` suffices; revisit
  only if a capability proves unreachable via the OpenAI surface.
- Model download/progress management (engine territory).
- GPU/driver diagnostics UI (engines own that; we surface their errors).

## Dependencies & suggested order

A → B (B's detection returns preset ids from A) → C (needs A/B to verify) → D
(documents C's verified matrix). C can start as soon as A lands.

## Verification per slice

Backend: `ruff check . && mypy . && pytest` · Frontend: `pnpm lint && pnpm typecheck &&
pnpm test && pnpm build`. Docs duty: `docs/ai.md` (local engines section pointer),
`docs/STATUS.md` changelog per slice, README bullet in D.
