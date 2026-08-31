# 15 — AI-Native Companion: entity references, HITL action cards, AI-composed material (Phase 11)

User decision (2026-08-20, ADR-043): the AI becomes a first-class actor in the study
workbench — it can *reference* existing items with clickable cards, *propose* actions
a human approves, and *compose* new material — all through the Phase-10 task layer,
never around it. This doc inventories what exists, names the gaps, and slices the work.

Amended 2026-08-20 after plan review: session-stable chat handles, READ round budget
split from math tools, proposal execute-time revalidation + dismissal feedback, compose
self-exclusion (ai-composed never grounds new compositions) with advisory sampled math
lint, 11C split into 11C1/11C2, ADR-042/043 recording (Step 0), and P6 — one shared
component system with a modern surface built strictly on the existing stack (shadcn,
Tailwind 4 tokens, framer-motion; no new frontend dependencies).

## 1. What AI can do today (verified 2026-08-20)

| Capability | Task | Where it lives | State |
|---|---|---|---|
| Page OCR (PDFs/scans → markdown+LaTeX) | `ocr` | ingest pipeline | done |
| Handwriting OCR (drawings, quiz answers) | `notes_ocr` | notes + `/quiz/recognize` | done |
| Material index cards (summary/topics/terms) | `description` | postprocess job | done |
| Chunk embeddings + hybrid search | `embeddings` | postprocess + search | done (task assignment UX gap) |
| Course outline draft (→ review → commit) | `outline` | workspace Structure card | done |
| Concept graph extraction (→ commit) | `concepts` | Concepts tab | done (assignment often unassigned) |
| Quiz generation (validated, repair loop) | `quizgen` | GenerateDialog | done, Phase-10 context |
| Exercise generation + variants + drills | `exgen` | GenerateDialog, Practice tab | done, Phase-10 context |
| Flashcards (notes/material/mistakes) | `flashcards` | GenerateDialog | done, Phase-10 context |
| Node organizer: review/cheatsheet/draft-note | `description` | workspace overview | done |
| Note actions: summarize/cleanup/explain/expand | `description` | note editor | done |
| Chat RAG: scoped retrieval, citations, grounding flag, streaming | `chat` | chat sidebar / tutor tab | done |
| Chat math tools CALC/SYMPY (sandboxed, verified) | — | chat tool loop | done |
| Tutor hint ladder 1–5 + quiz-question help (leak-guarded) | `tutor` | exercise player, quiz runner | done |
| Context engine: scope/opt-in-out/notes/concepts/ai_hints + preview | — | resolver + GenerateDialog | done (Phase 10) |
| Per-node AI instructions inherited down the tree | — | `ai_hint` | done (Phase 10) |
| MCP read-only resource server (7 tools, external agents) | — | `python -m courseassistant mcp` | done |
| Tool catalog UI (chat wrench button) | — | `/ai/tools` | done |

**What it cannot do (the gaps this phase closes):**

1. **No referencing in output.** The model *sees* `[M12] Lecture 3` handles in its
   prompt (Phase-10 manifest) but nothing teaches it to *use* them in answers; chat
   citations are the only clickable thing in the app; explanations/notes/drafts are
   plain markdown with zero links into the workspace.
2. **No on-demand context.** Chat injects up to 8 fixed chunks; the model cannot ask
   "show me the full note N3" — long material is truncated away (10E, deferred).
3. **No HITL actions.** When the tutor says "you should review the chain rule", the
   student re-types everything. The AI cannot *propose* "create a note with this
   summary / assign this material to the node / generate a 5-question drill".
4. **No AI-composed material.** Cheatsheets and drafted notes exist but are one-off
   artifacts; the AI cannot create a *real, indexed, citable, assignable* study-guide
   material from course content.
5. **Solidity gaps** (§6): chat retrieval still FTS-only, skills whitelist too narrow,
   two tasks often unassigned with no guidance, `grade.freeform` seeded but unused.

## 2. Design pillars

### P1 — Entity mentions everywhere (one protocol)

The Phase-10 manifest already hands the model stable handles. Formalize the other
direction: **the model may mention entities by handle; the backend resolves, the
frontend renders clickable cards.**

Handle registry per AI call = everything the ContextBundle contained (materials
`[M#]`, notes `[N#]`, concepts `[C#]`) **plus** the scope node `[T#]` with its
children, and (quiz/exercise contexts) `[Q#]`/`[E#]`. The registry is built by the
resolver (`ContextBundle.mentions()`), serialized into the prompt ("you may refer to
these as [M12] etc."), and stored with the call for output parsing.

**Session-stable in chat**: the registry accumulates over the session — a handle is
assigned once and never renumbered, so `[M12]` means the same item in turn 1 and in
turn 10 even as retrieval shifts between turns. Each message stores its resolved
refs, and rendering resolves from the message, never from current state. All other
tasks keep per-call registries.

- **Parser** (`app/ai/mentions.py`): regex `\[([MNC TQE])(\d+)\]` over model output →
  resolve against the call's registry (unknown/out-of-course handles are left as
  literal text, never crash, logged as repair feedback `mentions_in_range` — mirrors
  `citations_in_range`).
- **Storage**: chat messages get `mentions` JSON (resolved refs) next to
  `citations`; quiz explanations / exercise steps / AI-drafted notes store mentions
  in their blocks as inline tokens the renderer understands (`{"type":"mention",
  "ref":"M12","title":…}` — added to the block family + BlockRenderer).
- **Frontend**: `EntityMention` chip component (kind icon + title, hover tooltip
  with summary) that routes: M → `/library/$id`, N → note drawer, C → concepts tab,
  T → node workspace, Q/E → runner/player. One component used by chat bubbles,
  BlockRenderer, and explanation panels.
- Mentioning is *taught* in the shared skill prompts (seed update, one line each)
  and validated by a new contract constraint (advisory first round, not blocking).

### P2 — On-demand context for chat (10E, finally)

Replace the fixed "8 chunks" prompt with **manifest-first + READ tool**:

- Prompt carries the manifest (titles + index-card summaries + note titles, small)
  and *no* full chunks by default; retrieval still seeds 4–6 chunks for the actual
  question (RAG stays for grounding/citations).
- New tool line `READ <handle>` (e.g. `READ M12` or `READ N3`) executed
  deterministically like CALC/SYMPY: fetch the item's content (extraction markdown /
  note body / concept row), char-budgeted (4k default), fed back as a system message.
  **READ has its own round budget** (up to 3/turn) on top of the existing 2 math
  rounds — "read two things, then verify with SYMPY" must not exhaust a shared cap;
  the per-turn total stays capped. READ results are model-only: stripped from the
  stored message and final answer exactly like CALC/SYMPY tool lines (the context
  panel is the user-visible record of what was read — a 4k fetch can never leak into
  a bubble). Unknown/out-of-scope handle → error line back to the
  model (it learns to pick from the manifest).
- Chat migrates to `retrieve_chunks_hybrid` (closes the FTS-only gap) and shares the
  resolver for scope/material filtering — one context pipeline app-wide, as ADR-042
  intended.
- **Context panel** in the chat sidebar (collapsible "What the AI sees"): session
  scope chip, auto-context list (latest-notes slot stays), per-turn manifest with
  READ indicators ("read Lecture 3 fully"). No hidden context — the Phase-10
  promise extended to chat.

### P3 — HITL action cards (propose → human approves → execute)

The model may end a chat turn with **structured proposals**, validated by the
contracts engine, rendered as cards with Approve / Dismiss — nothing executes
without a click.

- **Protocol**: a fenced block the model may emit once per turn:
  ```` ```proposal {"action":"create_note","title":…,"body_md":…,"node_id":…} ``` ````.
  The chat contract validator checks it against a **whitelisted action schema**
  (pydantic models per action; unknown action / bad target = violation → repair, or
  stripped with a notice if repair fails).
- **Storage/audit**: `chat_proposals` table (message_id, action, payload JSON,
  status `proposed|approved|dismissed|executed`, result ref, created/executed_at);
  every execution audited to `ai_interactions` (`context_type=proposal`).
- **Execute-time revalidation**: approval may come minutes later and state may have
  moved — the click re-runs the target service's validators against *current*
  state. Already-satisfied actions (material already assigned, concept already
  covered) complete as `executed` with a no-op note; invalid targets (node deleted)
  mark the card stale with an explanation — never a silent failure.
- **Dismissal feedback**: after 2 dismissals in a session, the system prompt gains
  "the user dismissed earlier proposals" and new cards render collapsed by default.
- **Phase-11 actions** (all through existing services — no new write paths):
  `create_note` (notes service, provenance tag `ai-proposal`), `assign_material`
  (material_links), `cover_concept` (node_concepts), `set_node_ai_hint`,
  `generate_quiz`/`generate_exercise` (does NOT auto-run: card renders the
  GenerateDialog *prefilled* — parameters are the proposal; the human click is the
  approval), `compose_material` (P4 — card shows brief + scope, opens compose
  confirmation).
- **Frontend**: `ProposalCard` in the chat stream (icon, one-line summary, expandable
  payload preview, Approve/Dismiss); approved `create_note` deep-links to the note
  drawer; toast + deep-link for every executed action. Node/course targets render as
  `EntityMention` chips inside the card.

### P4 — AI-composed material (`material.compose`)

The AI creates real study documents — indexed, searchable, citable, assignable,
printable — not throwaway artifacts.

- New task `material.compose` (+ TaskDef row + settings assignment; text-capable).
- Pipeline on the TaskRunner: input = brief (title, kind, instructions) +
  ContextBundle (any scope, **excluding `ai-composed` materials by construction** —
  the resolver filters them so a composition never grounds on a prior composition;
  chat retrieval keeps them: they are your study docs) → markdown draft (blocks) →
  **deterministic validators** (non-empty, min/max length, mention handles in
  range, math lint **advisory + sampled** — a few formulas per document, not a
  full-document equivalence pass; the chain is built for answer checking, not
  prose) → repair loop → persist via
  `MaterialsService.create_text` (`.md` material, `provenance=ai-composed`, author
  note in header) → the standard ingest pipeline indexes it (chunks/FTS/embeddings/
  index card) → **auto-assign to the scope node** (material_link rationale
  "AI-composed from …").
- Composed materials are visually distinct (AI badge in library + workspace rows),
  editable like any material (extraction QA), deletable; mentions inside them render
  as EntityMention cards.
- **Entry points**: workspace overview "Compose study material" (brief dialog on the
  GenerateDialog chassis — scope picker + context preview included), chat
  `compose_material` proposal card, tutor "save this explanation" (post-session, on
  the transcript footer).
- Kinds seeded: study guide (structure + explanations + worked examples), summary
  sheet (cheatsheet-as-material — supersedes the one-off organizer cheatsheet later),
  practice set with answers (as printable material, distinct from real quizzes),
  error-pattern recap (from the mistake notebook).

### P5 — Companion glue (small, high-value)

- **Tutor session summaries**: on exercise completion, offer a proposal card
  (`create_note` with the transcript's key mistakes + hints used).
- **Today screen**: next-best-action cards may carry a one-tap "ask the tutor about
  {weak concept}" (pre-scoped chat session) next to drill/challenge.
- **Skills UI**: the sandbox test-run gains the mention registry + proposal validator
  so prompt authors can test the full protocol, not just text.

### P6 — One component system, modern surface (frontend)

**Modular by default**: all Phase-11 UI is assembled from a small set of shared
primitives in `frontend/src/features/ai/`, imported by chat, workspace, note editor,
and library alike. No feature-local variants of the same concept (acceptance-greppable).
Backend mirrors this: mentions parsing, proposal schemas, and READ execution are
small single-purpose modules next to the existing tool/skill code.

- `EntityMention` — the one reference chip: kind→icon/color map, hover tooltip with
  summary, router link per kind (M→library, N→note drawer, C→concepts tab, T→node
  workspace, Q/E→runner/player), keyboard-focusable. Used by chat bubbles,
  BlockRenderer mention tokens, ProposalCards, and context-panel rows.
- `AiBadge` — one provenance badge: library rows, workspace rows, chat header,
  composed materials.
- `ProposalCard` — shadcn Card composition (no bespoke chrome): status badge
  (proposed/approved/dismissed/executed), one-line summary, expandable payload
  preview, Approve (primary) / Dismiss (ghost) with a pending spinner; targets
  render as `EntityMention` chips inside the card.
- `ContextPanel` — collapsible "What the AI sees" disclosure; rows reuse
  `EntityMention` plus a READ-activity line ("read fully").
- `MentionToken` joins the block family — BlockRenderer stays registry-driven.
- The compose dialog rides the **GenerateDialog chassis** (schema-driven fields,
  scope picker, context preview) — no parallel dialog code.
- **Modern polish on the existing system only** (Tailwind 4 semantic tokens + shadcn
  + framer-motion; no new dependencies): entrance/expand micro-interactions on
  cards, animated disclosure chevrons, skeleton rows for the debounced context
  preview, toasts with deep-links (and undo where the service supports it),
  dark-mode via tokens, aria labels + i18n keys for every new string
  (`no-literal-string` — keys are slice deliverables, not afterthoughts).

## 3. Slices (each shippable, in order)

- **Step 0 — records**: record **ADR-042/ADR-043** in `06-decisions-and-risks.md`
  (doc 06 currently ends at ADR-041) and fix `docs/STATUS.md`'s stale "32 ADRs"
  count. No code.
- **11A — Mentions**: session-stable registry in resolver + parser + `MentionToken`
  block type + `EntityMention`/`AiBadge` primitives (`features/ai/`) + chat/
  explanations rendering + seeds teach it + `mentions_in_range` constraint
  (advisory; rollout signal = violation rate from audit). Tests: parser ranges,
  render links, unknown-handle safety, handle stability across turns.
  Deliverables: i18n keys, golden mention fixture.
- **11B — Chat on-demand context**: READ tool (own round budget, model-only
  results) + hybrid retrieval + shared resolver + `ContextPanel` + tool catalog
  auto-includes READ + catalog-generated prompt doc (single source). Tests: READ
  fetches only in-manifest items, scope respected, panel data endpoint, budget
  cap, no READ leakage into stored messages.
- **11C1 — HITL proposals core**: schema whitelist + contract validation +
  `chat_proposals` table + `ProposalCard` + approve/dismiss endpoints + audit +
  `create_note` only. Tests: proposal validation (good/bad/unknown), execution
  happy path, no-execution-without-approval (server refuses unapproved payload
  execution), audit rows; golden proposal fixture.
- **11C2 — Proposal actions**: assign_material / cover_concept / set_node_ai_hint +
  generate-*=prefilled-dialog behavior + execute-time revalidation (no-op + stale
  paths) + dismissal feedback. Tests: per-action happy paths, revalidation
  (already-satisfied, deleted target), dismissal feedback.
- **11D — Compose**: task + pipeline (resolver excludes ai-composed; advisory
  sampled math lint) + compose dialog on the GenerateDialog chassis + auto-assign +
  provenance/AiBadge + chat `compose_material` proposal + tutor save-explanation.
  Tests: end-to-end compose → material ready+indexed+linked, self-exclusion of
  ai-composed from compose context, validator rejections, provenance fields.
- **11E — Glue + leftovers**: tutor completion proposals, Today tutor deep-link,
  skills sandbox upgrade (registry + proposal validator), solidity items below
  that are user-visible.

## 4. Schema changes

- `chat_messages.mentions` JSON (11A)
- `chat_proposals` (11C1): id, message_id FK, action, payload JSON, status, result
  JSON, created_at, executed_at
- `materials.provenance` JSON column already exists as pattern? — no: add
  `provenance` JSON (or reuse created_from naming used by exercises) — decide at
  implementation; index card row gains `composed_by` flag if cheaper (11D)
- task_registry: `material.compose` row (seeded migration or startup seed — follows
  the existing task-seed pattern, no alembic needed)
- skills seeds: mention line + proposal protocol + READ doc (version+1 system seeds,
  user overrides untouched)

## 5. Acceptance (phase)

- Ask the tutor "what do I have about u-substitution?" → answer names materials/
  notes/concepts as **clickable cards**; clicking opens the item; every visible ref
  exists (no dead handles).
- Chat can be given a 40-page material with **no chunks in the prompt** and still
  answer grounded by READING it on demand; the context panel shows what was read.
- A chat turn can propose "create a note summarizing this", student approves, note
  appears in the workspace — nothing was created before the click.
- "Compose a study guide for this chapter from these materials + my notes" produces
  a real material in the library, indexed and assigned to the node, with AI badge.
- All flows audited; no new write path bypasses services/validators (ADR-042 holds).
- One `EntityMention`/`AiBadge` implementation serves every surface (chat bubbles,
  blocks, proposal cards, context panel, library rows) — grep shows no local
  re-implementations; all new UI is keyboard-accessible, dark-mode-correct, fully
  i18n'd.
- In a single chat session, a handle never changes meaning between turns.

## 6. Solidity / restructure items (found in the 2026-08-20 audit)

Do these inside the slices where they bite (marked) or as chores:

1. Chat retrieval FTS-only → hybrid via resolver (**11B**, required).
2. `embeddings` + `concepts` tasks frequently unassigned → Settings Tasks tab shows
   an inline "assign a model" nudge with consequence text ("semantic search off",
   "concept extraction unavailable") (chore, 11E).
3. `CONTEXT_VARS` whitelist too narrow for bundle vars (manifest/read/proposal) →
   extend + document in skills UI (11B/11C).
4. `notes_ocr` bypasses SkillService (hardcoded prompt) → register through skills
   like every other task (chore).
5. `grade.freeform` skill seeded, never called — wire rubric grading for essay
   questions C17 or mark the seed dormant until then; don't leave dead surface
   (post-phase, tracked).
6. Tool catalog (`/ai/tools`) should be the single source for the chat system
   prompt's tool doc (generate the doc from CHAT_TOOL_CATALOG + READ entry) —
   prompts and catalog must not drift (11B).
7. `ProviderError` (new) should also wrap the embeddings/describe job paths — jobs
   record friendly failures (already partially true; verify in 11B).
8. Docs: ai.md gains the mention/proposal/compose protocol sections; usage/chat.md
   gets the cards + context panel + proposals guide (same-commit rule).
9. Record **ADR-042/ADR-043** in `06-decisions-and-risks.md` — doc 06 currently ends
   at ADR-041 and `docs/STATUS.md`'s "32 ADRs" is stale (**Step 0**, before any
   code).

## 7. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Model spamming proposals / mentions wrongly | Contract-validated whitelist; advisory-then-strict rollout; once-per-turn proposals; strip-on-failure |
| READ tool blowing context/cost | per-call char budgets, round cap 3, manifest-only handles, audit tokens |
| AI-composed material polluting retrieval (cited as "course material") | provenance flag; search/citation UI badge; option to exclude from retrieval (settings flag, default included — they are *your* study docs) |
| Proposal execution doing the wrong thing | Actions only via existing services with their validators; **revalidated at click time**; every action audited; dismiss is one click; create paths are reversible (delete note/material) |
| Prompt drift between seeds, catalog, docs | Single-source generation (item 6); eval fixtures extended with a mention/proposal golden turn (11A/11C1 deliverables) |
| UI drift: chat/workspace/library growing local card/chip variants | Shared primitives in `features/ai/` are the only implementations; acceptance greps for duplicates |

## 8. Non-goals (this phase)

- No LLM-native function-calling migration (the line protocol stays — it works,
  it's testable, and models vary).
- No autonomous agents / scheduled AI actions; HITL always.
- No write tools in MCP (read-only by design, unchanged).
- No new question types / grading paths (C17 rubric tracked separately).
- No mentions inside the tutor hint ladder this phase — hint text stays plain; its
  `no_answer_reveal` guard must not gain new extraction surface (revisit with C17).
