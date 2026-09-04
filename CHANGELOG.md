# Changelog

All notable changes to **Study Assistant** are documented here.

## [Unreleased]

### Changed
- **Chat-turn engine cutover (family AI-alignment Phase 8, plan 10).**
  `SA_CHAT_ENGINE` now defaults to `graph` — chat turns run on the
  checkpointed LangGraph engine by default (soaked: paced-token live-server
  soak with legacy-shadow diffing — event-order parity modulo the ratified
  D1; Playwright e2e smoke green on the default engine; full suites green).
  `legacy` remains available as rollback and pins the legacy streaming
  presentation tests; the legacy loop is deleted in a later release after
  one clean graph-default release. D2 (proposals → `interrupt()`) stays
  reserved — the adapter hook is in place, the semantics change rides a
  later proposals PR.

### Added
- **Family event vocabulary + `FlowStatusCard` adoption (family
  AI-alignment migration Phase 6, plan 10 §6.2/6.3).** Chat turns now emit
  the family event vocabulary (`flow_started`/`node_started`/
  `node_finished`/`delta`/`flow_finished`/`flow_failed`) additively
  alongside the legacy WS names on `chat:{id}` — one pure mapper
  (`app/agui/family.py`, closed `FlowEvent` StrEnum) applied to both chat
  engines; legacy consumers are untouched (unknown types are ignored).
  The shared editor's ✨ AI helper adopts the library's new
  `FlowStatusCard` (`@neuronection/assistant-ui` ^0.18.0, shim
  `components/ui/flow-status.ts`): the running state shows the
  Transform → Review flow card with Cancel (replacing the duplicate Stop
  button), and failures render the card's retryable-failed state with Retry.
  `TraceTimeline` stays for the rich chat view.
- **Chat-turn graph engine (family AI-alignment migration, plan 10 Phase 5,
  ADR-0008).** The chat turn is now also available as a checkpointed LangGraph
  `StateGraph` (`backend/app/ai/graphs/chat_turn.py`):
  `retrieve → contract_guard → agent_round ⇄ → validate_repair → finalize`,
  mirroring the legacy `ChatService.answer_streaming` loop node-for-node —
  native tool calling with in-memory degradation to the prompt grammar,
  per-kind tool budgets (math 2 / READ 3 / STATE 3 / resource 5), the
  deterministic contract repair loop, and byte-identical WS event payloads
  (`stream_start` / `phase` / `stream_delta` / `tool_call` /
  `stream_interrupted` / `assistant_message` / `turn_error`) and the AG-UI
  mapping on top. The engine is selected by `SA_CHAT_ENGINE=legacy|graph`
  (default `legacy` — nothing flips); context assembly, contracts, and
  persistence are shared helpers (`prepare_turn_context`,
  `prepare_turn_contract`, `finalize_turn`) so the two engines cannot drift.
  Checkpointing is dialect-picked (`AsyncSqliteSaver` on
  `data_dir/checkpoints.db` for desktop, `AsyncPostgresSaver` for a future
  server mode), opened once in the app lifespan with `thread_id` = chat
  session id, and pruned at boot (`SA_CHECKPOINT_TTL_DAYS`, default 14).
  Token deltas flow through the raw stable streaming API
  (`astream(stream_mode=["updates", "messages"])` — integrator ruling
  2026-09-04; the v3 event-streaming swap is a one-file adapter change).
  Node fault tolerance is
  layered over the gateway's own retries (graph retries only raw transport
  leaks; per-node hang-guard timeout). `TaskRunner` single-call tasks are
  untouched.

## [v0.5.0] - 2026-09-02

### Added
- **Compact sidebar on short viewports** — at ≤720px window height the
  nav drops to the library's new `SidebarNav` `compact` density and the
  footer drops to a compact variant (Neuronection mark + wordmark link,
  smaller Fund/About pills, version; the family panel hides) so every
  nav item stays reachable.
- **Sidebar footer project block** — "Part of Neuronection" (mark + wordmark
  link), the three family assistants (Health / Career / Study — library
  marks, aligned names, external links, the current app emphasized), Fund +
  About pills and the app version (from `frontend/package.json`). The Fund
  popup reuses the library `SponsorCard` (Buy Me a Coffee + GitHub star
  channels in `config/funding.tsx`, also wired into the About page). Copy
  lives in the app locale — the library stays presentational per ADR-006.
- **`@neuronection/assistant-ui` ^0.17.0** — `SidebarNav` `compact` density,
  compact SponsorCard redesign, clickable current-app FamilyBadge,
  `SidebarNav.secondaryItems`.

### Changed

- **Sidebar nav structure** — Settings is now a pinned `secondaryItems`
  entry on the library `SidebarNav` (replacing the hand-rolled footer
  link) and the About link becomes the footer block's About pill;
  `/about` itself is unchanged. `frontend/package.json` now carries the
  app version (propagated by `version_manager.toml` on every bump).
- **App shell nav on the shared library primitive** — the primary
  sidebar navigation is now `SidebarNav` from `@neuronection/assistant-ui`
  (keyboard navigation, `aria-current`, family-standard visuals), driven
  by the new `config/nav.ts` registry with a tested `resolveActiveId`
  helper. Part of the family nav primitives program (ADR-0007).
- **Dev-link commit guard** — commits are blocked while an
  assistant-ui dev-link is active: `scripts/check-dev-link.sh` runs as a
  pre-commit hook (enable once per clone with
  `git config core.hooksPath scripts/githooks`) and in CI, failing when
  `pnpm-workspace.yaml` carries a `link:` override for the library.

## [v0.4.0] - 2026-09-02

### Added
- **Plan 50 — sharing & OSS readiness** — four slices, four commits:
  - **`ca-course/v2` course bundles (ADR-109)** — bundles now carry the full
    learning state: flashcards with FSRS schedules (review log opt-in),
    `exam_date`, discovered error patterns, and (opt-in) quiz/exercise
    attempt history + note version history; v2 quiz questions carry ids for
    history remapping; the importer still accepts v1. **Imports self-heal**:
    every imported material is enqueued for postprocess (embeddings + index
    card), so imported courses stop degrading to FTS-only search; the import
    response returns `postprocess_job_ids`.
  - **Skill packs (`ca-skills/v1`, ADR-110)** — export skill definitions +
    system-scope version history as JSON; staged import with per-skill
    validation and explicit collision resolution (replace as new version /
    rename / skip). UI: per-row Export + Import pack dialog in
    Settings → Skills.
  - **Playwright e2e smoke (ADR-111)** — four specs against the real backend
    (boot/wizard, upload+search, quiz run+score, chat turn with a tool card)
    driven by a mock OpenAI-compatible provider (keyless, per plan 48-A);
    new CI `e2e` job and release-gate step.
  - **OSS polish** — `SECURITY.md`, GitHub issue/PR templates, About-page
    family links, and an enriched sample course (3-question quiz, 6
    flashcards with 2 due, exam date in 14 days, concept with coverage).

### Changed

- **Plan 48 — local-first AI engines (ADR-105)** — llama.cpp and LM Studio
  presets (keyless like Ollama); `GET /providers/detect-local` probes local
  engines with shape validation and skips already-configured base URLs; the
  first-run wizard auto-detects running local engines with one-click add;
  all-local setups get an offline hint; embeddings calls now write
  `ai_interactions` ledger rows (they had bypassed the ledger); new
  `docs/usage/local-ai.md` guide.
