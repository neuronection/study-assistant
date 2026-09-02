# Changelog

All notable changes to **Study Assistant** are documented here.

## [Unreleased]

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

- **App shell nav on the shared library primitive** — the primary
  sidebar navigation is now `SidebarNav` from `@neuronection/assistant-ui`
  (keyboard navigation, `aria-current`, family-standard visuals), driven
  by the new `config/nav.ts` registry with a tested `resolveActiveId`
  helper. Part of the family nav primitives program (ADR-0007).
- **Plan 48 — local-first AI engines (ADR-105)** — llama.cpp and LM Studio
  presets (keyless like Ollama); `GET /providers/detect-local` probes local
  engines with shape validation and skips already-configured base URLs; the
  first-run wizard auto-detects running local engines with one-click add;
  all-local setups get an offline hint; embeddings calls now write
  `ai_interactions` ledger rows (they had bypassed the ledger); new
  `docs/usage/local-ai.md` guide.
