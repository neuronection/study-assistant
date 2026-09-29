# Changelog

All notable changes to **Study Assistant** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Release history from before the public launch lives in the
[git tags](https://github.com/neuronection/study-assistant/tags) and
[GitHub Releases](https://github.com/neuronection/study-assistant/releases).

## [Unreleased]
### Added
- **Uniform family turn-error display**: failed turns persist a
  display-only `turn_failed` marker row (survives refresh; excluded
  from the model context), `turn_error` events carry stable codes,
  family-uniform `TaskUnassigned` wording surfaces as
  `ai_not_configured` with an "Open AI settings" deep-link, and the
  streaming error card replaces the footer alert (`ChatMessage` error
  card + regenerate; `chat.openAiSettings` in en/de/el).
- **ADR-0023 desktop dev loop**: `run-dev.sh` runs shell-less desktop
  dev (SQLite profile, desktop identity) with the §11 shell gate armed
  only when the shell attaches (`SA_SHELL=1`); `--web` runs server
  identity against the Postgres dev-db. The DIM exchange mints the
  implicit owner to **loopback callers only** (kit-side).

- **Demo flavor + demo seeding + "Demo — synthetic data" badge (S8,
  identity-auth §13):** `docker/docker-compose.demo.yml` runs the real app
  as a public demo — own compose project, `demo-net` `internal: true`
  (zero egress) + an `edge` network only for the gateway (loopback-bound),
  database `neuro_study_demo`, `SA_DEMO_MODE=true` with `SA_APP_ENV=demo`
  (the entrypoint's production guard), registration disabled, and a
  one-shot `demo-seed` service (the app never auto-seeds); optional
  reset-on-restart via `--profile reset` (`demo-reset`). Demo data is
  synthetic-only and seeded exclusively by the new `scripts/seed-demo.py`
  (idempotent; clearly fictional users/courses/materials/notes/flashcards,
  several study profiles per persona) — the seeder **refuses anything
  else** loudly: a non-`*_demo` Postgres target or a SQLite target without
  an explicit `--demo-dir`, and any instance without
  `instance_settings.demo_mode=true` (`--init-demo` initializes that flag
  on an **empty** demo database only). The SPA shows a persistent
  "Demo — synthetic data" badge on demo instances — rendered before login
  (boot gate) with i18n (en/de/el) — fed by the new public read-only
  `GET /api/v1/instance/config` (`demo_mode` / `auth_mode` /
  `registration_enabled`, no secrets; session- and profile-exempt). The
  credential-free `demo` principal stays kit-owned (`POST /api/v1/auth/demo`,
  `demo` tokens rejected on non-demo instances).
- **Admin users UI + account self-service (ADR-0013 rollout, S7-users):**
  a Settings → **Users** tab (admins only) rendering the shared
  `AdminUserTable` from `@neuronection/assistant-ui` — list with activity
  counts, promote/demote, activate/deactivate, inline reset password,
  force logout, guard-rail errors surfaced as friendly messages — plus
  an **Account** card on the General tab: own sessions list with revoke
  (current device flagged and confirmed), self-serve password change
  (other sessions end, you stay signed in), and account deletion with
  password confirmation. Full i18n (en/de/el).
- **User management + account self-service API (ADR-0013 rollout,
  S7-users):** the family contract's §12 surface now ships from the auth
  kit — `GET /api/v1/admin/users` (listing with activity counts),
  `PATCH /api/v1/admin/users/{id}` (activate/deactivate, promote/demote
  — guard rails: no self-demotion/deactivation, no demoting the last
  admin, `ver` bump on change), `POST /api/v1/admin/users/{id}/
  reset-password` + `/force-logout`, `PATCH /api/v1/admin/instance`
  (admin + password re-verification, §4.5 transitions via the
  `request_transition` guard), `GET/DELETE /api/v1/me/sessions`
  (device labels from the User-Agent), `PATCH /api/v1/me/password`
  (other sessions die, the caller stays signed in), and
  `DELETE /api/v1/me` (password confirmed, cascades). `auth_sessions`
  gains an additive `created_at` column (migration 0067).

- **Session enforcement + login gate (ADR-0013 rollout, S4b):** every
  `/api/*` request requires a valid session (health and auth flows
  exempt); the WebSocket handshake verifies Origin and the session
  cookie; the app establishes its session before rendering (live
  cookie → refresh rotation → desktop one-time exchange) and shows a
  sign-in/register gate when there is none. `apiFetch` transparently
  refreshes expired sessions and returns to the gate when they are
  really gone. Desktop stays zero-setup: the shell token drives a
  silent exchange on first boot.
- **Family auth surface (ADR-0013 rollout):** `/api/v1/auth/*`
  (register, login, refresh, logout, logout-all, me, demo) with cookie
  sessions + double-submit CSRF; identity tables `users`,
  `auth_sessions`, `instance_settings`, `audit_events` (migration
  0065). Instance `auth_mode` is initialized once (`SA_AUTH_MODE` —
  server ⇒ `authenticated`, desktop ⇒ `open`) and read from the
  database on every request; desktop builds send a per-boot shell
  secret and the CSRF token with every API call. Session enforcement
  and the login UI follow in the same rollout.

### Changed
- **PostgreSQL 16 for web/server mode (ADR-0022 rollout, S3 — deployment
  breaking):** one dialect-aware schema family-wide. The migration chain
  (incl. the raw-DDL migrations 0002/0019/0020/0026/0045/0053/0057/
  0061) now runs cleanly on PostgreSQL 16 as well as SQLite. Search
  keeps identical behavior across dialects — `material_fts` ↔ tsvector +
  GIN (`'simple'` config), `material_fts_trigram` ↔ pg_trgm,
  sqlite-vec `chunk_vecs` ↔ pgvector HNSW (cosine), shared RRF fusion —
  verified by a two-dialect parity gate (same corpus + queries, ≥80%
  top-5 overlap). Backup archives carry `database.sqlite` or
  `pg_dump -Fc` `database.dump` and restore via `pg_restore`; the
  LangGraph checkpointer runs `AsyncPostgresSaver` on server mode and
  prunes on both dialects. Config: `SA_DATABASE_URL` (wins) /
  `SA_DB_NAME` / `SA_DB_USER` / `SA_DB_PASSWORD` / `SA_DB_HOST` /
  `SA_DB_PORT`; desktop + tests stay SQLite. SQLite files follow the
  family convention now: `<data_dir>/study.sqlite3` +
  `checkpoints.sqlite3`. Compose (`standalone`/`prod`/`dev-db`) runs
  `db + app + nginx + backup` on `neuro_study` with owner/app roles;
  `scripts/backup.sh`/`restore.sh` + a documented restore drill
  (`docker/README.md`); CI verifies migrations on **both** dialects.
  Known divergence: PG fuzzy recall uses whole-column trigram
  similarity (long materials can miss where SQLite's per-trigram match
  hits; precision identical via the shared post-filter) — follow-up:
  `strict_word_similarity`.
- **Per-user profiles with UUID ids (ADR-0013 rollout, S2b — breaking):**
  `profiles` now matches the family normative schema
  (guidelines/identity-auth.md §5): app-generated UUID `id`, `user_id`
  (NOT NULL, FK → `users`, ON DELETE CASCADE), `is_default` (exactly one
  per user), `updated_at`, product columns `color`/`preferences` kept,
  plus `last_used_at` (§6). Every `profile_id` column is a UUID and its
  rows cascade on profile delete. User creation auto-provisions the
  Default profile in the same transaction; deleting the last profile
  re-provisions it. The `/api/v1/profiles` surface is user-scoped,
  `ProfileOut.id` is a string and carries `is_default`, `PATCH
  /api/v1/profiles/{id}` (rename/recolour/set Default) is new, and
  delete cascades content instead of refusing. Migration **0066** is the
  destructive, irreversible greenfield baseline (no backwards
  compatibility — recreate dev databases and reindex; see
  docs/dev/data-model.md Migration notes).
- **Profile binding (ADR-0013 rollout, S5):** `X-Profile-Id` is
  ownership-validated on every domain call (identity-auth §15) and its
  value is a string UUID — server mode requires it (absent ⇒ 400;
  malformed, unknown, or foreign ⇒ 403), desktop falls back to the
  last-used profile, and auth/`/me`/`/profiles`/`/admin` stay exempt.

- **Documentation is now split by audience** — the manual lives under
  [`docs/user/`](docs/user/README.md) (end-user guides) and
  [`docs/dev/`](docs/dev/README.md) (developer and operator guides), with a
  machine-readable [`docs/docs-tree.json`](docs/docs-tree.json) navigation
  tree consumed by the website's docs section. The local-AI settings hint now
  points at `docs/user/local-ai.md`.

### Fixed
- **Blob loads over browser navigations** (PDF iframe documents,
  `<img>` subresources): both header gates (`X-Profile-Id` web-mode
  400, `X-Shell-Token` desktop 403) can never be satisfied by a
  navigation — `/api/v1/blobs` is exempt from both and owner-scopes
  the sha itself (ADR-0025). Also closes a data leak: any sha was
  previously fetchable by any authenticated caller; foreign and
  unreferenced shas now answer 404.
- **WS surface owner-scoped** (identity-auth §10): topic subscriptions
  must resolve to resources the caller owns (fail closed); client-side
  `publish` removed from the protocol (event-injection vector); editor
  transform jobs stamp their creator and answer 404 for foreign ids.

### Security
- Turn errors and job error rows are sanitized before persist/emit
  (credential-shaped material — DSNs, bearer tokens, API keys, JWTs —
  scrubbed).

- **Unauthenticated web surfaces closed** (family ADR-0013 rollout, S1):
  filesystem browsing is confined to granted roots (`SA_FS_ROOTS` +
  data dir + home), the WebSocket verifies its `Origin` before accept,
  CORS is explicit and deny-by-default (`SA_CORS_ORIGINS`), and the
  desktop-only file endpoints are no longer mounted in web/server mode.

## [v0.11.1] - 2026-09-20

### Added
- **Resizable course structure sidebar** — drag the sidebar's right edge to
  resize it (220–420 px, persisted).
- **Tree auto-expands to the current section** — navigating to any section
  at any depth expands its full ancestor chain, scrolls it into view and
  moves the keyboard cursor there (previously skipped whenever any expansion
  state had been saved).

### Fixed
- **Course structure sidebar was invisible in the real browser build** —
  an unlayered `.hidden { display: none }` from the bundled library
  stylesheet outranked layered responsive utilities in the CSS cascade
  (layers beat source order), so `hidden md:flex` collapsed the sidebar to
  zero size at every viewport — jsdom tests never see CSS, so it slipped
  through. The sidebar (and the chat "Quiz me" label, same pattern) now
  use layered `max-*` variants (`max-md:hidden` / `max-lg:hidden`); a
  real-browser Playwright regression spec (`06-tree-sidebar`) asserts the
  sidebar renders with actual size on a course workspace.

### Changed
- **Course structure sidebar is always visible in the course workspace** —
  the hide toggle is gone (a previously closed sidebar can no longer stay
  hidden), and the tree gained a visual refresh: indent guides, folder
  icons that reflect expansion, leaf dots, an accent bar on the active
  section and softened hover states.

## [v0.11.0] - 2026-09-20

### Added
- **Deep navigation: jump anywhere in a course (plan 80)** — the command
  palette now indexes every section of every course at every depth (with
  breadcrumb subtitles and matching on parent names, not just titles), so a
  depth-3 section opens in a few keystrokes instead of three drill-downs.
  Profile recents power a **"Continue where you left off" card** on Home, a
  Recent section atop the palette, a **"Jump back in" list** on the course
  overview and last-visited links on the course cards; the sidebar filter
  jumps to the selected match on Enter; and content-search results (palette
  `?query` and Library) deep-link into their section with the material
  docked in the workspace.
- **Interface feature-visibility toggles (plan 80)** — Settings → General
  → "Interface & features" hides or shows the recents surfaces (Home
  continue card, palette recents, course overview strip, course card meta)
  instantly; preferences persist locally.
- **MCP remote transports (custom connectors)** — stdio servers gain
  remote-transport and keyring secret support (desktop parity).
- **Two-pane family settings shell** — Settings is reorganized into
  grouped AI sections shared with the family apps.
- **BYOK one-click provider setup (plan 79, family plan 17 Phase 2)** —
  **Add provider** in Settings → Providers now opens a setup dialog with
  neutral one-click preset tiles (OpenAI, Gemini, OpenRouter, Anthropic,
  Groq, Mistral, DeepSeek, Ollama — same family order and curated model
  allowlists as every family app, synced from the family contract file).
  Picking a provider shows its key steps (with copy buttons), free-tier
  note and key link; connecting validates the key by fetching the
  provider's real catalog first (a rejected key persists nothing), saves a
  curated model default (snapshot-dated ids recognized automatically; if
  none match, the full catalog is saved and flagged), then sets up default
  chat/vision and speech-to-text (whisper) models without ever
  overwriting live assignments. Re-setup never duplicates providers
  (manual rows with the same type + base URL are adopted) and appends
  instead of replacing. Advanced discloses the API base URL (locked for
  fixed-base providers), hosting and country — edits there save through
  the manual form, as does the Custom tile (full manual fields:
  name, base URL, key, hosting, country). Setup failures are routed by
  stable error codes with a vendor mis-paste hint; model capabilities now
  use the family `stt`/`tts` vocabulary end-to-end (migration 0064
  rewrites stored values), with the gates (`check-byok-contract.sh` +
  ai-alignment) enforcing the contract in CI.

### Changed
- **assistant-ui 0.42.0 → 0.43.0** — family catch-up (drop-in).
- **Sidebar family menu lists Desktop Assistant** — new row (library
  `DesktopMark`, linking to neuronection.com/en/desktop/) alongside
  Health / Career / Study.

## [v0.10.0] - 2026-09-18

### Fixed
- **Desktop webkit fallback hardening (ported from career-assistant
  v0.11.x)** — the renderer-sentinel relaunch crashed on an invalid
  logging kwarg (`argv=`), so the software fallback never engaged; the
  fallback now also disables the WebKitGTK bubblewrap sandbox, forces
  the X11 GDK backend, pins EGL+GLX to Mesa when the default glvnd
  vendor is broken hardware, persists a `webkit_soft_fallback` marker
  in the data dir (later boots skip the blank GPU attempt), and every
  launch logs its render mode at WARNING. The .deb build now fails if
  any GL/X/render library survives the strip (regression guard).

### Added

- Tutor chat: the tools catalog now lists the assistant's proposal abilities
  as first-class HITL capabilities ("propose edits", "propose generations")
  with a warning-tone badge, and turns whose suggested actions fail
  validation say so honestly — a warning line plus per-fence reason codes
  (`trace.proposals_dropped`) instead of silently vanishing proposals
  (plan 78-A, ADR-192; family ADR-0015 conformance).
- Tutor chat: proposals are now grounded — every target id is checked
  against the offered manifest at contract time, and edit-in-place proposals
  (note/material edits and appends) require the target's full content to
  have been read in the same turn; ungrounded proposals trigger a repair
  round that names the exact `READ` call to make, and are dropped with an
  honest reason instead of becoming cards that can never apply (plan 78-B,
  ADR-192).
- Tutor chat: note and material edit proposals can now carry anchored
  `text_edits` (replace-with-exact-anchor / append / prepend) that resolve
  server-side against the current content — surgical diffs for targeted
  changes instead of whole-document regeneration, with
  mismatch/ambiguity/conflict dropped by stable reason codes (plan 78-C,
  ADR-192).
- Tutor chat: approving a proposal whose target changed in the meantime no
  longer dead-ends as stale — the card flips to "Changed" with the diff
  refreshed against the current content for explicit re-approval (anchored
  edits preserve interim manual edits), and the tutor now learns the outcome
  of its earlier cards on the next turn so it stops re-proposing resolved
  changes (plan 78-D, ADR-192).
- Tutor chat: suggested actions are now visible and resolvable outside the
  conversation — a cross-session proposals list (`GET /chat/proposals`), a
  pending count in the notification bell with a link to chat, and a badge on
  the chat rail entry (plan 78-E, ADR-192).
- Tutor chat: content-bearing proposals (create/edit/append notes and
  materials) gained a rendered preview — an eye button or clicking the card
  subject opens a large modal rendering the actual content (math, diagrams,
  tables) through the app's markdown surface, so nothing has to be judged
  from raw JSON (plan 78-F, ADR-192).
- Opening a material or note in the course workspace now docks it as a
  resizable, non-modal side panel beside the tutor chat instead of a modal
  drawer — the workspace stays fully interactive, both rails remember their
  widths, expand jumps to the full-page view, and deep links and back-button
  behavior are unchanged (ADR-191).
- Loading states across the app now use soft skeleton placeholders instead
  of spinners, and a keyboard shortcuts help overlay documents every binding
  in one place (plan 77-A).
- Materials show an index-card hover preview — summary, topics and metadata
  surface on hover without opening the file (plan 77-B).
- Extraction history and drawing re-OCR reviews now render the old-vs-new
  diff in the same formatted view as chat proposals — math, tables and
  headings render, unchanged blocks fold, raw view one click away (plan 77-C).
- One-tap "Study now" guided session: the home screen's Study action chains
  what the app knows needs doing — review, practice and wrap-up — from a
  single deterministic recommendation aggregate, no LLM in the loop (plan 77-D).
- The Concepts tab gained a persisted List ⇄ Graph toggle that renders the
  course's concept relations as an interactive canvas colored by mastery
  (plan 77-E).
- Materials and course tree nodes now join the trash — deleting them is
  recoverable via restore, like notes and quizzes before (plan 77-F).

### Changed

- Visual token refresh: softer two-layer elevation shadows, dark-mode shadow
  tuning, the success color deepened to meet WCAG AA contrast (with a new
  automated contrast gate so it stays there), and all hardcoded Tailwind
  shadows swept onto tokens — conservative, no component redesign (plan 77-G).

- Adopt `@neuronection/assistant-ui` 0.42.0 (chat-tools-catalog badge chip,
  chat-hitl module enhancements, ModalBody compound, token refresh).

## [v0.9.1] - 2026-09-16

### Changed

- Adopt `@neuronection/assistant-ui` 0.37.0 (session-list title wrapping,
  softer chat-bubble radius, standalone `InfoTooltip`, settings-shell
  container-query layout modes) and refresh the minor/patch dependency
  drift (React 19.3, TanStack router/query/virtual, i18next, lucide-react,
  framer-motion, vite, eslint, and friends). Rendering majors (plotly 4,
  mermaid 12, katex 0.18) and toolchain majors (TypeScript 7, vitest 5)
  are deliberately held for dedicated passes.

### Fixed

- Tutor page (`/chat`): the chat history panel now scrolls on its own while
  the conversation and composer stay fixed (previously the whole page
  scrolled as one), and the input is the standard multiline composer that
  grows with the message like in Career Assistant.
- Startup: a stray `.env` in the working directory no longer crashes the
  app at boot — unrelated keys in it are now ignored (only `SA_*` settings
  are read).

## [v0.9.0] - 2026-09-16

### Added

- Custom MCP connectors: register your own external MCP servers in
  Settings → Integrations, refresh to list their tools, and assign each tool
  as a discovery source (appears in Discover and chat DISCOVER) or a parser
  (keyed by a URL pattern, runs inside Import & parse). Servers are disabled
  by default, invocations are audited and time-boxed, and all external
  output is validated before use. (plan 73-G, ADR-170)
- Chat discovery with approval-only attach: the chatbot gained a DISCOVER
  tool (web, YouTube and site presets; `DISCOVER here` searches for the
  current topic without typing a query) and an attach_link proposal that
  turns a found URL into a placed link reference after you approve it.
  (plan 73-F, ADR-167/170)
- External web sources: add RSS/Atom feeds, YouTube channels or playlists and
  site-filtered searches as standing sources — a deterministic scheduler scans
  them on a schedule (manual "Scan now" included) and new items land as
  suggestions in the Discover dialog, never auto-imported and never LLM-called.
  Settings → Integrations gains the Web sources card; sources travel inside
  course bundles with fresh cursors. (plan 73-E, ADR-167/170)
- Discovery suggestions & Discover dialog: search results can now be kept —
  save for later, dismiss, or attach/import them as link materials, with one
  tracked row per normalized URL per profile and a "Saved & dismissed" list in
  the new Discover dialog (course Materials tab and Library create menus).
  Settings → Providers gains a Discovery card for provider toggles and
  site presets. (plan 73-D)
- Discovery provider registry: search across web, YouTube, and site-filtered
  presets (Khan Academy built in) through one normalized, never-persisted
  search endpoint with honest per-provider errors. (plan 73-C, ADR-166)
- Parser registry & YouTube transcripts: the "Import & parse" verb on link
  references now works — YouTube videos gain searchable, timestamped
  transcripts, direct file URLs (PDF, Markdown, Office, audio…) download into
  the standard library pipeline, and plain pages convert like the URL
  importer. Links without captions say so and offer one-click audio
  transcription; re-parsing keeps version history. (plan 73-B, ADR-165)
- Link materials: paste a URL to keep it as a real, first-class reference —
  placeable at any topic, taggable, starable and searchable, with
  database-enforced dedupe on normalized URLs (YouTube short links and
  tracking parameters count as the same link). The URL import dialog now
  defaults to attaching references, with full import remaining one click
  away. (plan 73-A, ADR-164/171)
- Async compose with progress and cancel: composing study material no longer
  blocks the app for the whole generation — documents are generated as a
  cancellable background job with live progress, single-job status polling
  and a cancel button; the chat approval path stays synchronous.
  (plan 70-D, ADR-156)
- Validated practice sets: AI-composed practice sets are now authored as
  structured items whose answers are verified server-side (SymPy-checked
  equations, distractors can't equal the answer, parseable numeric values)
  before the document is saved — a broken generation is repaired or refused,
  never persisted with a provably wrong key. (plan 70-C, ADR-158)
- Compose orphan-material awareness: when composing at a topic, materials
  that were uploaded but never placed anywhere are no longer silently
  ignored — the dialog offers an opt-in checkbox to also draw on them, with a
  shortcut to the course materials tab for placing them properly. (plan 70-B)
- Compose coverage honesty: AI-composed documents now measure how much of the
  scope's material retrieval actually surfaced (deterministic accounting, a
  diversified second retrieval round when a large scope is thinly covered)
  and report it — the GenerateDialog result names the shortfall ("Built from
  8 of 14 materials — 6 weren't retrieved.") and flags the document for
  review when coverage stays thin. The same review flag is now surfaced for
  formula sheets, whose "needs review" marker previously had no visible
  consumer. (plan 70-A, ADR-157)

### Changed

### Fixed

- Viewer drawer: no longer clipped off the left edge of the window while the
  chat side panel is docked — the overlay panel was double-inset by the chat
  width (once in the backdrop, once in the panel). It now sits flush against
  the chat dock and clamps to the available width on narrow windows.
- Viewer drawer: the material body is now the single scroll owner — the overlay
  panel no longer keeps a second, competing scrollbar (the inner one previously
  had only a few pixels of travel while the panel did the real scrolling).
- Viewer: display math indented inside list items no longer leaks raw LaTeX as
  red KaTeX errors — the `$$…$$` fence canonicalization now preserves the
  line's indentation instead of emitting a mixed-indent closing fence that
  remark-math rejects (`normalizeMathFences`).

## [v0.8.1] - 2026-09-10

### Added

- GitHub Sponsors funding (Buy Me a Coffee only) via `FUNDING.yml`.

### Changed

- README: direct stable download links for release assets, quick-start reorder,
  family wordmark colophon, new community and security sections, and a Website
  link in the header.
- Release workflow uploads stable-name download aliases next to the versioned
  assets so README links survive future releases.

### Fixed

- Graph chat engine: round-close straggler dropping now applies only to tool
  rounds, so a final answer's trailing token chunks are no longer dropped when
  the round-end flush races the merged token queue (regression from the
  2026-09-09 tool-call leak fix; could truncate streamed answers under load).
