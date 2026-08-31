# 14 — AI Task Layer & Context Engine (Phase 10)

User decision (2026-08-20, ADR-042): one uniform way to invoke AI generation tasks
(quiz/exercise/flashcards/…) with **explicit, inspectable context** — materials opt-in/out,
notes, concepts, per-node AI hints — plus a modular **context resolver** that every AI
caller (pipelines now; chat + MCP later) shares. Builds on ADR-039 scoping; chat's
existing RAG behavior is untouched in this phase (10E later).

## Findings that motivate this (2026-08-20 audit)

- 16 AI call sites hand-roll: JSON extraction (7×), repair loop (6×, rounds drift 1–3),
  skill-resolution boilerplate (7×), token estimation (5×), blocks→md (4×, `$` vs `$$`
  inconsistent), duplicated system prompts (pipelines vs skill seeds — drift risk).
- Context assembly is ad-hoc per caller (quizgen `[n]`[:1000]×16, exgen [:900]×12, chat
  [:1200]×8); only chat gets notes; nothing gets node summaries/objectives/concepts.
- `retrieve_chunks` ignores `embed_query` — chunk retrieval is FTS-only despite STATUS
  claiming hybrid RAG (material-level `hybrid_search` is the only true hybrid path).
- Audit rows inconsistent: organizer/concepts/outline/notes_ocr write only the gateway
  ledger row; quizgen's audit row lacks model/latency.
- Frontend: 5 generate surfaces with different param sets; `concept_id` and
  `material_id` generate params exist but are never sent by any UI; nothing previews
  what context will be sent.

## Design

### ContextResolver (`app/services/context.py`)

```python
class Scope(str, Enum):
    node = "node"        # direct material links of the node only
    subtree = "subtree"  # node + descendants (current roll-up default)
    course = "course"    # whole course (root) — no material filter

class ContextSpec(BaseModel):
    course_id: int
    node_id: int | None = None
    scope: Scope = Scope.subtree
    include_material_ids: list[int] = []
    exclude_material_ids: list[int] = []
    note_ids: list[int] = []
    concept_ids: list[int] = []
    hint: str | None = None          # one-off instruction for this call
    query: str | None = None         # retrieval query (defaults to topic/node title)
    max_chunks: int = 12
    chunk_chars: int = 1000
```

`ContextResolver.resolve(spec) -> ContextBundle`:

- material set = (scope links ∪ include) − exclude, validated intra-course; `[]` when a
  non-root scope has nothing (same "no chunks" edge as today; include_ids can rescue).
- **Chunk-level hybrid retrieval** (new `retrieve_chunks_hybrid` in `services/search.py`):
  FTS ranking (existing path) RRF-fused with sqlite-vec chunk vectors when an embedding
  for the query exists; graceful FTS-only fallback when vectors/embeddings absent.
- **Node header**: node title/summary/objectives + breadcrumb; **AI hints** =
  `ai_hint` of the node and every ancestor (root hint = course-level guidance), plus
  the one-off `spec.hint`.
- **Manifest**: stable handles `[M3] title`, `[N1] note title`, `[C2] concept — desc`
  from index cards (materials), note bodies (budgeted), concept rows.
- `render_prompt()`: budgeted numbered sections (Sources / Notes / Concepts /
  Instructions) — one implementation replacing the three hand-rolled variants.
- `stats()`: counts + titles for the UI preview.

Notes selection is **explicit** (`note_ids`) — the implicit "latest 3 notes" slot stays
chat-only until 10E.

### TaskRunner (`app/ai/runner.py`)

```python
runner.run_json(
    *, task, skill_key, course_id, fallback_system, render_vars, prompt,
    validate: Callable[[dict], list[str]], max_rounds=2,
    audit: AuditRef(context_type, context_id, direction),
) -> TaskRunResult  # draft, problems, rounds, skill_version_id, model_label
```

- resolves the skill via SkillService (fallback constant), renders vars, runs the
  repair loop with the caller's validator, writes the uniform app-level audit row
  (model label, skill_version_id, token estimates, latency_ms measured).
- `app/ai/parsing.py` collects: `extract_json_object`, `strip_code_fence`,
  `blocks_to_md` (single `$…$` inline-math convention), `estimate_tokens`.
- Pipelines keep validators/persistence; they lose their loop/skill/audit/JSON code.
  The duplicated pipeline system-prompt constants are deleted — skill seeds are the
  single source.

### AI hints (10C)

- Migration 0021: `tree_nodes.ai_hint TEXT` (root = course-level hint).
- `NodeUpdate` + `update_node` + tree/workspace payloads carry it; UI edits it in the
  workspace overview ("AI instructions for this node").
- Injection: every task call scoped inside a node's subtree inherits that node's and
  its ancestors' hints (course root first, most-specific last).

### API (10C)

- `POST /quiz/generate`, `/exercises/generate` gain `scope`, `include_material_ids`,
  `exclude_material_ids`, `note_ids`, `concept_ids`, `context_hint`. Concept focus
  accepts `concept_ids` list (first = topic). Flashcards generate gains `context_hint`
  only (its source model is already explicit).
- New `POST /ai/context/preview` (same spec) → manifest stats + truncated rendered
  context — powers the UI preview; no LLM call.

### Frontend (10D)

- `features/ai/GenerateDialog.tsx` — one schema-driven dialog (presets: quiz /
  exercise / flashcards): task params (count/difficulty/topic/steps/source), scope
  selector (this node / subtree / whole course), materials opt-in/out picker
  (in-scope checked, uncheck = exclude, extra checks = include — MaterialPickerDialog
  interaction patterns), notes + concepts multiselect, one-off hint field, and a
  **context preview** (debounced `/ai/context/preview` → counts + expandable text).
- Surfaces rewired: PracticeTab quiz inline form + exercise GenerateDialog +
  FlashcardsPage/CardsTab GenerateCard → presets of the uniform dialog (old
  components retired). One-click actions ("Study here", palette, HomePage, NoteEditor
  "Make flashcards") keep defaults.
- Workspace overview gains the per-node AI-hint editor.

## Slices

- **10A** resolver + hybrid chunk retrieval + parsing utils + tests
- **10B** TaskRunner; quizgen/exgen/flashcards migrated (behavior-identical; suites green)
- **10C** migration 0021 + node API/payloads + generate-endpoint params + preview endpoint
- **10D** uniform GenerateDialog + rewire surfaces + hint editor + tests
- **10E (deferred)** chat on manifest + `read_item` tool; MCP shares the resolver

## Verification

Existing suites stay green (quiz/exgen/flashcards API tests unchanged in behavior);
new tests: resolver scoping/include-exclude/hints/budget/hybrid-fallback, endpoint
param plumbing (excluded material absent from prompt — fake-gateway capture), preview
endpoint, frontend dialog presets + preview + opt-out flow.
