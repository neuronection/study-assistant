# Study Assistant — Planning & Architecture

AI-powered desktop study companion: ingest course material (any format), structure it into
courses/chapters, and learn through quizzes, multi-step guided exercises, notes (rich text +
handwriting), and a context-aware AI tutor. Math-first, but subject-agnostic by design.

## Documents

| Doc | Contents |
|---|---|
| [01-vision-and-features.md](01-vision-and-features.md) | Product vision, personas, full feature catalog (tiered P0–P2) |
| [02-architecture.md](02-architecture.md) | System architecture, tech stack, UI shell recommendation, project layout |
| [03-data-model.md](03-data-model.md) | SQLite schema, content-block format, blob/vector/FTS storage |
| [04-ai-and-pipelines.md](04-ai-and-pipelines.md) | LangChain/LangGraph pipelines, model routing, **OCR-first multimodal design**, prompt/cost/eval governance |
| [05-roadmap.md](05-roadmap.md) | Phased delivery plan with acceptance criteria |
| [06-decisions-and-risks.md](06-decisions-and-risks.md) | ADRs, risk register, open questions |
| [07-settings-providers-models.md](07-settings-providers-models.md) | Settings UI: provider registry, model discovery, per-task assignment |
| [08-skills-and-prompts.md](08-skills-and-prompts.md) | Skills & prompt library, behavior contracts (e.g. hint-never-reveals-answer), course-type scoping |
| [09-design-and-ux.md](09-design-and-ux.md) | UI/UX design system, quiz flow & engagement loop (streaks, goals, next-best-action), accessibility |
| [10-analytics.md](10-analytics.md) | Question metadata taxonomy, score page (all tries & metrics), diagnostics & recommendations engine |
| [11-import-export-format.md](11-import-export-format.md) | `caq` JSON + `qpkg` zip interchange formats, import pipeline, watched inbox, external-AI authoring kit |
| [12-uniform-scoping.md](12-uniform-scoping.md) | **Phase 9**: unified node tree (one `tree_nodes` per course, ≤4 levels) + `node_id` placement everywhere — schema, tree service, NodeWorkspace UI, AI/MCP resource layer (ADR-039) |
| [13-sidebar-navigation.md](13-sidebar-navigation.md) | App rail + tree sidebar navigation round |
| [14-ai-task-layer.md](14-ai-task-layer.md) | **Phase 10**: ContextResolver + TaskRunner + GenerateDialog (ADR-042) |
| [15-ai-companion.md](15-ai-companion.md) | **Phase 11**: AI as first-class actor — mentions, on-demand context, HITL proposals, AI-composed material (ADR-043) |
| [16-study-launcher.md](16-study-launcher.md) | Study launcher / mindmap round (ADR-044) |
| [17-consolidation-and-polish.md](17-consolidation-and-polish.md) | Post-1.0 consolidation: material display, mindmap history, entity actions, MCP context, code-splitting |
| [18-focus-mode-uniformity-and-exercise-types.md](18-focus-mode-uniformity-and-exercise-types.md) | FocusShell/origin-return navigation + exercise kind system incl. card migration (ADR-045) |
| [19-card-write-mode-and-answer-basket.md](19-card-write-mode-and-answer-basket.md) | Card write mode + answer basket |
| [20-workspace-tab-action-bar.md](20-workspace-tab-action-bar.md) | Uniform `TabActionBar` across NodeWorkspace tabs (one primary action per tab, documented exceptions) |
| [21-node-settings-popover.md](21-node-settings-popover.md) | Node settings popover in the workspace header (title/description/AI instructions incl. root via course PATCH; `AiHintCard` retired) |
| [22-durability-sharing-study-experience.md](22-durability-sharing-study-experience.md) | **Post-1.0 round 3:** data durability (note autosave/versions, automatic backups + sync folder, trash), inline drawings + canvas v2, course bundles (`ca-course/v1`), split-view study, exam planner + formula sheet, organizer artifacts as materials with one-live-artifact regeneration (ADR-046…051) |
| [31-inline-ai-helper.md](31-inline-ai-helper.md) | **Inline AI helper in the rich editor:** ✨ toolbar button → AI popover (transform presets + free-form write + context toggle, streamed preview, human-gated insert) on the shared Tiptap editor — `editor.transform` skill, WS streaming, lossless markdown insert (ADR-068, planned) |
| [34-interactive-widgets-and-agui.md](34-interactive-widgets-and-agui.md) | **Interactive widget blocks & the AG-UI state channel:** a `widget` block kind built from a typed component registry (chart/geo/checklist/slider/choice/equation_input/numberline), chart+geo renderers (Plotly/JSXGraph), and a bidirectional AG-UI state channel so graders and the LLM can read widget state (ADR-071…073, planned) |
| [37-ai-gateway-framework-and-reliability.md](37-ai-gateway-framework-and-reliability.md) | **AI gateway framework adoption & reliability:** LangChain chat models behind `LLMGateway` (retries/fallback, real usage+cost), native function calling via `.bind_tools()` (cap-gated + auto-degrade), `.with_structured_output()` pre-validation, prompt caching + token accounting (ADR-081…084, proposed; revised 2026-08-26 after review — pre-A dependency spike, streaming-retry policy, fallback billing attribution, live-model smoke checks) |
| [40-chat-branching-composer.md](40-chat-branching-composer.md) | **Chat turn branches + composer/message actions:** OpenWebUI-style message branching (0044 parent/active-child tree), copy/edit/retry + variant switcher, "+" menu equation/drawing/screenshot, stop + scroll pill + code-copy + .md export (ADR-093…094) |
| [41-chat-branch-tree-rail.md](41-chat-branch-tree-rail.md) | **Chat branch-tree rail:** header popover rendering the full message tree from `GET /chat/sessions/{id}/tree` (commit-graph styling, active path highlighted, click = `select` variant) — no schema change, no graph deps (ADR-095) |
| [43-infinite-drawing-canvas.md](43-infinite-drawing-canvas.md) | **Infinite drawing canvas:** unbounded pan/zoom canvas (wheel zoom, middle/Space/hand pan, floating zoom bar), dialog fullscreen, crop-on-save (bbox + 24 px) + `view` scale metadata (0046) restoring 100% on re-edit (ADR-098) |
| [44-first-run-wizard.md](44-first-run-wizard.md) | **First-run setup wizard:** server-truth gate, skippable core steps (provider → models → defaults → course → files), `GET /onboarding/state` (ADR-100) |
| [45-working-directory.md](45-working-directory.md) | **Working directory as a first-class setting:** config-dir pointer file, validate/apply-on-restart API + UI in Settings and the wizard (ADR-101) |
| [46-ocr-image-efficiency-and-async-drawing-ocr.md](46-ocr-image-efficiency-and-async-drawing-ocr.md) | **OCR payload efficiency + async drawing OCR:** long-edge cap + WebP re-encode at the engine boundary; drawing OCR as a background `drawing_ocr` job (ADR-102) |
| [47-ingestion-office-and-av.md](47-ingestion-office-and-av.md) | **Ingestion breadth:** DOCX/PPTX/EPUB/HTML converters (B10), lecture audio/video → transcript materials (B13), unsupported uploads refused at the door (ADR-103/104, planned) |
| [48-local-ai-engines.md](48-local-ai-engines.md) | **Local-first AI engines:** llama.cpp/LM Studio presets, local-engine detection in onboarding, local embeddings via OpenAI-compatible servers; no in-process ML models, ever (ADR-105, supersedes ADR-011 clause; planned) |
| [49-study-experience-review-sessions-exams.md](49-study-experience-review-sessions-exams.md) | **Study experience:** cross-course Review queue, `study_sessions` + focus timer (I18/H3/H10), server-enforced exam timing (C10) (ADR-106…108, planned) |
| [50-course-v2-and-oss-readiness.md](50-course-v2-and-oss-readiness.md) | **`ca-course/v2` + OSS readiness:** flashcards/FSRS + exam_date in bundles, import re-embeds, skill packs (J7), Playwright e2e smoke, README/About/sample-course polish (ADR-109…111, planned) |
| [51-ai-native-answer-types.md](51-ai-native-answer-types.md) | **AI-native answer types:** C21 number-line answers, G7 graph-sketch grading (keypoints v1), C20 error-spotting, C14 code-exec via Pyodide, C16 composite (follow-through credit), C19 table-fill, C4/C5 visual answers, C11 item-level Elo (ADR-112…125, planned; widened same day) |
| [52-topic-explorer-and-course-genesis.md](52-topic-explorer-and-course-genesis.md) | **Topic explorer & course genesis:** per-profile Scratchpad + promote-to-course, topic → AI-scaffolded course (lessons/quizzes/flashcards behind budget gates), SEARCH/FETCH chat research tools with optional web grounding (ADR-116/117, planned) |
| [53-planner-and-expression.md](53-planner-and-expression.md) | **Planner & expression:** study planner (H5) + exam-readiness forecast (H6), Quiz-me chat mode with deterministic grading, teach-back flow, TTS read-aloud, print/PDF template engine (ADR-118…121, planned) |
| [54-consolidation-and-hardening.md](54-consolidation-and-hardening.md) | **Consolidation & hardening (run before 47–53):** cancel-on-purge + `cancelled` job status + commit-time stale checks (ADR-126), mechanical module splits (`lib/api/`, `domain/models/`, `services/` groups — ADR-127), flake-class hygiene; zero-behavior refactors with test-count invariance |
| [55-code-quality-and-typed-contracts.md](55-code-quality-and-typed-contracts.md) | **Code quality & typed contracts (after 54):** StrEnum vocabularies replacing string matching (ADR-128), OpenAPI-generated frontend types with CI drift guard (ADR-129), typed service/API boundaries killing `dict[str, Any]` (ADR-130), shared constants, assistant-ui adoption round 2 |

## Core principles

1. **Local-first** — all data (originals, extractions, DB, vectors) lives on disk; cloud is only for LLM/OCR APIs.
2. **Multimodal by design, OCR-first** — every visual asset is normalized to a canonical markdown "extraction" via Gemini Flash OCR. Text-only LLMs can run every pipeline; vision LLMs are an optimization, never a requirement.
3. **Originals are sacred** — nothing replaces uploaded files; everything derived is versioned alongside them.
4. **Everything is blocks** — questions, notes, chat, extractions share one structured content format (text/math/diagram/chart/image/table/code), renderable in UI and serializable for LLMs.
5. **Audit all AI** — every model call is logged (prompt version, tokens, cost) and every tutoring interaction is stored per attempt.
6. **Deterministic before probabilistic** — math answers checked with SymPy first; LLM grading only as fallback/rubric layer.
7. **User-owned engines** — providers, models, and per-task assignment are configured in the UI (doc 07); the app ships with no hardcoded engine choices.
8. **Profiles, not accounts** — several learners on one machine, no authentication; all user data is profile-scoped in the schema from day 1. English-only UI in v1, i18n wired from day 1.
9. **Behavior is contracted** — every AI behavior is a versioned *skill* with machine-checkable constraints (doc 08); "give a hint" can never leak the answer because a validator won't let it.
10. **Calm, motivating UI** — modern workbench aesthetics, instant feedback, visible mastery progress and tasteful celebration (doc 09); engagement without dark patterns.
