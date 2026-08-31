# Plan 52 — Topic explorer & course genesis: start from a subject, not from files (user request 2026-08-31)

Status: planned (2026-08-31, user-approved) · Phase: post-1.0 · Suggested order: A → B → C → D (A first: B's scratch space and D's research notes both live in it)

## Context

The 2026-08-31 audit closed the ingest→study loop (plans 47–51), but the app is
**closed-world**: a student who wants to learn "Linear Algebra" or "The French
Revolution" and doesn't already possess material has no entry path. Every course
starts with an upload; notes are course-bound by design (ADR-036/040 — correct for
content ownership, but it means *exploration has no home*). "Explore topics/courses
they want with the help of LLMs" is half the product promise and currently zero
percent of the surface.

Design stance (deterministic-first house rule still governs): genesis is **scaffold
→ generate → review**, never a one-shot blob. The LLM drafts structure and lessons;
everything lands as normal, editable, provenance-tagged objects (nodes, composed
materials, generated quizzes/flashcards) the user can prune, regenerate, or overwrite
with real material later. Budget gates are explicit — generating a whole course is
the most expensive operation in the app, and it must never run away.

**ADRs recorded as slices start:**

| # | Decision |
|---|---|
| 116 | A per-profile **Scratchpad** system course (the migrations' "Unsorted" pattern) hosts pre-course exploration — notes, drawings, chat uploads, research captures — with a **Promote-to-course** flow that moves scratch content into a real course; ADR-040's course-required rule gains this sanctioned exception, not a nullable-course regression |
| 117 | Course genesis = topic → editable outline draft → explicit scaffold commit → per-node generation behind per-step budget gates and a global session cap; every artifact carries AI provenance; **web grounding is optional** and cited, model-knowledge-only by default |

## A — Scratchpad: a home for exploration (ADR-116)

**Problem.** Notes/materials require a course (ADR-040); a topic-dabbler has nowhere
to park anything before committing to a course.

**Design.**

- Migration **0050**: `courses.origin` (`manual | genesis | import | scratch`,
  default `manual` — `import` set by the plan-50 v2 importer for observability) +
  `courses.hidden` (bool; scratch is hidden from the Courses page and the rail
  switcher, surfaced only in the Scratchpad UI and palette).
- One **Scratchpad** course per profile (seeded lazily on first need, like the
  "Unsorted" pattern): its tree has a single root; users can add child nodes freely
  to organize exploration (topic → subtopic). All existing surfaces work unchanged
  inside it — notes + drawings, text/markdown files, chat uploads (the course-less
  chat fallback `resolveUploadCourse` gains the scratchpad as a preferred target
  over "Unsorted"), read-states, generate actions.
- UI entry: rail **Scratchpad** row (below Courses; hidden when empty, `hidden`
  course) and a Home "Explore a topic" card (slice B's genesis entry point beside
  it). The Scratchpad looks like a small course workspace (same NodeWorkspace, minus
  exam/practice analytics noise — Today's recommendations exclude it).
  **Analytics scoping** (revision 2026-08-31): scratch answers still count toward
  streaks/daily goals (honest activity), but `origin=scratch` courses are excluded
  from exam forecasting, course-level readiness/weakness summaries, and
  recommendation cards — exploration must never masquerade as course progress.
- **Promote-to-course**: scratchpad node context-menu action → wizard (title,
  subject, level, color) → creates a real course and *moves* the subtree (nodes,
  notes, materials, links, chat bindings) into it — a subtree re-parent across
  courses is new (the tree service gains `move_subtree_to_course`), ownership
  columns ride along, provenance unchanged. Nothing is copied or regenerated.
  **Concept coverage does not move** (revision 2026-08-31): concepts are a
  per-course graph (ADR-039) — a subtree move drops its coverage links, with an
  honest line in the confirm dialog ("concept coverage stays behind"); node-bound
  chat sessions re-bind through the same composite-FK rule the tests pin.

**Accept.** Open Scratchpad, create node "Group theory", write notes, attach two
chat uploads, ask the tutor about it → then Promote-to-course "Abstract Algebra" →
the notes/materials/node tree are now a normal course; Scratchpad is empty again.

**Tests.** Backend: lazy scratch seeding per profile, hidden-course list filtering
(courses list, rail counts, Today recommendations), `move_subtree_to_course`
(integrity of composite FKs, chat session re-binding, material links), promote
endpoint + idempotency. Frontend: scratchpad entry points, promote wizard, hidden
filtering.

## B — Course genesis: topic → scaffolded course (ADR-117)

**Problem.** No path from "I want to learn X" to a studyable course.

**Design.**

- New skill `course.genesis` (task reuses `outline` — the existing outline-draft
  task already drafts 2 levels with deterministic validators): prompt takes topic +
  optional level (school / university-intro / university-advanced) + depth hints,
  returns title/description/subject/level/goals + 2-level node outline with
  per-node one-line objectives. Same draft → review/edit → commit flow as material
  outline (frontend `OutlineActions` pattern, new `GenesisDialog` in
  `features/ai/`): step 1 topic form → step 2 editable outline → step 3
  generation options.
- **Scaffold commit**: `POST /courses/genesis` — creates the course (`origin=genesis`,
  every node tagged `ai_hint` with the objective), then runs **generation options**
  (all off by default except lessons-on-core-nodes, each behind its own gate):
  - **Lessons** (slice C) on depth-1 nodes.
  - **Seeded quizzes**: one 5-question quiz per depth-1 node (existing quizgen,
    node-scoped; retrieval includes the fresh lessons because provenance rules
    already include `ai-composed`).
  - **Flashcards**: 10 per depth-1 node (existing flashcards pipeline).
  - Budget honesty: a genesis session cap (profile preference, default ~N tasks)
    surfaced in step 3 with an estimated task count; the whole run is a chain of
    normal jobs (`genesis` job type, progress events per node, cancellable,
    retriable per-task on failure — a failed lesson never blocks the quiz for a
    different node).
- Provenance everywhere: course badge "AI-generated — review before trusting"
  (AiBadge pattern) on the workspace header; materials/lessons carry the existing
  `ai-composed` provenance; quizzes/flashcards are normal generated objects.
- The generated course is **empty of real material by design**: node Reviews will
  honestly report "no material covers X" (the organizer already does), and the
  workspace empty states prompt "add your course files" — genesis is a starting
  scaffold, not a textbook replacement. Copy in the genesis dialog says so.

**Accept.** Type "Linear algebra for economists", pick university-intro, keep
defaults → a course exists with a sensible 2-level outline, a readable lesson per
chapter, one short quiz and 10 cards each — all editable/regenerable, all clearly
AI-tagged, and the course honestly says "add your own material" on its Materials
tab.

**Tests.** Backend: genesis skill contract validators (shape, ≤2 levels, objective
lines), scaffold endpoint (idempotency on double-submit, cancellation mid-chain,
budget cap enforcement, per-task failure isolation), provenance/badges on all
artifact classes. Frontend: dialog steps, budget preview, progress UI, badge
rendering.

## C — `lesson` compose kind (ADR-117)

**Problem.** Genesis lessons need a content object; today's compose kinds are all
*revision* artifacts over existing material, none is an expository lesson.

**Design.**

- `pipelines/compose.py` KINDS += `lesson` ("expository lesson: definitions,
  explanation, worked example, common pitfalls; no fabricated citations"). New
  retrieval posture: for lessons, **model-knowledge is the source** — the ContextSpec
  rides with whatever material exists (none at genesis time) and the skill prompt
  says so explicitly; `RETRIEVAL_EXCLUDED_KINDS` stays untouched (lessons are study
  content, retrievable like cheat sheets).
- One-live-artifact per (node, `lesson`) — the plan-22 J rule applies for free
  (regenerate = new extraction version, history preserved).
- Lessons render in the workspace like any composed material (ExtractionView,
  printable via slice 53-F later). Notes-style editing through the extraction QA
  editor, so users can correct the model's exposition (and the correction persists
  across regenerations via the `{existing}` revision slot).

**Accept.** Generate a lesson on "Eigenvectors" for a node → a structured markdown
material with definition → explanation → worked example → pitfalls, editable,
retrievable by the tutor, regenerating versions in place.

**Tests.** Compose round-trip (kind registration, one-live rule, revision-aware
regeneration with a hand-edited previous version), validator sanity (length,
no-preamble contract), retrieval inclusion.

## D — Research tools: SEARCH + FETCH in chat, optional web grounding (ADR-117)

**Problem.** Model knowledge alone goes stale and can't cite; students exploring
current/contested topics need sources.

**Design.**

- **Search provider setting** (Settings → Providers gains a section; NOT a provider
  row): `search_provider` preference — one generic adapter, Tavily-style
  `POST {base_url}/search {query} → {results:[{title,url,content}]}` (covers Tavily
  self-hosted and compatible services; SearXNG's JSON API adapter behind the same
  interface via a `flavor` field). Key in the **keyring** (rule 6), base URL + flavor
  in the DB. Unassigned = feature absent (honest degradation, same as embeddings).
- Chat tools (CHAT_TOOL_CATALOG += `SEARCH "query"` (budget 2/turn) and
  `FETCH <url>` (budget 1/turn, content → readable text via the plan-47
  html→markdown converter, ≤4k chars, domain-allowlist off but robots-unaware
  fetch is labeled in the tool doc)): results render as citation chips (url
  domains), tool_call cards as usual; **advisory contract constraint**
  `sources_cited_when_search_used` — like `mentions_in_range`, logged not blocking.
  Native `bind_tools` schemas from the same catalog (ADR-082 machinery).
- Genesis step-1 gains an optional "ground the outline in web sources" toggle
  (visible only when a search provider is assigned): runs 3–5 SEARCH queries on
  topic subaspects, feeds titles+snippets into the outline prompt, and stores the
  source URLs on the course description footer ("Drafted with sources: …").
- FETCH/SEARCH content is **never persisted** beyond the message/trace (READ-tool
  contract precedent).

**Accept.** Assign a Tavily-compatible endpoint, ask "what are the current standard
treatments of P vs NP in undergrad curricula" → SEARCH/FETCH tool cards appear, the
answer cites source domains; a genesis run with grounding shows the sources footer.

**Tests.** Backend: preference CRUD + keyring round-trip, adapter (both flavors)
with stub transport, chat tool execution/budgets/strip-from-answer, contract
constraint logging, socket-blocking guard intact (httpx MockTransport only).
Frontend: settings section, citation chips, genesis toggle visibility rules.

## Non-goals (this round)

- Full-text web *importer* (turn a URL into a course material) — FETCH is a research
  tool; "save this page as material" is a natural follow-up once demand shows.
- Generated lessons as PDFs/textbooks with images/diagrams (compose is markdown;
  the widget/chart grammar can decorate later).
- Multi-web-source synthesis with contradiction reporting (research-assistant depth).
- Spaced *curricula* ("12-week syllabus with deadlines") — that is plan 53-A's
  planner consuming an existing course, not genesis.
- Public template gallery / sharing genesis presets (ca-course/v2 + skill packs in
  plan 50 are the transport; curation is community work).
- Voice exploration (speak a topic) — dictation already covers input.

## Dependencies & suggested order

A first (B and D's scratch surfaces live in it). B before C's user-facing payoff
(lessons are generated by B's chain, but C is independently testable via the
compose pipeline — safe to build in either order after A). D independent of B/C.

## Verification per slice

Backend: `ruff check . && mypy . && pytest` · Frontend: `pnpm lint && pnpm typecheck &&
pnpm test && pnpm build`. Docs duty: `docs/features.md` (exploration section),
`docs/ai.md` (genesis + research tools), new `docs/usage/exploring.md` (scratchpad,
genesis, promote, research tools), `docs/data-model.md` (0050), `docs/STATUS.md`
changelog + module rows each slice.
