# 01 — Vision & Feature Catalog

## Vision

A desktop, local-first study workbench: you drop in any course material (text PDFs, scanned
PDFs, lecture photos, whiteboard shots), the app OCRs and structures it, builds a course
outline, and then tutors you — quizzes, multi-step exercises with a guided hint system,
handwritten notes with OCR, and a RAG chatbot grounded in *your* material, with citations
back to the original pages.

**Primary use case:** mathematics learning (robust equations, charts, diagrams, handwritten
math input). **Design constraint:** must generalize to any subject (history, biology, code…)
— math features are a first-class layer, never a hardwired assumption.

## Personas

- **Learner (primary)** — studies a course, wants active recall + guided practice + progress insight.
- **Curator** — assembles/curates material, fixes OCR output, organizes sections.
- (Future) **Author/Teacher** — builds shareable course packages.

## Feature catalog

Priority: **P0** = MVP, **P1** = v1.0, **P2** = later/backlog. Features are grouped by domain.

Within P0, the **v0.1 walking skeleton** is the minimal lovable loop — ingest → outline →
basic quiz → chat RAG — reached at the end of roadmap Phase 4. P0 items outside the
skeleton may slip one phase without breaking the product story; the skeleton may not.

### A. Courses & structure

| # | Feature | P |
|---|---|---|
| A1 | Courses → chapters → sections (**depth fixed at 2 levels — ADR-035**), drag & drop reorder, soft-delete/undo | P0 |
| A2 | Course metadata: subject, level, goals, tags, color, cover | P0 |
| A3 | Materials owned per course — **no global library (ADR-036)**; per-course folder trees (course → folders → materials); Library page scoped by the selected course | P0 |
| A4 | Material **groups**: bundle many images into one logical document (e.g. 12 whiteboard photos = one lecture), reorder/merge/split pages | P0 |
| A5 | Tags, favorites, full-text + semantic search across everything | P0 |
| A6 | AI outline: auto-generate chapters/sections from ingested material (editable before commit) | P0 |
| A7 | AI material→section allocation with rationale + confidence, manual override | P0 |
| A8 | Course import/export (zip: DB data + blobs), course duplication, templates | P1 |
| A9 | Concept extraction → knowledge graph / concept map view (interactive) | P1 |
| A10 | Gap analysis: course goals vs material coverage, suggestions | P1 |
| A11 | Mind-map view of course structure | P2 |
| A12 | Profiles: several learners on one machine, **no authentication** — quick switcher; profile-scoped schema from day 1 (see 03) | P1 |
| A13 | **Scoped material assignment (ADR-036)**: one document assignable at course / chapter / section scope of its own course; unlink ≠ delete; course deletion cleans up its material + folder tree | P1 (Phase 8A) |
| A14 | **Chapter workspace view**: per-chapter study route — assigned materials with read-status + original viewer, chapter notes, sections tree, scoped generate actions; course page gains Outline/Materials/Notes tabs | P1 (Phase 8B) |

### B. Ingestion & OCR

| # | Feature | P |
|---|---|---|
| B1 | PDF with text layer: layout-aware extraction (headings, lists, tables) via PyMuPDF | P0 |
| B2 | Scanned/image PDFs: rasterize pages → OCR (Gemini Flash) | P0 |
| B3 | Image OCR (incl. handwriting) → markdown with **LaTeX for math, Mermaid for diagrams, tables** | P0 |
| B4 | Extraction stored as versioned canonical markdown + structured blocks; **original always kept** | P0 |
| B5 | Per-file auto "index card": summary, topics, key terms, reading time, difficulty estimate | P0 |
| B6 | Chunking + embeddings + hybrid index (FTS5 BM25 + vectors) | P0 |
| B7 | OCR QA view: side-by-side original ⇄ extraction, inline edit, re-embed, confidence flags | P0 |
| B8 | Batch upload with background job queue + progress UI | P0 |
| B9 | Deduplication: perceptual hash (images), content hash (files) | P1 |
| B10 | DOCX / PPTX / EPUB / HTML / Markdown / plain-text ingestion | P1 |
| B11 | Image preprocessing: whiteboard cleanup, perspective correction (OpenCV) | P1 |
| B12 | Re-ingest as new version; diff extractions between versions | P1 |
| B13 | Audio/video ingestion (transcription via Whisper-class models) | P2 |
| B14 | Language detection + translation of material | P2 |
| B15 | **Linked material folders**: register external files/folders as sources (referenced in place, never copied/moved); periodic background rescan (default 5 min, + startup + manual) using cheap mtime+size check, full content hash only on change; new files auto-ingested, changed files offered for re-ingestion as a new extraction version, vanished files flagged `missing` | P1 |
| B16 | **Study mode & read-status**: per-profile reading state per material (unread / reading / studied), page-level progress, "mark studied"; cheap signal that feeds mastery estimates & dashboards | P1 |

### C. Quizzes & assessment

| # | Feature | P |
|---|---|---|
| C1 | Question types: single choice, multi-select (partial credit), true/false, type-in text | P0 |
| C2 | Math question types: **equation input (MathLive)**, numeric with units & tolerance | P0 |
| C3 | Fill-in-blank (cloze), matching pairs, ordering/sequencing | P1 |
| C4 | Diagram labeling & hotspot (click region on image/diagram) | P1 |
| C5 | Graph-reading questions (answer from Plotly chart) | P1 |
| C6 | Questions render full block format: LaTeX, Mermaid, charts, images, tables in stems & options | P0 |
| C7 | Generation controls: count, difficulty, Bloom level, scope (section/chapter/course), source (material, weak areas, mistakes) | P0 |
| C8 | Deterministic math answer checking via **SymPy equivalence** (+ numeric tolerance path) | P0 |
| C9 | Immediate feedback: correct/wrong + explanation + "why is this distractor wrong" | P0 |
| C9b | **In-question help (practice mode)**: same 5-level hint ladder as exercises (hint-leak guard active); "Ask about this question" deep-links to sidebar chat with question + open attempt pre-loaded — chat runs under `no_answer_reveal` until the attempt is submitted. Both blocked in exam mode; both audited toward the independence score | P1 |
| C10 | Practice mode vs exam mode (timed, feedback withheld until submit, section weighting) | P1 |
| C11 | Adaptive difficulty engine (item-level Elo) | P1 |
| C12 | Question bank: edit, clone, tag, flag/regenerate, similarity dedup at generation time | P0 |
| C13 | Mistake notebook: auto-collect wrong answers → targeted re-quiz | P1 |
| C14 | Code-execution questions (sandboxed, for programming courses) | P2 |
| C15 | Question statistics (difficulty index, discrimination, distractor efficiency) — item analysis feeding bank quality flags (doc 10) | P1 |
| C16 | **Multi-part/composite questions**: one stem, ordered sub-questions (a/b/c) with independent parts, **follow-through credit** (later parts graded on the student's earlier value where mathematically valid) | P1 |
| C17 | **Essay / long-answer / proof** ("prove", "show that"): rubric-graded, explicitly flagged as LLM-graded, teacher-style margin comments | P1 |
| C18 | **Handwriting input mode**: input-mode toggle (type ⇄ write) on equation/numeric/text questions — draw on canvas (stylus/touch), strokes kept, OCR → LaTeX, **"interpreted as" confirmation chip** (user corrects misreads *before* submit), then standard equivalence-chain grading | P1 |
| C19 | **Table/matrix completion**: value tables, truth tables, grid cells with per-cell grading + tolerance | P1 |
| C20 | **Error-spotting**: presented worked solution contains a seeded flaw (from the G10 taxonomy or LLM-generated + step-verified); user identifies the faulty step and/or supplies the correction | P2 |
| C21 | **Number-line / coordinate-grid answers**: click points, shade regions, plot simple graphs — middle ground between hotspot and full sketch (G7) | P2 |
| C22 | **Assessment import/export & sharing** (doc 11): `caq` single-file JSON + `qpkg` zip package (assets, checksums, license); bank/question selection export; imported questions validated by the same contracts as generated ones | P1 |
| C23 | **External-AI authoring**: markdown-shorthand JSON quizzes from any AI (paste/upload/inbox); in-app prompt builder + schema card; agents can self-serve `schema.json` from the inbox | P1 |

### D. Multi-step exercises & guided tutoring

| # | Feature | P |
|---|---|---|
| D1 | Exercises with ordered steps; per-step inputs (numeric, equation, text, choice) | P0 |
| D2 | **Hint ladder**: clarify → nudge → strategy → partial solution → full worked solution (AI, level-by-level) | P0 |
| D3 | Socratic mode toggle (AI responds with guiding questions, never gives the answer) | P0 |
| D4 | Full audit trail of every AI help event per attempt → "independence score" per exercise | P0 |
| D5 | Step-by-step worked solutions with LaTeX, verified by SymPy where applicable | P0 |
| D6 | Rubric-based grading of free-form answers (AI rubric grading w/ deterministic pre-checks) | P1 |
| D7 | "Similar exercise" generator (isomorphic problem, parameter variation for math) | P1 |
| D8 | Error-pattern detection across attempts ("recurring sign error") → micro-drills | P1 |
| D9 | Multiple solution paths accepted & checked (equivalence classes) | P1 |
| D10 | Help taxonomy unified across quiz & exercise: hint ladder (5 levels), Socratic toggle, "ask about this", post-answer feedback — every help event audited (who, what level, when) and scored into one **independence score** per attempt | P0 |

### E. Notes & handwriting

| # | Feature | P |
|---|---|---|
| E1 | Notes attachable to sections, questions, attempts, exercises (or standalone) | P0 |
| E2 | Rich text editor with LaTeX, Mermaid, tables, code, images | P0 |
| E3 | **Drawing canvas** (stylus/pressure, colors, shapes, layers) → OCR to markdown blocks; original strokes kept & replayable | P0 |
| E4 | Snap regions of PDFs/images into notes | P1 |
| E5 | AI note actions: summarize, clean up, generate flashcards, explain, expand | P1 |
| E6 | Handwritten math → LaTeX (via OCR pipeline), editable after conversion | P0 |
| E7 | Flashcards: basic, cloze, reverse; **FSRS spaced repetition** scheduling; Anki **import** (.apkg/.csv) and export | P1 |
| E8 | Notes search including OCR'd handwriting | P1 |
| E10 | **Notes as study objects (Phase 8C)**: tags + tag filters, paginated API, per-chapter notes index/tree, note→material links surfaced in the chapter workspace | P1 |
| E9 | PDF annotation layer (highlight/comment on originals) | P2 |

### F. AI chatbot (sidebar)

| # | Feature | P |
|---|---|---|
| F1 | Sidebar chat, streaming responses, saved sessions per course | P0 |
| F2 | Auto-context: current section + its materials + active note + recent quiz mistakes | P0 |
| F3 | RAG over course material with **citations linking to source page/image region** | P0 |
| F4 | Tools: calculator, SymPy (solve/simplify/plot), course search | P1 |
| F5 | Modes: Tutor (Socratic), Explainer, Quick-answer, Quiz-me (AI interrogates the user) | P1 |
| F6 | "Ask about this image/diagram": select region → vision-grounded answer | P1 |
| F7 | Pin any assistant answer into notes | P1 |
| F8 | Follow-up suggestion chips | P2 |
| F9 | Voice input/output (STT/TTS) | P2 |

### G. Math robustness layer (subject-agnostic core, math-first extensions)

| # | Feature | P |
|---|---|---|
| G1 | KaTeX rendering everywhere; MathLive WYSIWYG equation input with symbol toolbar | P0 |
| G2 | SymPy answer equivalence (algebraic/symbolic), numeric with units & tolerance | P0 |
| G3 | Plotly interactive charts (function plotting, data charts) | P0 |
| G4 | Mermaid diagram rendering & editing | P0 |
| G5 | JSXGraph interactive geometry (draggable constructions) | P1 |
| G6 | Auto-generated formula/cheat sheet per chapter | P1 |
| G7 | Graph-sketch answers: compare student sketch vs key features (intercepts, extrema, asymptotes) | P2 |
| G8 | Step-verification: each step of a student's solution checked independently | P1 |
| G9 | **Answer equivalence chain**: SymPy simplify → numeric random-point sampling → solveset; units via pint — robust for calculus forms that simplify() alone can't match | P0 |
| G10 | **Calculus error taxonomy & diagnosis** (chain-rule omission, missing +C, u-sub bounds, sign slips…) → targeted hints & micro-drills | P1 |
| G11 | **Hint-leak guard**: deterministic check that hints/feedback never contain answer-equivalent math | P0 |

### J. Skills, prompts & AI behavior customization

| # | Feature | P |
|---|---|---|
| J1 | **Skills library UI**: per-task behavior definitions with resolution chain (system → course type → course) | P1 |
| J2 | **Prompt template editor**: Jinja2 templates, context-variable sidebar, live preview against real material | P1 |
| J3 | **Test-run sandbox**: execute a skill on real context → output + per-constraint validation results + cost | P1 |
| J4 | **Behavior contracts engine**: machine-checkable constraints per skill (e.g. hint NEVER reveals the answer), deterministic validators + repair loop | P0 (code-enforced from first AI features) |
| J5 | Versioning: every save versions; diff, rollback, restore system default; version logged per AI call | P1 |
| J6 | **Course types** (math, science, language, programming, generic; user-definable) with per-type skill overrides | P1 |
| J7 | Skill packs: export/import JSON for sharing | P2 |

### H. Progress, analytics & motivation

| # | Feature | P |
|---|---|---|
| H1 | Mastery estimate per concept (Bayesian knowledge tracing / Elo hybrid) | P0 |
| H2 | Quiz/exercise session reports: mistakes, explanations, linked material & notes | P0 |
| H2b | **Score page** (doc 10): all attempts/tries history with per-question drill-down; overview (mastery map, rolling & difficulty-adjusted accuracy, trends); diagnostics (concepts×skills weakness matrix, error-pattern profile, speed–accuracy); recommendations with evidence lines | P1 |
| H3 | Dashboard: study time, streaks, activity heatmap, upcoming SRS reviews | P1 |
| H8 | Gamification (XP, levels, badges) — **calm by default**: silent XP accrual, toast level-ups, no leaderboards/social pressure; full off-switch; no dark patterns (see 09) | P1 |
| H10 | **Daily goal & streaks**: minutes-or-questions goal, weekly-earned streak freeze, guilt-free heatmap framing | P1 |
| H11 | **"Next best action" engine**: ranks due reviews, weak concepts, unfinished exercises, unread material by urgency × goals; one tap starts a session (drives the Today screen) | P1 |
| H12 | **Session variety engine**: quiz blueprints mix types, difficulty ramps, alternating stem shapes (text/diagram/chart) — monotony is the primary boredom source | P1 |
| H4 | Weak-area detection → one-click targeted review session | P1 |
| H4b | **Question metadata & telemetry**: concepts + skill (conceptual/procedural/applied/notation) + bloom + difficulty + expected-time + source refs on every question; time/hints/retries/error-tags on every answer (doc 10) — bank-enforced, not optional | P0 |
| H5 | Study planner: goals, deadlines, schedule generation | P1 |
| H6 | Exam-readiness forecast | P2 |
| H7 | **LLM cost dashboard**: tokens & $ per feature per model, budget caps | P0 |
| H9 | Progress/data export (CSV/JSON) | P1 |

### I. Platform, UX & engineering

| # | Feature | P |
|---|---|---|
| I1 | Desktop app on Linux/Windows/macOS, launched via Python (`python -m courseassistant`) | P0 |
| I2 | Offline-first: all reads local; LLM features degrade gracefully when offline | P0 |
| I3 | Settings: **provider registry** (Google / OpenAI-compatible / Anthropic, keys in **OS keyring**), per-provider **model auto-discovery** with enable toggles, **per-task model assignment** (see plan 07), tutor behavior prefs | P0 |
| I4 | Light/dark themes, font scaling, accessibility (keyboard nav, ARIA, contrast) | P0 |
| I5 | Command palette + keyboard shortcuts | P1 |
| I6 | Backup/restore full app data; auto-backup | P0 |
| I7 | **Ollama as a first-class local provider** (preset in provider wizard, auto-detect `localhost:11434`; chat + embeddings → near-full offline mode) | P1 |
| I8 | **i18n wired from day 1** (i18next/react-i18next, zero hardcoded UI strings); **English-only UI for v1** — additional languages later = dropping in JSON catalogs | P0 |
| I9 | Onboarding wizard + sample course | P1 |
| I11 | Plugin system (custom question types, generators, importers) | P2 |
| I12 | Telemetry strictly opt-in; local structured logs | P0 |
| I13 | CI, type checking, linting, tests (unit/integration/e2e), prompt evals | P0 |
| I14 | TTS read-aloud of material | P2 |
| I15 | Auto-update checker | P2 |
| I16 | **PDF/print export**: quizzes (with & without answer key), worked solutions, notes, chapter cheat sheets — study away from the screen (print-CSS HTML or Typst/weasyprint) | P1 |
| I17 | Global quick-capture hotkey → inbox note (text, screenshot region, photo), triage later | P2 |
| I18 | Focus timer (Pomodoro) logging into `study_sessions` | P2 |
| I19 | **Celebration & milestone moments**: ring-burst animations on first 100%, streak milestones, concept mastery (tasteful, sparse — never routine); optional sounds | P1 |
| I20 | **Mastery visualizations**: per-concept rings, chapter coverage bars, course mastery tree that fills in as you learn | P1 |
| I21 | **Today screen**: streak + daily-goal ring + next-best-action card + fast course switcher — the app's front door (see 09) | P1 |
| I22 | **Import inbox directory**: watched folder (same scanner as linked material folders) picking up `caq`/`qpkg`/Anki files; staged-import preview; `.imported`/`.rejected` disposition (doc 11) | P1 |

## Explicit non-goals (for now)

- Web/mobile deployment, multi-user realtime collaboration, cloud sync service, billing.
- Training/fine-tuning models — prompting + RAG only.
