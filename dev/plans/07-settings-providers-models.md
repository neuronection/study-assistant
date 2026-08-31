# 07 — Settings: Providers, Models, Task Assignment

User-configurable AI engine layer. Nothing is hardcoded: the user registers providers,
discovers their models, and maps models to tasks. Three tabs in Settings.

```
┌─ Settings ──────────────────────────────────────────────────────────────┐
│ [ Providers ] [ Models ] [ Tasks ]                                      │
│                                                                         │
│  Providers                                    [+ Add provider]          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ ● Google Gemini            generativelanguage.googleapis.com      │  │
│  │   key sk-…a19c · tested 2m ago ✓ · 43 models · [Test] [Edit] [⋮]  │  │
│  │ ● Ollama (local)           http://localhost:11434/v1              │  │
│  │   no key · tested 1h ago ✓ · 5 models · [Test] [Edit] [⋮]        │  │
│  │ ○ OpenRouter               https://openrouter.ai/api/v1           │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

## Tab 1 — Providers

A provider = one account/endpoint. Adding one is a small wizard:

| Field | Notes |
|---|---|
| Name | user label ("Google Gemini", "Ollama on laptop") |
| Type | `google` · `openai_compatible` · `anthropic` — Add dialog offers **presets**: Google Gemini, OpenAI, Anthropic, **Ollama (local)** (pre-fills `openai_compatible` + `http://localhost:11434/v1`, no key, auto-detects a running instance) |
| Base URL | shown for `openai_compatible` (covers OpenAI, Ollama `/v1`, LM Studio, vLLM, OpenRouter, Groq, DeepSeek, Together…); fixed defaults for `google`/`anthropic`, overridable (proxies) |
| API key | write-only; stored in **OS keyring** under `CourseAssistant/provider:{id}`; UI shows masked `sk-…a19c` only. Empty key allowed (local servers) |

- **[Test]** button → connectivity + auth check + (if OK) triggers model discovery.
- Status line per provider: last tested, ok/error message, model count.
- Provider can be disabled without deleting (models hidden from Tasks tab).
- Deleting a provider: its models are removed; task assignments referencing them become
  *unassigned* (warning banner on Tasks tab, pipelines that need them refuse to run and
  deep-link to Settings).

## Tab 2 — Models

Per provider (sub-tabs or grouped list): **auto-fetched catalog** + user enable checkboxes.

- Discovery per type:
  - `openai_compatible` → `GET {base}/models` (works for OpenAI, Ollama, LM Studio, vLLM, OpenRouter…)
  - `google` → `GET /v1beta/models` (filter to generation methods: chat/GenerateContent)
  - `anthropic` → `GET /v1/models`
- [Refresh] re-fetches; upsert by `external_id`; models that vanished get flagged
  `missing` (kept listed, dimmed, with note) so assignments aren't silently destroyed.
- Per-model row: enable toggle, label, detected **capabilities** (text / vision / tools /
  embeddings), context window, cost per 1M tokens in/out (user-editable — feeds the cost
  dashboard).
- Capability inference is best-effort (name/metadata heuristics: `gemini-*`, `gpt-4o*`,
  `claude-3*`, `*-vl`, `llama*vision*` → vision; `*-embedding-*`, `text-embedding-*`,
  `bge-*` → embeddings). **Always user-overridable via an edit dialog** — heuristics
  only pre-fill checkboxes. Unknown → assume `text` only.
- Enabled models are the only ones selectable in Tasks.

## Tab 3 — Tasks

Fixed task list from the AI layer (see 04). Each row: task name, description,
**model dropdown** (enabled models, grouped by provider), optional **fallback model**,
advanced per-task params (temperature etc., collapsed).

**As-built (2026-08-26, ADR-088): per-capability defaults + per-task override.** A
pinned **Default models** section at the top sets one primary (and optional fallback)
model per capability — `text` / `vision` / `embeddings` (`default_task_assignments`
table). Every task row's dropdown starts at **"(Inherit default)"** (its effective
model = the capability default); picking a specific model turns the row into an
override; clearing it inherits again. Gateway resolution null-coalesces
`task.model_id ?? default(requires).model_id` (same for fallback).

| Task | Needs | Notes if unmet |
|---|---|---|
| ocr | vision | hard requirement — dropdown offers vision models only |
| notes_ocr | vision | hard requirement — vision models only |
| description, outline, quizgen, tutor, grade, chat, flashcards | text | any model; if text-only chosen, images are injected as their OCR extraction (OCR-first normalizer, doc 04) — info note shown |
| embeddings | embeddings capability | embedding models only (local sentence-transformers remains the default option) |

UX rules:

- Assigning a model marks the row with capability badges; mismatches warn inline
  (OCR ← text model is *blocked*; chat ← text model is *fine*, just noted).
- "Suggested setup" button when nothing is assigned and a Google provider is connected:
  one click assigns `gemini-2.5-flash` everywhere (the doc-04 default mapping).
- Per-model override of cost/caps propagates to cost tracking immediately.
- Validation endpoint returns task-requirement metadata so the UI never hardcodes rules.

## API surface

```
GET    /api/v1/providers                      list (masked keys, status)
POST   /api/v1/providers                      create (key → keyring) + auto-test
PATCH  /api/v1/providers/{id}                 edit (key optional on update)
DELETE /api/v1/providers/{id}
POST   /api/v1/providers/{id}/test            connectivity/auth check
GET    /api/v1/providers/{id}/models          remote discovery (fresh fetch)
PATCH  /api/v1/models/{id}                    enable, caps, costs, label
GET    /api/v1/tasks                          task defs + requirements + assignments
PUT    /api/v1/tasks/{task}                   { model_id, fallback_model_id, params }
GET    /api/v1/tasks/defaults                 per-capability defaults (ADR-088)
PUT    /api/v1/tasks/defaults/{requires}      { model_id, fallback_model_id }
```

Backend resolves `task → model → provider` at call time through the `LLMGateway`
(registry is a thin cache over these tables; provider/key lookup incl. keyring read
happens per call, so edits apply instantly with no restart).

## Schema additions (doc 03)

```
providers         id, name, type(google|openai_compatible|anthropic), base_url,
                  keyring_ref, enabled, status(json), created_at
models            id, provider_id FK, external_id, label, caps(json),
                  ctx_tokens, cost_in, cost_out, enabled, missing(bool),
                  discovered_at, last_seen_at
                  UNIQUE(provider_id, external_id)
task_assignments  task(PK), model_id FK, fallback_model_id FK nullable, params(json)
default_task_assignments  requires(PK: text|vision|embeddings), model_id FK,
                  fallback_model_id FK nullable     (0041, ADR-088)
```

API keys never touch the DB or logs. Migration seeds nothing; first-run onboarding
offers the provider wizard + "suggested setup".

## Behavioral integration

- `LLMGateway.get_model(task)` reads assignment → model → provider (with fallback chain:
  assigned → fallback → error "task unassigned, configure in Settings").
- Response cache keys include provider+model+prompt hash — swapping models per task stays
  safe and re-runs are still cached per model.
- Cost dashboard (H7) groups by task × model × provider using user-entered rates.
- Offline mode: if the assigned provider is unreachable, tasks with an Ollama/local
  fallback run degraded; otherwise features show a clear "provider offline" state.

## Related

A fourth Settings tab — **Skills** (per-task prompt/behavior editing with contracts) — is
specified in [08-skills-and-prompts.md](08-skills-and-prompts.md).
