# Changelog

All notable changes to **Study Assistant** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Release history from before the public launch lives in the
[git tags](https://github.com/neuronection/study-assistant/tags) and
[GitHub Releases](https://github.com/neuronection/study-assistant/releases).

## [Unreleased]

### Changed

- **Chat adopted the family Airy surfaces.** Assistant replies render as flat
  prose beside a small identity orb, the transcript groups consecutive turns,
  the empty state is the shared glowing welcome kit with suggestion cards, and
  an unconfigured dictation model now shows a quiet muted mic whose popover
  explains the setting instead of a persistent notice above the composer.

## [v0.15.0] - 2026-11-22

### Changed

- **AI setup now ends on task assignments.** The provider wizard asks for
  the provider, then the defaults, then — only if no default could be set —
  for models, and its primary action opens Settings → AI → Tasks. Per-task
  overrides (decision kinds and specialist tasks) are a collapsed
  **Advanced** disclosure under the visible default models.

### Fixed

- **The "Dictation unavailable" notice no longer squeezes the chat
  composer.** It renders as a full-width, dismissible strip above the input
  row instead of a prose row inside the toolbar; the input keeps a minimum
  width at narrow panel sizes. The notice stays dismissed per profile until
  speech-to-text is configured again.

## [0.14.3] - 2026-11-20

### Changed

- **Per-app cookie names (auth-kit 0.7):** session cookies are now
  `sa_access` / `sa_refresh` / `sa_csrf` (previously the shared family
  `nx_*` names). Cookies are scoped by hostname — ports are ignored —
  so co-located Neuronection apps on one host no longer shadow each
  other's sessions or CSRF jars. **You are logged out once on
  upgrade**; stale `nx_*` cookies are cleared automatically on your
  first request.

### Changed (installer)

- **Default port is now 8091** (was 80) — the per-product family default
  (health 8090 / study 8091 / career 8092), so several Neuronection
  apps coexist on one host with no flags. Existing installs keep their
  persisted port; an install whose `docker/.env` predates persisted
  ports stays on 80 with a loud note instead of silently moving.
- **`--public-url URL`** persists `SA_PUBLIC_URL` (drives Secure
  cookies, CORS and OAuth redirects; `http://` keeps LAN logins
  working). The summary now prints the configured public URL as the
  app URL when one is set.
- **`--bind ADDR`** (default `0.0.0.0`) publishes on a chosen interface
  — `127.0.0.1` when you front the app with your own reverse proxy.
- **`scripts/uninstall.sh`**: clean removal that keeps data by default
  (`--purge` deletes only this project's volumes; `--remove-dir`
  explicit; label-based teardown works without a readable `.env`).
- `backup.sh` and `restore.sh` gained `-h|--help` like the other
  scripts.

## [Unreleased]

## [0.14.2] - 2026-11-20

### Fixed (installer)
- **Fresh installs generate a usable Fernet data key.** `SA_DATA_KEY` was
  generated with `secrets.token_urlsafe(32)` — 43 characters with the base64
  padding stripped — and the backend refused to boot with
  `SA_DATA_KEY must be usable Fernet material`. The installer now uses a
  dedicated stdlib Fernet generator (32 random bytes, urlsafe base64 with
  padding). An existing install with the invalid key should replace just that
  line in `docker/.env` before first boot; do not delete the env file, because
  the database roles are already initialized with its passwords.

## [0.14.1] - 2026-11-20

### Fixed (installer)
- **One-line installs survive GitHub's release asset redirect.** GitHub now
  serves `/releases/download/...` assets from
  `release-assets.githubusercontent.com`; the bootstrap host allowlist only
  accepted `github.com` and `objects.githubusercontent.com`, so a fresh
  install aborted before extracting anything. The allowlist now includes the
  new host, and the release bootstrap is rebuilt from this commit.

### Fixed (release tooling)
- **The OpenAPI schema version is propagated with the app version.** A patch
  or minor bump no longer leaves `frontend/openapi.json` one release behind
  and trips the CI drift guard; the schema's `info.version` now updates in
  the same release commit.

## [0.14.0] - 2026-11-20

### Added
- **Self-host installer and source-free release bundle (plan 69).** A fresh
  Docker host can install Study Assistant from the published release with
  `scripts/install.sh` or the generated one-line `scripts/bootstrap.sh`.
  `installer.json` is the product contract; the bundle carries
  `manifest.json` and `SHA256SUMS`, and `scripts/update.sh` provides the
  idempotent upgrade path. Install flags include `--no-pull`, `--no-wait`,
  `--auto-ports`, `--no-ports`, `--http-port`, `--env-only`, `--reset`,
  `--yes` and `--image-tag`. Release CI now publishes
  `study-compose-v0.14.0.tar.gz`, `study-bootstrap.sh` and
  `study-bootstrap-v0.14.0.sh`; `install-scripts.yml` and
  `release-smoke.yml` exercise the installer and the published assets.

### Changed
- **Deployment conformance (plan 64 W1-C: ADR-0062 v7 §3-§5, ADR-0063,
  ADR-0064).** Two DB roles, two credentials: the owner DSN
  (`SA_MIGRATIONS_DATABASE_URL` / `SA_DB_OWNER_PASSWORD`) now lives only in
  the one-shot `migrate` service — the `app` service carries the app DSN
  alone, and `entrypoint.sh serve` refuses a boot that carries the owner
  DSN. Every `migrate` run bootstraps/syncs the app role as owner (create,
  password rotation, DML-only grants, `ALTER DEFAULT PRIVILEGES`,
  `vector`/`pg_trgm` verification with a managed allow-list note) and
  provisions the checkpoint schema; migrate mode resolves the ADR-0064
  tri-state (split / legacy warning / `SA_DB_SPLIT=1` without a URL
  refuses to boot). New `GET /ready` ingress probe (DB at migration head,
  required storage, boot complete; 503 otherwise; soft signals — Redis is
  `none` — never flip the status) beside the unchanged
  `GET /api/v1/health`. Cookie `Secure` is now **derived from the public
  scheme** (`SA_PUBLIC_URL` or `SA_TLS=1`; explicit `SA_COOKIE_SECURE`
  still wins) so LAN/VPN logins over HTTP keep working;
  `SA_TRUSTED_PROXY_COUNT` is wired in both compose flavors. Backups:
  `scripts/backup.sh` uploads off-host (rclone / aws s3 / azcopy via env),
  appends a `backup_runs.jsonl` ledger row per run, and `restore.sh`
  re-grants the app role after `pg_restore`; the restore drill is
  documented in `docs/dev/deployment.md`. Desktop (`python -m
  studyassistant`) is unchanged; the macOS packaging gap stays documented.
- **Read-only storage status card and `app.storage` settings domain (plan 55
  P4b2).** Admins get Settings → Developer → Storage, a read-only card fed by
  `GET /api/v1/admin/storage/status`: backend, bucket/container, prefix,
  region/endpoint host, SSE, per-object cap, presign TTL and the cached live
  health row, with a **Test connection** action (`?refresh=true` forces a
  fresh probe). There is no credential form, provider tile or backend switch —
  changing backends stays a verified migration. Non-admins receive 403 and
  cannot deep-link the section; desktop renders nothing. The response redacts
  credentials, connection strings, presigned URLs and the full endpoint URL.
  The family `app.storage` settings-map domain (scope `instance (admin)`,
  secrets `none`) is declared and vendored; the conformance test pins study's
  developer sections. Tests: `test_storage_status.py` (admin/non-admin,
  redaction, cache/refresh) and `StorageStatusCard.test.tsx`
  (render/refresh/error, non-admin/desktop).
- **Storage health is on `/api/v1/health` and boots log a redacted storage
  line.** The health row reports the backend, `ok`/`degraded`/`unavailable`
  and whether storage is required; the probe is cached for 30 s and bounded
  to 5 s (a slow provider cannot outlive the healthcheck), a transient
  provider failure or probe timeout degrades open (200), and the endpoint
  returns 503 only when storage is required or the failure is sustained. A
  missing bucket is still a boot error. The manual `Cloud storage smoke`
  workflow runs the AWS and Azure provider tests on demand; normal PRs stay
  local-only.
- **Adopted the family object-storage contract (plan 55 P1 / ADR-0057).**
  `BlobStore` is now a thin wrapper over the vendored
  `app/storage/object_storage.py`: the legacy `<aa>/<bb>/<sha>` layout and
  `put/get/has/known_shas` are unchanged, writes are atomic through the
  contract, and new `stream`/`materialize`/`delete` methods replace durable
  path use. Every direct `blobs_dir` seam was re-seamed (sources, course
  export/import/duplicate, scan scheduler, lecture purge, blob streaming),
  `SA_*` storage settings bootstrap `app.state.objects`, and the web image
  installs the optional `object-storage-s3` extra. The effective storage cap
  tracks the host's 200 MB upload ceiling (oversized uploads return 413, not
  500), and blob downloads use `attachment` + `no-store` + `nosniff` by
  default (inline only for images). The library's PDF original view fetches
  the bytes and renders a revocable `blob:` URL, so the download policy stays
  intact without breaking in-app preview. Backup/restore/reset stay
  desktop/local-only: an object backend returns 409 instead of archiving an
  empty `blobs/` tree, and the compose backup sidecar skips its `/data` tar
  under a cloud profile. Desktop behavior and data directories are unchanged.
  New contract/migration tests plus an env-gated MinIO/S3 smoke test are
  documented in `docs/dev/storage.md`.
- **Retired compatibility paths removed (no users exist).** The
  `price_source='legacy'` marker is gone from the enum/CHECK (migration
  `0035_drop_legacy_price_source` maps any residue to `unknown`), and the
  pre-scope global audio-cache purge (`purgeLegacyAudioCache` and its
  localStorage key) is deleted. New installs carry no migration state.

## [0.13.1] - 2026-11-18

### Fixed
- **Corrected the source-free deploy bundle.** The v0.13.0
  `study-compose-v0.13.0.tar.gz` omitted `docker/init-db.sh`; the bundle
  builder now includes it. The bundle also pins the compose base images
  (pgvector `0.8.7-pg16`, nginx `1.31.8-alpine`) and widens the DB
  healthcheck start period. No application behavior change — the app image
  is unchanged apart from the version metadata.

## [0.13.0] - 2026-11-13

### Changed
- **Revoked account rows use the library sign-out flag (plan 60 Phase 4 follow-up).**
  `@neuronection/assistant-ui` moves to `^0.88.0` and Settings → Account marks
  already-revoked sessions with the row's `revoked` flag instead of an app-side
  chip: the library renders its **Signed out** badge (`labels.revoked` stays the
  localized `settings.account.sessionRevoked`) and no **Sign out** action, so
  `revoked_at` sessions are read-only content rather than a no-op button. Active
  rows keep the confirm-then-revoke flow, the current-session sign-out warning
  and the per-row busy state; a successful revoke now returns focus to the
  sessions heading and the result line is announced (`role="status"`). This
  supersedes the 0.86.0 note above (revoked rows carried the action then).
- **Onboarding provider setup uses the shared provider grid (plan 113 C/D).**
  The wizard's provider step now reuses the same `ProviderSetupTiles` +
  `ProviderSetupForm` flow as Settings, including capability chips, guided key
  checklists and the local-engine companion tile. Preset setup hides the
  auto-derived connection name, hosting and country; the Custom path keeps the
  fields it needs. Local-engine adds route through the preset setup when the
  detected engine is a known preset, and the legacy
  `useProviderCreate`/`ProviderCreateFields` path is deleted. The standalone
  local-engine block in the Providers empty state is replaced by the grid tile.
  The wizard's **Pick default models** step now uses the same library
  `TaskAssignmentPicker` as Settings → AI → Tasks and auto-fills missing
  capabilities from enabled models; wizard provider setup binds curated
  defaults instead of passing all `bind_*: false`.
- **Onboarding data location is desktop-only and explicit (plan 113 A/B).** The
  first-run wizard hides the working-directory step on server identity, and the
  welcome copy no longer claims local-only storage there. The shared
  `WorkingDirEditor` now shows the current path read-only until **Change
  folder…** is chosen; the desktop shell opens the system folder picker through
  a dedicated `pick_data_dir` bridge that does not register the data directory
  as an upload root, while browser development falls back to manual editing.
  Settings → Data hides the same card on server identity, and the config routes
  return 404 there. The restart-pending banner no longer prints the current
  path as if it were the pending one.
- **Account sessions render through the shared library list (plan 60 Phase 4).**
  `@neuronection/assistant-ui` moves to `^0.86.0` and Settings → Account uses
  the library `AccountSessionList` (new `components/ui/account-session-list`
  shim): the local session-row markup is gone, rows keep the signed-in/expiry
  line, the current-session badge and the "Signed out" chip, and a revoke in
  flight disables only that row's button until the request settles. Revoked
  rows now also carry the library sign-out control (the shared row has no hide
  action; the server DELETE is idempotent), as career documents. The
  confirmation dialog, error banner and password/account-deletion flows are
  unchanged.
- **The canonical extension source grammar is vendored** as
  `backend/app/extensions/extension_sources.py` (byte-identical to the family
  contract, synced by `scripts/sync-extension-contract.sh`). Nothing consumes
  it yet — it is the one parser for extension-source URL / ref / subpath /
  commit-sha / archive-entry grammar, so no behaviour changes.

### Added
- **Data & Cost (plan 58 P1).** AI calls now record integer micro-USD cost plus
  provenance at call time (`usage_source`, `estimate_method`, `price_source`,
  `price_version`); the old float `cost_usd` and per-model `cost_in/cost_out`
  are migrated once to exact `ai_price_overrides` rows and dropped. The Data
  tab shows month/task totals, recent calls, built-in list prices and custom
  overrides (`/api/v1/ai/prices`), with the standard/uncached/non-batch
  disclaimer. Existing money caps are stored as `monthly_cap_micros`.
- **Capture inbox (plan 90-A).** The New menu's **Take photo…** action stages
  camera/file photos first: a capture inbox lists them with status, size and a
  preview, and only **Add** commits one into the open course/topic through the
  normal upload + OCR path. Staged captures expire after 7 days by status only
  (no blob deletion); a profile-scoped `client_op_id` makes offline replays
  idempotent. Backend: `capture_staging` + `capture_tokens` (migration 0020),
  `/api/v1/capture` stage/list/commit/discard, and a device-credential token
  service for the upcoming share target/clipper.
- **Text highlights (plan 90-B).** Select a passage in a material and choose
  **Highlight**; the mark stores the extraction version, quote and occurrence,
  keeps an optional note and one of four colors, and appears in the reading
  header's Highlights panel. Extraction edits and re-ingest re-locate a highlight by quote or
  mark it **source changed**; highlights are excluded from course bundles.
  Backend: `document_anchors` (migration 0021), the `AnchorPayload` validator
  and `/api/v1/materials/{id}/anchors` + `/api/v1/anchors/{id}`.
- **Offline capture journal (plan 90-E).** Photos taken without a connection
  wait in the capture inbox as **Waiting for connection**, saved in IndexedDB
  (session-only where durable storage is unavailable), and drain
  automatically on reconnect through the same staging endpoint with an
  idempotent client op id. Retry / Retry all / Remove per item; one failed
  capture never blocks the others. No schema change.
- **Secure-connection report (plan 92-G).** Settings → General → Connection
  shows whether the current origin can install the app, accept a phone share,
  use the microphone and show notifications, with an honest **Plain HTTP**
  state and a "what needs HTTPS" note instead of controls that silently
  vanish. Adds `lib/secure-context.ts`, a `docs/dev/tls-and-secure-context.md`
  guide (bundled nginx TLS, Caddy, local CA) and a TLS section link; desktop
  reports **Desktop app** separately. No schema change.
- **Installable web app + mobile shell (plan 92-A).** The web build now ships
  a manifest with maskable icons and a small app-shell service worker
  (production, secure origins only; `/api` and `/ws` stay network-only), an
  install action in Settings → General → Connection, and a mobile bottom bar
  (**Home · Courses · Review · Capture · More**, with search in More). The
  shell uses `100dvh`/safe-area insets and leaves room for the bar; Capture
  enqueues through the offline journal, so a photo can be taken and filed
  from any page. **Offline review ratings** are queued in the same journal,
  replayed with their original review time (`reviewed_at`), with a
  **rating saved offline / Sync now** pill; the review endpoint accepts
  `reviewed_at` inside a 30-day, no-future window. No schema change.
- **Multi-page scans (plan 92-B).** When more than one photo is staged, the
  capture inbox shows a page filmstrip: reorder, rotate in 90° steps, remove a
  page, name the scan, and **Combine into PDF**. The server assembles the pages
  with PyMuPDF into one staged PDF, discards the source image rows and commits
  through the normal upload/OCR path. Tests: `test_capture_api.py`,
  `ScanPages.test.tsx`.
- **Study pace settings (plan 99-A).** Settings → General → Study pace adds
  Light / Standard / Intense presets plus retention target, maximum interval,
  daily new/review caps, leech threshold, sibling burying and load balancing.
  FSRS parameters resolve course → profile → defaults, so existing profiles
  keep today's 90%/365-day behaviour until they opt in; per-course overrides
  are available through `/api/v1/study/courses/{id}/fsrs`. Schema: migration
  0022 (`fsrs_settings`, `course_fsrs_overrides`). Tests:
  `test_fsrs_settings.py`, `FsrsSettingsCard.test.tsx`.
- **Review filters, preview mode and daily cap (plan 99-B).** The review page
  gains Due today / Ahead N days filters, saved profile-scoped filters, a
  **Preview** chip with **Reschedule as reviewed**, and a daily-cap banner.
  Preview ratings log `review_log.source=cram_preview` without touching FSRS;
  real reviews stay `review`. `GET /review/due` accepts filter/course/node/
  window/order/limit, returns `preview`/`capped`/`remaining_today`, and honors
  the profile's reviews-per-day cap. Schema: migration 0023 (`review_filters`,
  `review_log.source`). Tests: `test_review_api.py` (filters, preview, cap),
  `ReviewPage.test.tsx` (preview path).
- **Retention & workload analytics (plan 99-D).** Scores gains a **Retention**
  tab: true recall over the last 90 days vs the target, young/mature interval
  buckets, review/lapse counts, and a 30-day workload chart with new-card
  availability and the peak day. New endpoints `GET /analytics/retention` and
  `/analytics/workload` are honest about empty samples. No schema change.
  Tests: `test_analytics_retention.py`, `RetentionTab.test.tsx`.
- **Adaptive weekly plan (plan 99-C).** Home gains **Plan my week**: a
  deterministic cross-course draft paced by exam proximity, weak concepts, due
  cards, untouched topics and daily capacity, with per-day minutes, evidence
  lines, manual items preserved and an honest overflow count. **Add to plan**
  writes `origin=generated` rows (replaced as a block on the next commit).
  Capacity (7 weekday minutes, light week, blackout dates) is editable in the
  dialog. Migration 0024 widens `plan_items.origin` with `generated`. Tests:
  `test_adaptive_plan.py`, `WeekPlanDialog.test.tsx`.
- **Speech-to-text capability gate (plan 94-F).** When no STT task has a model,
  the chat composer shows an **Assign a speech-to-text model** link instead of a
  mic that would fail after recording. Tests: dictation panel test.
- **First-run funnel events (plan 101-F).** Onboarding completion, first review,
  first finished quiz and first capture are recorded once per browser via a
  local `sa-first-event.*` dedupe; failed writes retry on the next action.
  Tests: `activation-events.test.ts`.
- **One-time contextual tips (plan 101-G).** Library, Review and Practice each
  show one dismissible first-use tip, persisted as `sa-tip.<id>` and recorded
  through the local-only counters. No modal tour. Tests: `OneTimeTip.test.tsx`.
- **Voice settings polish (plan 94-F).** Voice & audio adds a persisted speaking
  speed used by browser read-aloud and the test phrase, plus an honest audio-
  input count hint (labels need microphone permission). Tests:
  `VoiceAudioCard.test.tsx`, `ReadAloudButton.test.tsx`.
- **Offline audio downloads (plan 94-C).** The global player can cache the
  current track in the browser Cache API and remove it again; cached audio is
  served from the cache when the browser is offline. Tests:
  `AudioPlayerBar.test.tsx`.
- **Browser voice picker (plan 94-F).** Settings → General → Voice & audio
  lists the browser voices and persists the choice (`sa-browser-voice`);
  read-aloud and the test phrase use it. Tests: `VoiceAudioCard.test.tsx`.
- **Searchable feature map (plan 101-G).** The `?` shortcuts dialog now has a
  **Find a feature** search over Capture · Read · Practise · Review · Organise ·
  Configure, with deep links and quick-capture/import actions. Tests:
  `ShortcutsDialog.test.tsx`.
- **Frontend performance budget and route splitting (plan 101-D).** Every page
  route (including Home) is lazy; the shell and chat dock stay eager. German
  and Greek locale dictionaries load on demand. A deterministic gzip budget
  (`pnpm --filter frontend check:bundle`) fails CI if the 300 kB entry or
  900 kB initial JS grows, or a route chunk disappears. Entry went from
  ~563 kB to ~223 kB gzip. Tests: route-chunk presence + budget script in CI.
- **Study coach strip (plan 101-G first cut).** Home shows up to two
  deterministic next-step cards in a fixed priority (first file, due review,
  exam practice, practise, AI provider), each with one deep-linked CTA and
  per-rule dismissal persisted locally. Clicks and dismissals feed the
  first-party counters; no AI call or new data source. Tests:
  `StudyCoachStrip.test.tsx`.
- **Activation counters (plan 101-F first cut).** Migration 0034 adds
  profile-scoped `activation_events` with a closed event vocabulary; Settings →
  General → Usage insights shows the recorded counts, exports JSON and clears
  them, with deployment-aware disclosure. Solve completion and
  moment→card are instrumented. No third-party telemetry or content capture. Tests:
  `test_activation.py`, `UsageInsightsCard.test.tsx`.
- **Spoken tutor replies + audio/voice polish (plan 94-E/C/F residuals).**
  Settings → General adds **Speak tutor replies aloud**; the newest completed
  assistant message auto-plays through the existing read-aloud engine, and
  starting dictation cancels speech for barge-in. The global player gains a
  sleep timer, Voice & audio gains **Test voice**, and transcript search jumps
  to the first match on Enter. Full voice quiz-me, offline audio downloads and
  device/voice pickers remain. Tests: read-aloud auto-play, MediaPlayer search.
- **Global audio player (plan 94-C first cut).** Audio materials now play
  through one app-shell provider: the recording keeps playing across route
  changes, a mini-player exposes title/progress/seek/speed/close, track and
  position persist across reloads, and Media Session metadata is set where
  supported. Video stays inline. Offline downloads and sleep timer remain.
  Tests: `AudioPlayerBar.test.tsx`, `MediaPlayer.test.tsx`.
- **Scheduled daily audio brief (plan 94-D first cut).** Settings → General
  stores an enabled flag, local time and 5/10/20-minute length. The scan
  scheduler creates one review-aware audio brief per profile per day for the
  newest non-scratch course, skips duplicates and reports honestly when there
  is no course. Home gains a Daily brief card that opens the rendered material
  or creates today’s brief. Notification delivery and the study-state
  fingerprint remain. Tests: `test_daily_brief.py`, `DailyBriefCard.test.tsx`.
- **Voice & audio settings (plan 94-F first cut).** Settings → General now
  shows the assigned speech-to-text and text-to-speech models, the device-voice
  fallback, browser speech-synthesis availability and microphone availability,
  with a direct link to AI task assignments. Device/voice pickers and the test
  diagnostic remain. Tests: `VoiceAudioCard.test.tsx`.
- **Artifact browser voice (plan 94-B first cut).** Audio brief specs now carry
  chapter titles and scripts. When no TTS model is assigned the artifact
  records `renderer=browser`, and the narration dialog plays the script and
  each chapter through `speechSynthesis`, with stop, a device-voice badge and
  an honest unsupported state. Provider audio caching/chapters and the global
  player remain. Tests: `NarrateDialog.test.tsx`, `test_artifacts.py`.
- **Lecture STT + text-only retention (plan 93-B/F first cut).** Finalized
  lectures now run one `lecture_transcribe` job: provider timestamped segments
  become `media_segments`, missing provider timestamps fall back to proportional
  sentence windows, and the derived extraction is re-indexed. No assigned STT
  model leaves the audio ready with an honest error. Text-only sessions carry a
  7-day audio expiry and are purged lazily once the transcript exists and no
  other reference needs the blob; the transcript survives and the player hides
  the expired audio. Migration 0032 widens the job CHECK and adds
  `audio_purged_at`. Tests: `test_lecture_transcribe.py`, purge in
  `test_lectures.py`.
- **Crash-resume and safe lecture containers (plan 93-A).** Recorded parts are
  written to the shared offline journal before upload, and a saved lecture
  draft is surfaced by a global **Unfinished lecture recording** banner and
  offers **Resume upload** after a relaunch: pending parts replay
  idempotently, then finalize. Finalize now validates the WebM/EBML, Ogg or
  MP4 box structure and refuses to publish an unplayable file, leaving a failed
  session with the parts intact. Tests: `test_container.py`, resume case in
  `LectureRecorderDialog.test.tsx`.
- **Lecture recording session (plan 93-A first cut).** Materials → New →
  **Record lecture** starts a consent-gated `MediaRecorder` session with
  pause/resume, ordered sha-checked chunk upload, idempotent sequence replay,
  gap checks, and a part/size quota. Stop concatenates the ordered parts into a
  normal audio material and queues ingest. `lecture_sessions`/`lecture_chunks`
  arrive in migration 0031. Crash-journal resume, container-box concat
  validation, text-only purge and live transcription remain. Tests:
  `test_lectures.py`, `LectureRecorderDialog.test.tsx`.
- **Study this lecture (plan 93-E first cut).** The media player opens the
  existing compose builder scoped to the lecture material with a
  timestamp-preserving instruction, so summaries and study guides use the
  normal compose pipeline. One-click summary/cards/quiz presets and coverage
  accounting remain.
- **Bulk moment cards (plan 93-D residual).** Moments can be selected with
  checkboxes and turned into a batch of basic cards in one action. Tests:
  `MediaPlayer.test.tsx`.
- **Speaker relabel and moment actions (plan 93-D residual).** Transcript edits
  now carry a speaker label; lecture moments can become a basic flashcard, be
  quoted into a course note, or be added to today’s plan through the existing
  APIs. Tests: `MediaPlayer.test.tsx`.
- **Transcript split/merge (plan 93-C residual).** The media player can split
  the active segment at the current timestamp and merge a segment with its
  next neighbour; both rebuild the derived extraction and re-index it. Tests:
  `test_media.py`, `MediaPlayer.test.tsx`.
- **Transcript editing + deep links (plan 93-C first cut).** Media transcript
  segments can be edited inline; an edit rebuilds a new `media_transcript`
  extraction from the ordered segments and enqueues postprocess for
  re-chunk/re-embed. Clicking a segment or opening `?t=` seeks the player, and
  an explicit rebuild endpoint is available. Merge/split UI and speaker
  relabel remain. Tests: `test_media.py`, `MediaPlayer.test.tsx`.
- **Review-aware narration (plan 94-A first cut).** The deterministic audio
  brief now opens with the due-card count and up to two weak concept×skill
  cells from recent answers before the material and next-step sections. Tests:
  `test_artifacts.py`.
- **Lecture moments (plan 93-D first cut).** The media player can mark the
  current timestamp with a one-line note and the active transcript quote.
  Moments are `time_range` document anchors (the same contract as text
  highlights), list below the player, seek back on click and are deletable.
  No schema change. Lecture recording, incremental STT, full transcript
  editing and card/quote actions remain. Tests: `MediaPlayer.test.tsx`.
- **Media player and transcript timeline (plan 90-C first cut).** Audio and
  video materials now open with a player and a timestamped transcript list:
  click a line to seek, search the transcript, follow the active segment and
  change speed. `media_segments` (migration 0030) stores ordered windows;
  segment create/patch/delete APIs are live, and the existing extraction seeds
  one full-duration segment when no timestamped transcript exists yet.
  Incremental timestamped STT, merge/split, extraction re-chunking and the
  global player remain. Tests: `test_media.py`, `MediaPlayer.test.tsx`.
- **Artifact registry + Narrate this topic (plan 90-D first cut).** A typed
  `artifacts` registry (migration 0029) records rendered outputs with status,
  spec version, output material and job/model/voice, and the new
  `artifact_render` job renders an `audio_brief`. A node Overview **Narrate
  this topic** builds a deterministic script from the node and its indexed
  material summaries, renders through the TTS gateway, and falls back to a
  browser-voice script material when no model is assigned. One live brief per
  node, regenerate in place, retry/delete; output lands as a normal material.
  Review-aware selection, chapters/player, daily brief and voice tutoring
  remain. Tests: `test_artifacts.py`, `NarrateDialog.test.tsx`.
- **Studio slide decks and handouts (plan 98-D/E first cut).** A new `/studio`
  surface (sidebar and palette) turns a course material with extracted text
  into a deterministic slide deck or handout: headings become sections,
  paragraphs become short bullets, and the typed spec prints through the normal
  print path at 16:9 or A4. The generated markdown is saved back to the course
  library as a normal material; deleting the artifact keeps that material.
  Migration 0028 adds `studio_artifacts`. Research briefs/sessions (98-A/B/C),
  rich layout editing, templates and bundle export remain. Tests:
  `test_studio.py`, `StudioPage.test.tsx`.
- **Problem Desk (plan 97-A/B/C/E/F first cut).** A new `/solve` surface
  (sidebar **Solve**, Home card, palette, mobile More) accepts typed MathLive,
  pasted or photographed math. A deterministic SymPy classifier picks
  simplify/evaluate/solve/differentiate/integrate/factor/expand; every displayed
  step is machine-checked (equivalence, derivative, antiderivative,
  substitution) and unverifiable results are withheld rather than narrated. A
  verified solve can generate three similar problems checked server-side or be
  kept as a scratchpad note; history is profile-scoped. Migration 0027 adds
  `solve_entries` with a typed result document. Handwriting, crop rectangles,
  graphing/exploration and limits/systems remain. Tests: `test_solve.py`,
  `SolvePage.test.tsx`.
- **Exam papers (plan 96-A/B/C/D/E first cut).** Practice → **Exam papers**
  assembles a multi-section paper from the course question bank with a live
  marks total, difficulty filters and a seeded, deterministic draw. Each
  question is copied into a paper activity snapshot, so later bank edits never
  change a paper already sat. Sit it through the existing attempts engine in
  exam mode (deadline, no hints, feedback deferred until submission), then read
  a marked report with per-section marks, grade bands and the topics that lost
  the most marks. Print paper/key through the existing print surface. Migration
  0026 adds `exam_papers`. Document-backed past papers, self-marking,
  predicted-grade calibration and the full palette/flag review screen remain.
  Tests: `test_exam_room.py`, `PapersPanel.test.tsx`, exam-deferred
  `QuizRunner` case.
- **Diagram-label questions (plan 95-A/B/C first cut).** A new
  `diagram_label` exercise kind: pick an image material, drag labelled regions
  on it, and save a question; the player shows the image with numbered hotspots
  and a shuffled label bank, graded deterministically by label→hotspot
  matching. Payload validation covers bounds, duplicate labels and label-bank
  completeness. Migration 0025 widens `exercises.kind`. Image occlusion,
  AI label proposals, Anki IO import and quiz-surface support remain.
  Tests: `test_diagram_label.py`, `DiagramLabelInput.test.tsx`.

### Changed
- **One secret store and one opaque credential core — family auth-kit 0.6.0
  (plan 60 Phase 2B).** `app/core/secrets.py` is now a thin adapter over
  `nx_auth.secrets`: the keyring service (`StudyAssistant`), sealed
  `secrets.json` shape, `enc::` values and `SA_DATA_KEY` sealing are
  unchanged, with keyring → sealed-file precedence and a round-trip probe.
  Capture device tokens mint and verify through `nx_auth.opaque` with the
  same `token_urlsafe(32)` plaintext and SHA-256 digest-only lookup. No
  schema or API change. Deltas: a stored empty secret now reads as `None`
  (was `""`), and deleting a secret fails closed when no writable backend
  can perform the revocation.
- **Command surfaces and the dictation gate use the family library (plan 59
  Phases 2–4).** `@neuronection/assistant-ui` 0.85.0 replaces the hand-rolled
  `?` shortcut sheet and Ctrl/Cmd+K palette shells: the shortcuts dialog is one
  library `Modal` composing `ShortcutList` and a `CommandList` feature map
  (every group/keycap, quick capture/import, `?`, Escape/backdrop close and
  focus return preserved), and the global palette is the library
  `CommandPalette` with the app's catalog, async `?`-prefixed content search,
  recents, course-tree search and actions kept app-side. The chat composer's
  missing speech-to-text state renders the library `DictationUnavailable`
  with the existing settings action. New `components/ui` shims:
  `command-list`, `command-palette`, `shortcut-list`; `dictation` now exports
  `DictationUnavailable`. Tests: `ShortcutsDialog.test.tsx`,
  `CommandPalette.test.tsx`, `StudyChatPanel.dictation.test.tsx`.

### Fixed
- **The e2e boot harness now runs migrations and boots in test mode.**
  `frontend/e2e/run_backend.py` applies the Alembic chain to its fresh
  datastore before `create_app` and pins `app_env=test` so the production boot
  guard does not reject the harness; the boot spec now matches the provider
  step by heading. `pnpm e2e` passes 12/12.
- **Library CSS no longer overrides app responsive utilities.** The prebuilt
  `@neuronection/assistant-ui/styles.css` is now imported into a dedicated
  `assistant-ui` cascade layer before app utilities, instead of as unlayered
  CSS. This fixes the desktop chrome: the sidebar is visible and the mobile
  bottom bar is hidden at ≥48rem, while the compact layout still uses the
  bottom bar. It also prevents the library's unlayered `.flex`/`.hidden` rules
  from beating every app `md:*` variant.
- **The mobile More sheet renders above the app chrome.** The More menu is now
  portaled to the document, raised above the bottom bar and overlays, and
  closes on outside pointerdown, Escape, or a route change; it also exposes
  `aria-haspopup`/`aria-controls`. This prevents the menu from being clipped or
  hidden behind other fixed surfaces on small screens.
- **Onboarding welcome title and language flags.** The wizard's welcome step
  now resolves `onboarding.welcomeTitle` in every shipped locale, and the
  language picker (used by onboarding and Settings) shows the shared language
  catalog's country flag beside each endonym. The i18n audit now covers the
  `onboarding` surface.
- **Offline audio and activation state are scoped per user/profile (plan 59
  1.1/1.2).** The audio cache is now `sa-audio-offline-v1:<scope>` and the
  player state is stored per scope, where the scope is
  `u:<user-id>:p:<profile-id>`; nothing is read before the scope resolves.
  Downloads use the authenticated `apiFetch` path and `cache.put` instead of
  `cache.add`, logout/401/account deletion purge the scope, and a profile
  switch stops playback but keeps the previous profile's explicit downloads.
  The pre-scope global cache and unscoped `sa-audio-state` key are deleted on
  first boot; Settings → Developer gains cache diagnostics/clear. Activation
  props are now a closed `ActivationStep`/`ActivationSurface` vocabulary with
  a bounded numeric `value` (unknown/extra props and out-of-vocabulary values
  are 422), the first-event marker is keyed by `(user, profile)`, and clearing
  the counters also removes those client markers. The Usage insights disclosure is
  deployment-aware instead of claiming everything stays on the device.
  Tests: `test_activation.py`, `audio-offline.test.ts`,
  `audio-player.test.tsx`, `AudioPlayerBar.test.tsx`,
  `activation-events.test.ts`, `activation-vocab.test.ts`,
  `UsageInsightsCard.test.tsx`, `AccountCard.test.tsx`.
- **Secret reads are lazy about key material again (plan 60 Phase 2B).** A
  missing or pre-adoption plaintext secret resolves without constructing the
  at-rest cipher, so a host with no (or unwritable) key material keeps
  answering those reads instead of failing on the lookup; an `enc::` value on
  such a host fails closed with `None`, and sealing still refuses without a
  resolvable key ring. The empty-ref semantics from the adoption stand:
  `set_secret("")` / `delete_secret("")` raise `ValueError`. No schema, API or
  stored-format change. Tests: `test_secrets.py`.

## [v0.13.0-rc.6] - 2026-11-10

### Fixed
- **One startup flow for the datastore break.** The kept-data notice is now the first screen and
  the first-run wizard is suppressed until it is acknowledged, so an upgrade no longer opens two
  modals at once (rc.5 had the quarantine and notice, but not the sequencing). No backend or data
  change.

## [v0.13.0-rc.5] - 2026-11-09

### 0.13 highlights

_rc.5 supersedes rc.4: a 0.12.x datastore is moved aside automatically on first launch (nothing deleted) with a one-time notice; PostgreSQL volumes are preflighted. No other product change._
- **Token-aware retrieval** — offline tokenizer with real token accounting; a v2 token-window
  chunker that builds beside the v1 space, backfills, passes coverage/quality and cuts over;
  bounded live indexing progress, retrieval operations/alerts and a read-only observation surface.
- **Cloud calendars** — Google, Microsoft 365, Nextcloud, iCloud, Fastmail, CalDAV and ICS; exam,
  deadline and milestone dates project as all-day events; two-way sync is opt-in; credentials stay
  in the OS keyring.
- **Connected sources & academic ingest** — arXiv/OpenAlex/Crossref discovery, `.bib`/`.ris`,
  `.ics`, markdown vaults, WebDAV/Drive/Dropbox/OneDrive/Zotero/Anki; imports land as suggestions.
- **Extension host** — validated manifests, bundled connectors and MCP instances; family contracts
  and extension data now ship in the frozen bundle and the Docker image.
- **PostgreSQL 16 web mode**, profiles/identity, and the 0.13 hardening round (restore safety, typed
  schema-break refusal, packaging completeness, CSP/OAuth callback, calendar sync safety).

### Known limitations (rc)
- CalDAV recurring events can appear as a single item at the series start; in-window expansion is a
  follow-up in the 0.13 line.
- Google/Microsoft calendar OAuth needs `SA_*_CLIENT_ID`; CalDAV/ICS work out of the box.
- The update badge activates once the website version API is deployed.
- Windows is built and smoke-tested by this tag's CI (first verification of this bundle).

### Breaking changes — 0.13 schema baseline (clean install required)
- **The datastore schema was rebuilt.** The Alembic chain was squashed into
  `0001_baseline` (ADR-196) and the content identity moved to UUIDs; there is
  **no migration path** from 0.12.x databases. A 0.12.x datastore is refused at
  boot with an actionable message (and `STARTUP-ERROR.txt` in the data
  directory) instead of an opaque Alembic error. To keep working, move the old
  data directory aside (or run `python -m studyassistant reset --all`) and start
  fresh.
- **Backups from 0.12.x are refused.** The archive manifest now records the
  schema revision; a restore whose schema does not match this release is
  rejected **before** anything is swapped (HTTP 422 on the API). Backups made
  by 0.13 restore normally.
- **No legacy shims.** The `ca-*` compatibility vocabulary, the hand-rolled
  `app/core/oauth.py` flow, the update banner and the pre-0.13 backup reader
  are gone; nothing reads the old formats.

### Added (bounded live indexing progress + read-only parity — plan 52 T5c)
- **Live detail**: migration `0019_job_progress_detail` adds nullable
  `jobs.progress_detail`. The Study retrieval pipeline folds one bounded
  counters document into its existing per-document progress UPDATE — phase,
  exact scan-start `total_documents`, cumulative/estimated chunks,
  embedded/skipped/failed documents and chunks, local-tokenizer tokens,
  embed calls and the exactness flag — with no second write, no source ids
  and no document text. The v1 character path labels chunks exact; the v2
  window path labels them estimated.
- **Continuation + pruning**: a limited pass exposes its counters as
  `progress_carry`; a retry seeds the new run from the stored detail so the
  bar resumes instead of resetting. The detail is pruned when the final
  `result` commits — the result stays authoritative.
- **Read surface**: `GET /admin/retrieval/runs` (and the composed overview)
  carries the optional `progress_detail` additively; a malformed row reads
  as absent. Run/space DTOs keep `token_aware` and now expose the persisted
  tokenizer `source` beside kind/identifier/exactness.
- **UI**: Settings → Indexing and the read-only observation run drawer render
  an accessible `role=progressbar` bar with processed/total documents,
  pending and estimated chunks, embedded/skipped/failed, approximate-token
  and embed-call counters, and a token-aware/legacy + exact/approximate
  label. Compact rows keep mobile width; the observation surface adds no
  action controls.
- **Not in this slice**: rollout docs/publication (T5d) and any token-aware
  write/cutover change.

### Added (token-aware writes + v2 cutover — plan 52 T5b2)
- **Profile + identity**: `services/retrieval/chunk_profile.py` resolves one
  effective tokenizer/chunk pair (explicit admin pair → curated OpenAI exact
  `cl100k_base` → labelled heuristic fallback) with separate per-item
  (`max_input_tokens`) and per-request (`batch_max_items`/`batch_max_tokens`)
  limits. `lifecycle.build_space` persists the pair, forces
  `chunker_version='2'`, validates the budget and computes `space_key_v2`;
  v1 builds stay on the character path. The ORM `space_key` default computes
  v2 from a complete pair and still refuses a half pair; `ContentSpace`
  reconstructs the pair and stored key.
- **Token chunking**: `pipelines/chunking.py` adds `chunk_tokens` using
  `encode_with_offsets` — exact char/token offsets, token overlap, a hard
  `max_chars` ceiling, no truncation and a typed `input_too_long` failure.
  `chunk_markdown` is unchanged. Ingest, trash restore, material edits and
  course import use the active v2 profile through `chunk_texts_for_space`;
  legacy chunks are preserved.
- **Writes + cutover**: `StudyVectorStore.store_specs` writes one
  `vector_records` row per token window with the vendored `IndexRecord` token
  columns; reindex skips unchanged windows, batches by items and token sum,
  and reports `input_too_long` once per chunk. Migration
  `0018_vector_record_token_windows` widens record uniqueness to
  `(space, chunk, window)`, so a source chunk can own several windows while
  v1 rows keep one/NULL. A v2 space builds beside v1, backfills, passes the
  coverage/quality gate, activates with the retired stored key and retains
  v1; space/run read DTOs expose `token_aware`, tokenizer/exactness and chunk
  config.
- **Not in this slice**: bounded `progress_detail`, Tools/Audit progress UI
  and rollout docs. Those are T5c; see
  [dev/retrieval-ops.md](docs/dev/retrieval-ops.md).

### Added (stored space key + tokenizer/chunk schema — plan 52 T5b1)
- **Stored space identity**: migration `0016_vector_space_stored_key` adds
  non-null `vector_spaces.space_key` and stamps every existing row once with
  the frozen v1 pre-image before enforcing NOT NULL. `ContentSpace`,
  `space_key_for`, build idempotency, activation (`previous_space_key`),
  status/DTO reads and `load_store` use the stored value instead of
  recomputing it; new spaces persist the v1 key. (T5b2 later replaced the
  explicit-key refusal with the v2 default.)
- **Schema for T5b2**: migration `0017_vector_token_schema` adds nullable
  tokenizer/chunk identity columns to `vector_spaces` and nullable
  `token_count`/`token_start`/`token_end` to `vector_records`, with
  all-or-none, kind/provenance/bounds, `chunker_version='2'` and
  ordered/consistent-token CHECKs. Downgrade drops the token columns but keeps
  `space_key`.
- **Not in this slice**: token-aware chunking/writes, v2 builds or cutover,
  progress detail or UI. Character chunking, token counts and write behavior
  are unchanged; the T5b2 handoff is in
  [dev/retrieval-ops.md](docs/dev/retrieval-ops.md).

### Added (offline tokenizer + real token accounting — plan 52 T5a)
- **Family contracts synced byte-identically**: `tokenizer_contract.py` +
  fixtures, the token-aware `vector_contract.py` (stored space key, v2 space
  identity, `IndexRecord` token fields) and the token-aware
  `retrieval_ops.py` DTOs (space/run tokenizer + chunk, bounded run progress
  detail). Vendored copies stay canonical; the dev ledgers record study.
- **Real offline tokenizer**: `app/ai/tokenizers/` bundles
  `cl100k_base.tiktoken.gz` with gzip + BPE SHA-256 verification and builds
  the encoding directly — no `tiktoken.get_encoding`, no `tiktoken_ext`, no
  network, no `sentencepiece`/HF download. Bounded LRU, `count`/`encode`/
  `decode`/`encode_with_offsets`, and a visibly labelled heuristic fallback.
- **One accounting seam**: `app/ai/tokenizers/accounting.py` resolves the
  effective tokenizer for the assigned embedding model (curated OpenAI
  embeddings → exact `cl100k_base`; anything else → `exact=False` heuristic,
  no model-name guessing). Ingest, trash restore, material edit/course
  import, chat context/trace, tutor/quiz help, note actions and the gateway
  ledger now use real local counts; the `len//4` estimate is gone. The
  exact/approximate label travels on `TokenCount` and the interaction
  metadata (same `ai_interactions` row).
- **Not in this slice**: token-aware chunk writes/offsets, `space_key` v2
  stamping, cutover, progress emission or UI (T5b/T5c). `Chunk.token_count`
  counts the existing character chunks only.

### Fixed (calendar identity + delta safety — ADR-0052 / E9 / M4)
- **A calendar link's `uid` is now the LOCAL uid**, with the provider's handle
  in `remote_id`. Providers may mint their own (Graph's `iCalUId` is
  server-generated), and uid-matching split one event into `unlink` +
  `create-remote` — a duplicate on every sync.
- **Orphan repair**: an unlinked plan item with a matching unlinked remote
  event is attached (`LINK_EXISTING`), never duplicated. This closes the
  crash window even on providers with no idempotency key.
- **Delta cursors are a fast path, never the remote view**: when the provider
  reports no changes the reconcile is skipped; any change falls through to the
  full window. The bind form is rendered entirely from the catalog's
  `setupFields`, so a new provider needs no UI change.
### Added (retrieval observation inside Tools → Indexing — plan 51 Q3c3b)
- **Admin-only read-only observation card.** The existing Tools → Indexing
  section now hosts a second, read-only surface without adding a settings
  domain or audit route. It is URL-synced on the same `/settings` route:
  `?tab=tools&section=indexing&obs=overview|spaces|runs|quality|query-health|failures|usage`,
  with the pinned `&detail=<id>` opening run (`<run_id>`), space
  (`space:<space_id>`) and quality (`quality:<space_id>`) drawers. Alert
  manage URLs that already carry a run id keep working.
- **Composed from the shipped read DTOs only** (`overview`, `spaces`, `runs`,
  `quality`, `query-health`, `usage`); the card imports no action client and
  renders no reindex/cutover/maintenance/compare/cancel/retry control. It
  links to the management controls above, and a test pins the read-only
  source guard. Overview shows the active space/backend/model/dim, honest
  coverage (never a fabricated percentage), p50/p95, degraded and zero-result
  rates and embed calls/tokens; runs include result counters and a drawer
  with stage/progress and bounded failed ids; quality includes set version,
  recall/precision vs floor, gate state and bad-match ids/scores only;
  query health shows latency, candidates, degraded reasons, per-view hits and
  an honest "not sampled" ANN state; usage shows calls/tokens by day, space
  and kind with `tokens_available=false` and the no-budget gap intact.
- **Failures are structured, never raw.** There is no `/failures` endpoint and
  no failures table: the card groups failed runs, space failed-document
  counts, a below-floor quality gate and query-health degraded reasons into
  reason-code groups with ids/counts. `run.error`, space `last_error` and all
  document/query text are never rendered.
- **No backend change.** Tests: `RetrievalObservationPanel.test.tsx`
  (cold/degraded, URL section switching, run/space/quality drawers,
  structured failures, usage gaps, admin-only and read-only/no-raw-text
  guards), updated `IndexingSection.test.tsx`, translations for en/de/el.
  Q5 (family closeout) remains.

### Added (retrieval alerts, generation tagging & canonical adoption — plan 51 Q3c3a)
- **Ten retrieval alerts through the existing notification funnel.**
  Migration `0015_retrieval_alerts` adds the boot-seeded
  `notification_kinds` registry and deduped `notifications` event rows.
  `services/platform/notifications.py` is the only emit seam and
  `services/retrieval/alerts.py` evaluates coverage_low, reindex_failed,
  reindex_stalled, quality_gate (fed by the real Q3c2b2 compare), query_slo,
  degraded_rate, provider_unassigned, index_missing and space_drop_pending
  on the existing `ScanScheduler` periodic seam — never the request path.
  Dedup keys are released when a condition clears so recovery is honest;
  admin fanout is bounded, daily caps come from the family `ALERT_DEFAULTS`,
  payloads pass `assert_no_raw_text`, and every manage URL points at the
  shipped Tools → Indexing (run detail included) or the AI task assignment.
  `retrieval.budget_exhausted` reports `unavailable` rather than inventing a
  token budget study does not have. The latency histogram writer now counts
  overflow only above the largest finite bound (it double-counted every sample
  before, so p95 was always 10000 ms and query_slo could never recover). `GET /notifications` carries the active
  recipient-scoped alerts and the bell renders them.
- **Generation-ledger tagging and an honest usage read.** Study's ledger is
  `ai_interactions`; migration `0015` adds `metadata` + `metadata_schema_version`
  and the caller supplies `space_id`/`kind`/`view`/`chunk_index` through
  `GatewayEmbedder.embed`/`record_usage` (indexing, reindex, live search and
  golden-query compares). `GET /admin/retrieval/usage` exposes calls/tokens by
  day/space/kind with `reindex_calls`; it never selects `prompt`, reports
  `errors_available=false` (the ledger has no status column) and `budget=null`
  (no token budget), and marks untagged rows `unattributed` instead of guessing.
- **Canonical settings-map/ledger adoption.** The `/dev` canonical settings map
  marks career and study `tools.retrieval` aligned, study hosts it in the
  `indexing` section, and the study vendored copy + `settingsMap.test.ts` match
  it. `dev-vector-p0/contracts/retrieval-ops.sync.json` records study's bytes
  with the branch note; the parity runner now reports only
  `adoption:study-main` until `/study-assistant` main carries the same bytes.
- Tests: `test_retrieval_alerts.py` (one per kind, dedup/recovery, fanout,
  caps, manage URLs, no raw text, empty/cold/quality fail),
  `test_generation_tags.py`, the 0015 SQLite/PG migration round-trips,
  `test_retrieval_ops_family_parity.py`, `NotificationBell.test.tsx` and
  `settingsMap.test.ts`. Audit → Retrieval (Q3c3b) and the Q5 closeout remain.

### Added (golden-query quality compare & gate — plan 51 Q3c2b2)
- **Versioned admin golden-query sets.** `services/retrieval/quality.py`
  loads `backend/app/data/retrieval/golden_queries.json` (empty by default —
  no fabricated pass), selects the newest set by space id then name,
  normalizes UUID-shaped expected ids, and validates every set through the
  family contract. Query text stays fixture-only; every read DTO carries
  query ids, document ids, scores and miss lists.
- **Bounded real-backend compare.** `POST /admin/retrieval/quality/compare`
  embeds each golden query once, searches the active and candidate space
  through `StudyVectorStore.search_scored`, maps chunk hits to material
  document ids, and returns the contract `QualityCompareDTO` plus a
  deterministic (distance, chunk id) bad-match detail: chunk/document ids,
  view, distance and score, never document or query text. The compare is
  persisted on the `VECTOR_CUTOVER` job result with same-key idempotent
  replay; `GET /admin/retrieval/quality` reports the newest evidence as
  `no_golden_set` / `not_sampled` / `sampled` / `stale_compare`.
- **The quality activation/cutover gate is real.** Activation verifies
  physical health, coverage (`0.995`) and the golden-query compare;
  `VECTOR_CUTOVER` backfills, enforces coverage, runs the compare and refuses
  below the floor. Refusals are structured (`quality_gate_failed`) and persist
  `quality`, `quality_state`, `bad_matches` and `activation_gate` on the failed
  job. The old `quality="not_sampled"` success path is gone: only a missing or
  blocked setup reports `not_sampled`/`blocked`, and never a pass. Repeating
  an activation/cutover on an already-active space is an explicit
  `already_active` no-op (no re-compare, no quality pass claimed).
- **Tools → Indexing quality surface.** The card lists each space's quality
  gate state, shows the set version/k, recall/precision vs floor, pass/fail,
  the gate and a bad-match drawer; it can run the compare against the active
  space, and activation/cutover refusals render the gate reasons. No Audit →
  Retrieval tab yet (Q3c3).
- **Cross-repo family parity runner.** `services/retrieval/parity.py` +
  `tests/test_retrieval_ops_family_parity.py` compare the study/career
  contract and fixture bytes, run every shared quality case through the
  vendored scorer, pin the DTO shapes and record the sha plus sync-gate
  status. It deliberately does not claim the family `--strict` gate while the
  canonical ledger and settings map still record study as pending.
- Tests: `test_retrieval_quality.py` (SQLite), the PG quality/gate twins in
  `test_vector_backends_postgres.py`, the updated lifecycle/action/parity
  walls, and the frontend card/panel tests. Alerts, generation tagging and
  the canonical sync landed in plan 51 Q3c3a.

### Added (vector backend & provisioning — plan 51 Q3c2a)
- **The content space now runs on a real family vector backend.**
  `storage/vector_backends.py` implements the vendored `VectorBackend`
  protocol: pgvector + HNSW cosine with the scope joined before the ANN
  scan (and an exact scan at or below the scoped threshold), sqlite-vec
  `vec0` keyed by the `vector_records.rowid` map with bounded over-fetch /
  post-filter, and an exact `LinearBackend` fallback that publishes
  `ann=False`.
- **Physical provisioning is one seam, off the request path.**
  `storage/vector_provisioning.py` creates `vec_<8hex>` (pgvector
  `vector(dim)` + HNSW, or sqlite-vec `float[dim]`) and writes
  `vector_spaces.index_table` in the same transaction as the DDL.
  `storage/vector_schema.py` owns the `vec_[0-9a-f]{8}` name guard and the
  Alembic autogenerate exemption.
- **Migration `0013_vector_space_provisioning` moves the legacy vectors.**
  It provisions `vec_dfbcce9b`, copies `chunk_vecs` through
  `chunk_vec_ids` into the metadata records, verifies the copied row count
  and only then switches `index_table`. `chunk_vecs` is left intact and
  stays the dual-written compatibility fallback; downgrade drops the new
  table and resets the pointer.
- **Search routes through the backend without changing fusion.**
  `StudyVectorStore.search()` now scopes the vector query by
  `course_id`/`material_ids`/`profile_id` before the ANN scan, falls back
  to the legacy search when the backend is unavailable, and returns the
  unchanged `(chunk id, distance)` shape; `retrieve_chunks_hybrid` and the
  FTS/RRF weights are untouched.
- **Status tells the truth.** `health()` / `space_status()` report the
  active table, HNSW/vec0 presence, row count and partial/missing states
  through the overview notes and `last_error`; `records` is the active
  backend count, not the legacy one.
- Tests: `test_vector_backends.py` (SQLite parity, scope, rowid map,
  linear fallback, partial/missing health), `test_vector_backends_postgres.py`
  (pgvector HNSW, exact vs ANN, scope, legacy fallback),
  `test_search_vector_backend.py` (FTS/RRF regression and fallback), and
  migrated SQLite/PostgreSQL 0013 round-trips.

### Added (vector space lifecycle & cutover — plan 51 Q3c2b1)
- **Real embedding-space lifecycle.** `services/retrieval/lifecycle.py`
  builds a `building` space with real model/dim/prefix metadata, provisions
  its `vec_<8hex>` backend, backfills it through the ordinary reindex writer,
  activates it only when physical health and coverage pass, retires every
  previous active row in one transaction, and supports typed retire/drop with
  the 7-day grace period. The active space can never be dropped.
- **Real cutover.** `VECTOR_CUTOVER` backfills the candidate, refuses a
  non-`pass` coverage gate, activates it, retires the previous space and
  reports `quality="not_sampled"` — no fake quality pass. `chunk_vecs` stays
  as the compatibility store until the retired legacy space is explicitly
  dropped.
- **Two spaces coexist.** Migration `0014_vector_record_chunk_id` adds
  `vector_records.chunk_id`; records use a deterministic per-space id and the
  sqlite-vec rowid rule, while search hydrates back to the chunk id. Rollups,
  coverage snapshots, run DTOs and query health follow the active real space
  id.
- **Management surface.** `POST /admin/retrieval/spaces`,
  `/spaces/{id}/{activate,retire,drop}` and `/cutover` are wired to the
  existing idempotency/lock/audit seam; Tools → Indexing lists spaces and
  exposes build/cutover/retire/drop with typed confirmations and an explicit
  quality-not-sampled note. `quality/compare` remains an honest Q3c2b2
  refusal.
- Tests: `test_vector_space_lifecycle.py` (build/backfill/activate/retire/
  drop, coverage refusal, one-active pointer, cutover, legacy compatibility,
  active-space identity), updated service/action/read/migration and frontend
  card tests.

### Fixed (PostgreSQL migration baseline — plan 51 Q3c1)
- **The PostgreSQL migration chain now runs end to end** from
  `0001_baseline` to `0012_vector_spaces` (PostgreSQL 16 + pgvector).
  `tests/test_migrations_postgres.py` executes against the configured test
  server instead of being skipped, and a fresh upgrade no longer fails at
  `CREATE TABLE courses`.
- Six boolean column defaults (`0`/`1`) became dialect-portable
  `sa.false()`/`sa.true()`: `courses.hidden`,
  `material_sources.mirror_subdirs`, `chat_sessions.quizme`,
  `chat_quiz_pendings.awaiting_answer`, `materials.starred` and
  `calendar_links.enabled`. The baseline decision-slot seed also casts its
  bind parameter (PostgreSQL rejected the reused parameter as
  `text` vs `character varying`).
- Revisions 0002–0011 no longer force a full table copy on PostgreSQL
  (`batch_alter_table(recreate="always")` broke dependent foreign keys when
  it dropped the primary key). SQLite still copies; PostgreSQL alters in
  place. Final schema and existing data are unchanged.
- The PG suite now seeds a real legacy store and asserts the 0012
  `content`/`legacy-chunk-vecs` space, document/record backfill shape,
  rowid parity, content hashes, no fabricated coverage snapshot, model/dim
  agreement with `vec_meta`, the Q3b partial indexes, and a
  downgrade/upgrade that leaves `chunk_vecs` intact.
- **PostgreSQL lexical search works again** (exposed by the now-runnable
  chain): the FTS/trigram chunk and material joins compared a UUID
  `materials.id` with the hex-keyed `material_fts*.material_id`, and the
  swallowed operator error returned no hits. Both twins now compare the
  hex form; SQLite behaviour is unchanged. Covered by
  `test_search_postgres.py` and `test_search_parity.py`.

### Added (vector storage foundation — plan 50 P3a)
- **The family vector contract is vendored byte-identically**
  (`storage/vector_contract.py` + its fixture table) with the canonical
  sha256 recorded in `docs/dev/retrieval-ops.md`; `test_vector_contract.py`
  runs every fixture group and the dev-checkout identity check.
- **Migration `0012_vector_spaces`** adds the portable metadata layer —
  `vector_spaces`, `vector_documents`, `vector_records` — and backfills the
  one `content` space (`legacy-chunk-vecs`) from `vec_meta`, with documents
  (materials) and records (chunk `body` + content hash + rowid reverse map)
  from `chunk_vec_ids`. `chunk_vecs` is untouched; no coverage snapshot is
  written.
- **`storage/vector_store.py::StudyVectorStore`** is now the read/write seam:
  search, embed writes, purge and the retrieval handlers use it. A
  model/dimension change raises `VectorSpaceChangeRequired` instead of
  silently dropping `chunk_vecs`; the old vectors remain readable until
  plan 51 Q3c's explicit new-space/cutover.
- **Honest state stays honest:** a cold store has no space row and no
  coverage number; `backfill_metadata()` fills content hashes idempotently
  for rows the SQL backfill mapped without them. The physical backend is
  still the legacy `chunk_vecs` store — P3a exposes the port, it does not
  claim the lifecycle yet.

### Added (retrieval operations — plan 51 Q3b)
- **Admin action API over the one legacy space.**
  `POST /api/v1/admin/retrieval/{reindex,maintenance,runs/{id}/cancel,
  runs/{id}/retry}` enqueues the existing `VECTOR_*` handlers; long work
  never runs in the request. Lifecycle verbs (build/activate/retire/drop,
  cutover, quality compare) answer with a structured `unsupported` 409
  instead of faking a space.
- **Idempotency and a database-level single-run lock** (migration
  `0011_retrieval_run_actions`): `jobs.idempotency_key` replays the
  original row inside the contract's 24 h window and 409s on a different
  payload; `jobs.lock_key` is a partial unique index over queued/running
  vector runs. `jobs.heartbeat_at` is written at worker progress
  checkpoints and a bounded reaper fails stale running rows (15 min) so a
  crash cannot block the space until restart.
- **Actions are audited in the existing `audit_events` table** (no second
  ledger): `vector.reindex.started`, `vector.reindex.cancelled`,
  `vector.reindex.retried`, `vector.maintenance.started`,
  `vector.run.stalled` and `vector.gate.failed` (full reconcile gate) —
  ids-only resources, never document/query/prompt text.
- **Tools → Indexing is now a real control surface** for admins: reindex
  (verify or force), recent runs with queued≠finished status, cancel,
  retry, orphan-sweep/vacuum/index-rebuild/retry-failed maintenance, an
  orphan-sweep dry run, and structured refusal messages. The legacy-space
  warning stays explicit. `tools.retrieval` is declared `aligned` in the
  study settings map (dev canonical sync is a follow-up handoff).
- **Read-DTO vocabulary parity test** pins study's run status, cold and
  degraded tokens to the shared career/study fixture table.
- **Deliberately not shipped (Q3c):** the real vector-space lifecycle and
  cutover target, golden-query quality gates/compare, the full family
  parity runner, alerts, and `ai_generations`-style metadata tagging.

### Added (retrieval operations — plan 51 Q3a)
- **The family retrieval-operations contract is vendored** (byte-identical
  to `dev-vector-p0`, sha-gated by the fixture wall) with the exact
  `VECTOR_REINDEX` / `VECTOR_MAINTENANCE` / `VECTOR_CUTOVER` job names.
  Study's closed `JobType` vocabulary and `jobs.type` CHECK gain the three
  slots; `jobs.result` carries the bounded
  `scanned/embedded/skipped/failed/failed_ids/truncated/gate` contract.
- **Bounded handlers over the existing legacy `chunk_vecs` store** — a
  resumable-free, limit/batch-capped reconcile that verifies or re-embeds
  chunks and publishes coverage only after a full pass; maintenance for
  orphan sweep, vacuum, index rebuild and scoped retry; a cutover handler
  that refuses honestly because study has no space lifecycle yet (Q3b).
- **Two operational aggregates** (`retrieval_query_rollups`,
  `retrieval_coverage_snapshots`, migration `0010_retrieval_ops`) with
  30/90-day TTLs. Query health (latency, zero-result, candidates, degraded
  reason) is buffered off the search hot path and flushed in 5-minute
  buckets; no query text is recorded. Rollups are aggregates, not audit
  history.
- **Admin read surface** `GET /api/v1/admin/retrieval/{overview,spaces,
  coverage,runs,query-health}` composed from the legacy store, jobs and the
  aggregates; cold/empty/degraded states stay truthful. Settings → Tools →
  Indexing gains a read-only status card for admins.
- **At Q3a this was deliberately not shipped:** the management/action UI,
  space lifecycle, quality gate, idempotency/single-active-run lock,
  `ai_generations`-style metadata tagging, and `tools.retrieval` alignment.
  Q3b (above) shipped the action API, lock, audit and Tools controls; the
  lifecycle, quality gate and full parity runner remain Q3c.

### Added (cloud calendars — ADR-0052 / plan 52)
- **A course can bind its own cloud calendar.** Providers come from the
  family catalog (Google, Microsoft 365, Nextcloud, iCloud, Fastmail, generic
  CalDAV, read-only ICS); exam, deadline and milestone plan items project as
  all-day events, and two-way sync is opt-in with an explicit study-event
  acceptance filter. Credentials live only in the OS keyring
  (`calendar:<link-id>:…`); the database stores a pointer, never a token.
- New `GET/POST/PATCH/DELETE /api/v1/calendar/links`, the provider catalog,
  one-shot secret write, OAuth start/complete, and test/sync verbs; migration
  `0009_calendar_links` adds the binding + identity-map tables and the
  `exam`/`deadline` plan kinds.
- Settings → Tools → Connectors → **Cloud calendars**: bind, status, test,
  sync and disconnect. The planner's add form offers the two new kinds.
- **The bind form is data-driven (plan 52 §12 Rev 4).** Fields — including
  the sign-in method (app password vs access token) — are derived from the
  catalog row's protocol, auth kinds and base-URL rule (`setup_fields` on the
  provider catalog response); adding a provider that speaks an existing
  protocol needs no frontend change, and the card holds no provider branches.
- **Calendar discovery (§9 M1).** `POST /api/v1/calendar/links/discover`
  lists an account's calendars (CalDAV PROPFIND, Google `calendarList`, Graph
  `me/calendars`) — capped at 50 rows, credentials held only for the one
  request, URLs sanitized to scheme+host+path. The bind form picks a calendar
  instead of pasting collection URLs; bound links offer **Choose calendar**
  (this is how Microsoft links select a calendar after OAuth).
- **OAuth honesty (§10 E12).** The bind flow's `state` is bound to the
  profile and single-use: the pending slot is consumed on success, expiry,
  profile mismatch or state mismatch, so a replayed or cross-profile
  completion is refused. The hand-rolled `app/core/oauth.py` flow is kept for
  now behind a marked seam in `calendar_sync.py`; migration to the family
  `nx_auth.oauth` module (PKCE S256, session-bound state) is documented in
  `docs/dev/cloud-calendars.md` and lands as a drop-in when that module
  ships.
- **Host contract pins** (`tests/test_calendar_sync.py`): the
  `local_hash`/`remote_hash` two-pin link schema (E3), the `skip` conflict
  default (C2/E4), window-aware reconcile — out-of-window links are skipped,
  never unlinked (E5) — and private-ICS-URL custody: the full URL goes to the
  keyring, the row keeps only scheme+host+path (C4).

### Changed (update checks — family version API, plan 48 W6)
- **`GET /api/v1/instance/update-check` now runs on the synced family
  version-check contract** (`backend/app/services/platform/version_check.py`,
  canonical in `the family contract canonical/`): the ad-hoc GitHub-Releases poll and its
  crude version tuples are replaced by the neuronection.com version API
  (ADR-0048) with real semver ordering, the stable-channel law (prereleases
  are never offered to stable clients), document validation before use and
  the skip-on-failure rule. Response shape is unchanged — the OpenAPI type
  is untouched. The plan-87 F banner is replaced by a discreet update badge
  in the sidebar footer (dot + popover with release links, self-clearing);
  accepted by the shared cross-language fixture wall
  (`backend/tests/fixtures/version_check.fixtures.json`).

### Changed (provider settings — family adoption)
- **Web search providers render through the family `web-search-providers`
  modules** (assistant-ui ^0.74.0), in the AI-providers pattern: configured
  providers are cards with all management actions in the `⋯` menu (enable,
  reorder, test, edit, delete), adding a provider is a two-step wizard
  (provider tiles → settings form) in a modal with the connection name
  auto-seeded from the provider label (numbered when taken), and the form
  keeps the main page minimal — the API key (or the required instance URL)
  plus the get-key link, with the name, endpoint overrides and the
  timeout/result-count tuning under **Advanced**. Endpoint overrides persist
  only when they deviate from the catalog default; editing keeps the stored
  key unless a new one is typed, and a **Clear stored key** action removes
  it. The search-provider API now accepts `timeout_ms` (500–30000, the
  catalog limit) alongside `max_results`.

### Added (connected sources — plan 86 / ADR-214–216)
- **One adapter family for source providers.** WebDAV/Nextcloud, Google
  Drive, Dropbox, OneDrive, a local Zotero collection and local Anki decks
  join RSS/YouTube/site search behind one reconciliation seam. Provider
  identity is catalog data (`providers.json`) validated at registration, so a
  new provider of an existing kind is a catalog row plus an adapter class —
  no migration (ADR-214).
- **OAuth2 loopback accounts.** Google Drive, Dropbox and OneDrive connect
  through an authorization-code + PKCE flow with a one-shot `127.0.0.1`
  listener; access/refresh tokens and token-provider passwords are sealed in
  the OS keyring, refresh stays inside the adapter layer, and disconnecting
  wipes the slots (ADR-215; supersedes plan 73's external-MCP-only OAuth
  ruling for loopback-capable providers).
- **WebDAV backup destination.** A WebDAV source (and a Dropbox connection)
  can hold `sa-backup/v1` archives: upload, list, download and restore
  round-trip from the source row. Google Drive and OneDrive stay read-only and
  request no write scopes.
- **Zotero and Anki bridges.** Zotero items arrive as citation-complete
  suggestions (DOI/authors/year/container) with attachment import; Anki
  reviews union-merge into `external_review_events` and deterministically
  recompute mapped cards' FSRS state (ADR-216).
- **RSS media enclosures.** Allowlisted audio/video enclosures become
  audio/video suggestions with a size cap; accepting one downloads it and
  feeds the existing transcribe job.

- **Discover integrates connected sources.** Saved suggestion rows from
  adapter-backed providers gain an **Import & parse** action that fetches
  through the source adapter (remote files never need to be publicly
  reachable), and a vanished remote file is marked missing on the next scan.

### Added (academic ingest — plan 85 / ADR-211–213)
- **Scholarly discovery providers.** arXiv (Atom), OpenAlex and Crossref join
  the Discover dialog beside web/YouTube/site presets — key-free, behind the
  polite perimeter, with `paper | dataset | reference` kinds and DOI metadata
  carried into saved suggestions (ADR-211).
- **Citations as schema.** Materials gain nullable citation columns
  (title/authors/year/DOI/container/kind); a `.bib`/`.ris` upload imports
  entries as link materials with DOI-first dedupe, a selection exports back to
  BibTeX, and notes render `[[cite:<id>]]` as an `Author (Year) — Title` chip
  (ADR-212).
- **Calendar import.** A `.ics` timetable stages a preview, expands recurring
  events into bounded planner items, dedupes re-imports by calendar UID, and
  fills `exam_date` only after an explicit confirmation (ADR-213).
- **Markdown-vault preset.** Link a folder of Markdown notes: frontmatter
  titles/tags, resolvable `[[wikilinks]]` with backlinks, versioned rescans, and
  a "download as vault" export (ADR-213).
- **Site presets.** Wikipedia, MIT OpenCourseWare and OpenStax join Khan
  Academy as default discovery site presets (data only).

### Changed (record — plan 83 / ADR-206/207)
- **`docs/STATUS.md` is a lean living index.** The phase header, module-status
  table, open issues and next-round pointers stay; the ~9,200-line narrative
  (round as-builts, dated changelog, incident post-mortems) moved to
  `docs/dev/history.md` (9,573 → 237 lines and 9,386 archived).
- **The STATUS version line is auto-derived.** `scripts/version_manager.py`
  gained a `check` command and a `[[propagate]]` entry for
  `docs/STATUS.md`; `scripts/check-status-version.sh` runs in CI, so a version
  bump cannot leave `v0.8.0` in the header again.
- **Three contradicting docs corrected:** the data model no longer lists the
  shipped `study_sessions` as "not yet built", and the SDK reference describes
  the live two-strikes `failing` status instead of calling it reserved.
- **Plan corpus hygiene:** seven shipped plans flipped to COMPLETE (as-built),
  the two stale `HANDOFF-*` files and the duplicate library-placement plan were
  archived, and a deferred-follow-ups register now lives in the family plans
  README.

### Added (quality gates — plan 84 C/D / ADR-210)
- **Coverage is measured report-only.** CI publishes `pytest --cov=app` and
  vitest v8 coverage artifacts on every PR; no floor is set until a month of
  numbers exists (baseline 2026-10-22: 88% backend statements, 77.5% frontend
  lines).
- **Golden OCR/extraction regression gate.** `tests/evals/test_ocr_golden.py`
  + `ocr_thresholds.json` score per-page routing, native PDF extraction and
  hybrid assembly against recorded thresholds (block structure, math-fence
  integrity, numeric fidelity). The deterministic subset runs in CI; the live
  vision half is opt-in (`SA_EVAL_LIVE=1`). Proven with three synthetic
  fixtures; the owner's real scans drop into the documented `golden/` slots.
- **Two e2e smoke specs:** `07-discovery` (link material → Discover dialog)
  and `08-extensions` (MCP connector → refresh → instance status → docs).

### Changed (structure — plan 84 A/B / ADR-208/209)
- **`NodeWorkspace` is a tab host (3,395 → under 400 lines).** Per-tab
  components live under `features/courses/workspace/` (`MaterialsTab`,
  `OverviewTab`, `NotesTab`, `CoverageTab`, `TutorTab`, plus `tabs.ts`,
  `navigation.ts`, `shared.tsx`); the shell keeps routing, query wiring and
  the shared header. The colocated test block was split 1:1 into
  `workspace/__tests__/` with a shared harness (95 tests, count unchanged).
- **Backend router domains split (zero route-shape change):** planner + ICS
  → `api/plan.py`, node/tree/placement/outline/concepts → `api/nodes.py`,
  genesis → `api/genesis.py`; `course_bundle.py` → `course_export.py` /
  `course_import.py` / `course_validate.py`. Regenerating `openapi.json`
  produces an empty diff (the proof).
- **`ca-course/v2` rows are TypedDicts:** manifest, course, tree, concepts
  (rows + links + coverage), materials (drawings/extraction/index card/links)
  and folders (rows + links) are declared wire types (plan 82-D residual 5).
- **Pyodide is lazy:** the code-question runner is dynamically imported, so
  the 9.6 MB runtime is no longer reachable from the initial route chunk
  (entry 1,709.10 kB → 1,689.25 kB min / 473.36 → 465.22 kB gzip).

### Fixed (frontend flake — plan 84 D)
- **`SnapIntoNote`'s insert no longer races the mutation options.** The
  capture flow reads current state through a latest-ref (and the reset moved
  from a passive effect to the render-phase transition), so a click cannot
  land on a stale `shot === null` closure. Suite deadlines are load-immune
  (testing-library 20 s, vitest 30 s); proven with 5/5 clean full-suite runs
  under concurrent-session load and 20/20 isolated suspect-file runs.

### Removed (legacy residue — plan 82 D / ADR-205)
- **The Phase-0 rendering harness is gone.** The `/spike` route and
  `features/spike/` are deleted; the Settings → Developer tab now shows build
  diagnostics (app/backend version + health). Three unused direct dependencies
  (`simple-icons`, `@radix-ui/react-slot`, `type-fest`) are removed.
- Hot-path payload typing: the chat turn-failure marker and the course-bundle
  adaptation maps are TypedDicts (service layer only; the DB shape is
  unchanged).

### Changed (vocabulary sweep — closed sets at every boundary, plan 82 C / ADR-204)
- **Question types, exercise kinds, flashcard kinds and job handler keys are
  StrEnums.** The API DTOs carry them, so the OpenAPI schema emits closed
  unions: an unknown quiz `type` is rejected with a 422 and a new member
  fails the frontend typecheck until the UI handles it. `questions.type` and
  `exercises.kind` gain DB CHECK twins in migration `0002_vocab_sweep`, and a
  job-dispatch test asserts every `JobType` member has a handler and vice
  versa.

### Changed (typed contracts — generated types everywhere, plan 82 B / ADR-203)
- **Every `lib/api` module consumes the generated OpenAPI schema.** The ~250
  hand-written wire interfaces are gone; what remains is 27 registered
  client-side shapes (narrowed views of open documents plus the few routes the
  schema cannot see), enforced by `pnpm check:api-types` in CI. A backend DTO
  change now fails `pnpm typecheck` instead of silently widening to `string`.
- **Closed payload maps are typed server-side:** the chat turn trace, proposal
  result document, provider status and preset model refs are generated shapes;
  `MaterialOut.provenance` stays an open metadata document by design and
  workspace materials expose `reextract_modes`.

### Changed (no-legacy sweep — mermaid fork removed, plan 82 A / ADR-202)
- **Mermaid diagrams render through `@neuronection/assistant-ui`.** The local
  `components/blocks/MermaidDiagram.tsx` fork is deleted; `BlockRenderer` and
  the editor's mermaid node view consume the library renderer via
  `components/ui/chat-markdown.ts`, and the editor keeps its own
  broken-diagram diagnostic (app logic, not renderer logic).
- **Chat composition hosts renamed** `StudyChatPanel` / `StudyChatSessionList`
  so the family usage audit stops flagging legitimate composition as a shadow
  copy; the app keeps zero local copies of library components.
- The family `HitlProposalCard` gained the study-promoted extras (body slot,
  conflict re-apply, conflict note, `reapply` label); study adopts it with the
  next library release.

### Changed (schema — payload contract law, plan 81 D / ADR-200)
- **Known-shape JSON state is typed; canonical content documents are
  versioned.** `chat_proposals` stores the card's target/snapshot as columns
  (`target_kind`, `target_name`, `target_node_id`, `target_node_path`,
  `original_md`) and its anchored edits in `chat_proposal_anchors`; the
  per-action instruction document stays JSON behind `payload_schema_version`
  and is validated by the action's payload model at every write.
  `chat_sessions.quiz_pending` moved to the one-row `chat_quiz_pendings` table
  (the session API exposes the public card state only — expected answers never
  leave the server), and drawing `view` JSON became
  `view_x`/`view_y`/`view_width`/`view_height`. `notes.body`/`note_versions.body`,
  `chat_messages.blocks`, `extractions.blocks` and drawing
  `strokes`/`ocr_blocks` keep their shape with `<column>_schema_version`
  siblings and write-boundary validation; `profiles.preferences` is validated
  at the preferences API edge. Every remaining JSON column has a named payload
  type and a `keep-open | typed-out` verdict in
  `contracts/data-model.jsonb-inventory.txt`; a model⇄DB drift gate asserts an
  empty autogenerate diff. Migration `0074_payload_law` (real downgrade).

### Fixed (extensions — bundled manifest provenance)
- **The three bundled connectors declared the wrong license.** The
  envelope manifests of `external-sources`, `discovery` and `mcp`
  carried `"license": "MIT"`, while Study Assistant itself ships under
  **Apache-2.0** (repo `LICENSE`, README) — and every sibling host
  (health / career / desktop) already declares `Apache-2.0` on its
  bundled manifests. The provenance field is rendered verbatim on the
  family's extension surfaces (the hub's extension detail pages, the
  in-app Docs dialog), so the wrong identifier reached visitors.
  Corrected to `Apache-2.0` in all three manifests — metadata only, no
  behaviour change.

### Added (per-extension docs — the wave-8 surfaces)
- **Every bundled connector now documents itself** (plan 34 wave 8): the
  three builtins (`external-sources`, `discovery`, `mcp`) carry a `docs/`
  tree (the closed-category `extensionDocsTree` form) with real,
  code-grounded pages — overview / setup / usage / troubleshooting, and
  the mcp connector adds **security** with the T3 perimeter disclosure
  rendered verbatim from the charter (byte-checked by the suite). The
  manifests bind the trees with the `docs` pointer, and the registry
  validates the binding at registration — a pointer with a missing or
  invalid tree throws exactly like an invalid manifest (red-checked).
- **The docs surface**: `GET /api/v1/extensions/{id}/documentation`
  (tree + markdown, opens on the landing page, traversal-safe,
  fence-aware raw-HTML neutralization) and the settings **Docs** action
  on the Web sources / Discovery / Connectors cards, rendering the kit's
  docs dialog (sidebar from the tree, audience badges, landing rule).

### Changed (docs — the Extension SDK set)
- **The extension documentation set lands at `docs/dev/sdk/`** (plan 34
  wave 5, the last content wave): all ten chapters of the family
  taxonomy with the `chapters` marker declared, quickstart = register an
  MCP server (the family template's shape) → refresh → declare the
  discovery contract → DISCOVER uses it, with a REAL transcript and the
  CI-pinned pipeline; five recipes in the four-part frame; the T3
  perimeter disclosure verbatim (byte-verified by the tree gate) in the
  security chapter and the new
  [Add an MCP connector](docs/user/add-an-mcp-connector.md) page. Four
  user pages (`add-a-search-provider`, `add-an-mcp-connector`,
  `manage-web-sources`, `extension-troubleshooting`) join the user
  guide; `docs/docs-tree.json` lists the set chapters and the new pages.
  The set's tree validates in-repo
  (`backend/tests/test_extension_docs_tree.py` — vendored schema +
  fixtures via the family sync, audience routing, both-trees listing,
  verbatim-disclosure + internal-link doc checks). Truthfulness pass
  over the pre-plan-28 leftovers: every stale `Settings → AI →
  Integrations/Skills` and `Settings → Search` path in user/dev docs
  now points at the real Tools-tab sections; `docs/dev/architecture.md`'s
  extension sections re-point to the set.

### Fixed (extensions — real MCP spawns)
- **Every real MCP server spawn raised `TypeError` before the first
  byte of protocol** (plan 34 wave 5 finding): `app/ai/mcp_client.py`
  exited its transport/session stack with a *sync* `with` on an
  `AsyncExitStack` — invalid, and never caught because the whole suite
  monkeypatches the spawn functions. Fixed to `async with` (two sites);
  the suite now carries a REAL-subprocess wall
  (`test_mcp_connectors.py::test_real_stdio_spawn_feeds_discovery_end_to_end`
  + the `tests/fixtures/mcp_discovery_server.py` twin) so the spawn
  path can never silently rot again. Refresh/call against actual
  external servers works for the first time since plan 73-G.

### Changed (settings — the MCP instance surface renders through the family kit)
- **The MCP connectors card swaps onto the `@neuronection/assistant-ui`
  integrations kit** (plan 33 Phase D / ADR-0040 D19/D25): the hand-rolled
  server rows are now `IntegrationInstancesList` — every configured MCP
  server renders as a D19 instance of the ONE bundled `mcp` extension (G1
  grouping), with the family status vocabulary (`ok | degraded | failing |
  stale`), `needs-config` conditions, `last_success_at` and
  `consecutive_failures` coming straight off the wire→kit mapping in
  `mcpIntegrationViews.ts` (desktop's pure-mapping-module precedent;
  statuses narrow through the kit's generated vocabulary). The wire line,
  sealed-credential chips, last error and the refresh/edit actions ride the
  kit's instance-actions slot; delete is the kit's tombstone action; enable
  is the kit toggle. **The Phase-7 wall holds: the T3 perimeter disclosure
  still renders verbatim from the vendored charter** (`GET /mcp/charter` →
  `mcp-t3-disclosure`, asserted byte-for-byte by the card test). The
  declared-tool contract editor (`discovery | parse`) stays study-domain
  app content under the list (the kit has no per-tool channel); the
  add/edit dialog keeps its bespoke keep-token/clear-env semantics.
  WebSourcesCard and DiscoveryCard stay app sections — course-scoped
  RSS/YouTube/site-search scanners and profile site presets are content
  pipelines, not extension sources (the kit's source row models the
  GitOps surface; recorded, not forced). Pin moves to `^0.67.0` (the
  pending library publish wave); local dev runs the tarball overlay
  until it lands.

### Added (family extension charter — plan 32 Phase 7, 2026-10-16)
- **Study converges onto the family extension charter (ADR-0040)** with the
  D24 subsystem home: `backend/app/extensions/` (vendored contract modules +
  the app-side registry, typed errors, instance status, the relocated
  ADR-0035 search trio, the MCP instance lifecycle) and repo-root
  `contracts/` (charter, envelope/source schemas, capability-RPC, the
  contract + polite-HTTP fixture walls — byte-identical via the dev sync
  scripts). Bundled connectors (`external-sources`, `discovery`, `mcp`)
  carry charter-envelope manifests validated at registration — an invalid
  or unhonored-capability manifest throws, never half-runs — and capability
  use is gated by declared data (D3), never probed.
- **MCP servers surface as D19 instances**: `GET /mcp/servers` rows now
  carry the family status vocabulary (`ok | degraded | failing | stale`,
  `last_success_at`, `consecutive_failures`, `needs-config` conditions —
  computed without a migration) and the declared `discovery | parse` tool
  contracts; the settings card renders the status and, verbatim from the
  vendored charter, the T3 perimeter disclosure (`GET /mcp/charter`).
- **The charter typed 15-code error model** (`extensions/errors.py`)
  replaces the local error vocabularies on the extension surface: external
  sources raise typed codes (`invalid`, `not-ready`, `protocol`,
  `provider`, `unreachable`), MCP validation raises `invalid`, and the
  vendored ADR-0035 `SearchError` taxonomy maps onto the charter codes via
  the D4 projection (the vendored trio itself stays byte-identical per the
  ADR-0035 wire contract).
- `docs/user/settings.md` corrected to the real settings tabs (General, AI,
  Tools, Data, Users, Developer) and the MCP/Integrations + status copy.

### Fixed (OpenAI-compatible wire sends `max_tokens` again — endpoint-routed token cap, 2026-10-15)
- **Local and OpenAI-compatible endpoints stop receiving
  `max_completion_tokens`:** Python `langchain-openai` renames the token
  cap unconditionally, which modern OpenAI models require but strict
  compatible servers (Ollama, LM Studio, llama.cpp, vLLM) reject. The
  factory now routes by endpoint (ADR-0038) — api.openai.com keeps the
  modern name, every other base URL gets `max_tokens` via
  `CompatibleChatOpenAI` (with `CompatibleCaChatOpenAI` preserving the
  reasoning-delta extraction). Model ids are never sniffed for the wire
  contract. Pinned by tests/test_chat_models.py.
- **The policy is canonical and enforced:** the wire rules live in the
  vendored `app/ai/wire_params.py` (byte-identical across the family —
  this repo no longer carries its own copy), temperature stays
  omit-unless-configured (study never manufactured a default), the
  shared fixture table (`tests/fixtures/wire_params.fixtures.json`)
  drives the new tests/test_wire_params_contract.py alongside the other
  repos, and alignment rules R6/R7 keep wire construction in the AI
  layer and temperature defaults out of app code.

### Added (model transport knob — reasoning + function tools on gpt-6 via the Responses API, 2026-10-15)
- **Model rows can set `chat_transport='responses'`** (nullable column,
  migration 0071) to ride the Responses API — honored only when the
  base URL is api.openai.com (compatible servers don't implement
  /responses and keep completions), always store-less (`store=False`).
  The gpt-6 family rejects function tools + `reasoning_effort` on chat
  completions; the knob keeps reasoning on tool tasks, while
  `reasoning_effort='none'` remains the zero-config alternative.
  `auto`/NULL stays on completions — nothing changes for existing rows.
  The shared fixture table pins the resolution matrix. **Field learning,
  same day:** gpt-6 rejects tool tasks on completions even with
  reasoning_effort omitted — so `auto` now routes by endpoint
  (api.openai.com → responses store-less, else completions;
  `chat_transport='completions'` pins the legacy wire).

### Changed (Add-model form polish — provider context, modern manual toggle, capability implications, 2026-10-13)
- **The form always answers "model of what?":** the add/edit modal opens
  with a discreet provider context banner (configured name + base URL)
  above the picker, and the manual-id toggle becomes a labelled ghost
  control with direction copy (pen icon → manual entry; "Pick from the
  catalog" to go back) — library 0.57.0 (`providerContextLabel`,
  `useCatalogLabel`).
- **Vision/tools imply text:** the form expresses the family's own
  semantics (`infer_caps` builds text first and appends the modifiers;
  every preset vision/tool model carries text) via `capImplications` —
  selecting Vision or Tools auto-enables Text, and deselecting Text
  drops everything that implies it. Catalog picks normalize the same
  way. i18n en + el + de.
- **Decision slots suggest their basic default:** an empty decision slot
  shows a muted "Suggested: {{model}} ({{provider}})" line from the
  first canonical preset declaring a `decision_default` — display-only,
  never an assignment.

### Changed (embeddings defaults wave — the embeddings slot gap-fills at setup, 2026-10-13)
- **Embeddings defaults join the setup flow:** the canonical presets gain
  `embeddings_model` (docs-verified: openai `text-embedding-3-small`,
  gemini `gemini-embedding-2`, mistral `mistral-embed`, ollama
  `nomic-embed-text` — pull-required; honest nulls elsewhere; openai and
  gemini ids join curated lists so catalog curation keeps them) and
  setup gap-fills the EMPTY `embeddings` default slot from it —
  `bind_embeddings` joins the options body (D14's binds + embeddings),
  `assigned_embeddings_model` rides the outcome, never-clobber rules
  hold, and `bind_embeddings: false` binds nothing. Contract matrix
  cases 21/21b pin the gap-fill both ways. i18n unchanged (the slot
  predates this wave).

### Added (plan 26 follow-up — decision models in the manual Add-model form, 2026-10-13)
- **Add-model speaks decision:** the models-tab add/edit form (library
  `ModelRegistry`, assistant-ui 0.56.0) gains standalone capability
  kinds — decision, speech-to-text, text-to-speech and embeddings select
  exclusively (a standalone kind replaces the chat caps and vice versa —
  the family's D4 slot-separation law expressed in the form), and a
  decision selection stamps the transport seam (read-only
  `Transport: systemone`, carried on the row). Generation options —
  temperature, max tokens, reasoning effort — now render per capability
  (only for chat-family caps), so decision/stt/tts/embeddings models get
  the minimal form.
- **Backend contract:** `POST/PATCH /api/v1/models` accept `decision`
  caps on any provider row (the API vocabulary gains the frozen §15
  `decision` capability) plus `decision_transport` (validated — the one
  shipping transport, `systemone`); creating/editing a decision model
  stamps the transport from the payload or the default, and editing the
  caps away clears it. Matrix-pinned by the new contract test.

### Added (plan 26 follow-up wave B — capability chips on the setup tiles, 2026-10-13)
- **The preset grid is self-explanatory:** the setup wizard derives
  per-tile capability chips from the API preset data — chat type → Chat
  (+ Vision where the preferred model carries it, + Speech-to-text where
  `stt_model` exists), `decision_models` → Decision, keyless-local →
  Local — rendered by assistant-ui 0.55.0's new `chips` prop with i18n
  labels (`settings.setup.chip*`, en + el + de). The grid now reads:
  openai [Chat, Vision, Speech-to-text] · gemini [Chat, Vision] ·
  openrouter [Chat, Decision] · typesafe [Decision] · anthropic
  [Chat, Vision] · groq/mistral/deepseek [Chat] · ollama
  [Chat, Decision, Local].

### Changed (plan 26 §13.3 follow-up — decision presets exposed, 2026-10-13)
- **Three decision providers, one transport, docs-verified:** the
  `typesafe` preset flips into `presetOrder` (a decision-only tile after
  OpenRouter; keyUrl → docs.typesafe.ai/api with console-worded steps —
  the console URL is not stated in the docs); Ollama gains decision
  models (`nimble` default, `tev1`, `clef`, `clef-flash` — pull-required,
  version floor riding the preset steps: v0.35.0+, clef models v0.35.1+);
  OpenRouter's decision ids are corrected to `typesafe/jev-1.13` (pinned,
  the default) + `~typesafe/jev-latest` (rolling) with the systemone
  surface pinned via `base_url_override` (`https://openrouter.ai/api` —
  the `/api` prefix; the SDK appends `/v1/systemone`). No `provisional`
  markers remain on decision data. Canonical + sync re-vendored
  byte-identical; `presets_data.py` regenerated.
- **Keyless decision resolution (local Ollama):** the official
  `typesafe-sdk` requires a non-empty API key (D9), so keyless presets
  (no `key_url` in the canonical data) resolve through the explicit
  sentinel key instead of failing `needs-key`; keyed presets keep the
  needs-key failure. Pinned by the conformance suite; the contract
  matrix's exposure assertions flip to the new reality (typesafe in
  `presetOrder`, openrouter ids corrected, ollama decision data pinned).

### Changed (plan 26 §13.8/§15 no-legacy + single-source sweep, 2026-10-13)
- **No canonical model ids as code literals:** the decision probe's
  model id derives from the synced preset data via
  `decision_probe_model_id()` (specs → `decision_default`, raising on a
  preset that declares neither — never an invented `jev-latest`), and
  the key-only `POST /providers/{id}/test` probe derives from the
  provider's preset stamp; a decision provider with neither models nor
  a derivable preset returns an actionable failure. Contract matrix
  gains the derivation pin (case 20b).

### Changed (plan 26 Phase 6 closeout)
- **Ruff: the generated presets module is excluded from the formatter**
  (`[tool.ruff.format]` exclude; the lint E501 per-file-ignore stays) —
  the scoped family accommodation for a file that is emitted, never
  hand-edited, and not formatter-stable. Ten Phase-3 files
  (`app/ai/decide/`, `app/ai/providers/`, `app/api/ai_settings.py` and
  four test files) are reformatted: `ruff format --check .` was red on
  them. Vendored gates re-synced (byok gate **R8** — no needle/llm
  decision-engine code; alignment family table all-strict; convergence
  `--self` layout probe).
### Fixed (plan 26 Phase 6)
- **The setup-modal clipboard mock restores the writeText Promise
  contract** (`mockResolvedValue`) — a bare `vi.fn()` returning
  undefined fired an unhandled rejection that red-exited the whole
  vitest run even at 1436/1436 green.

### Fixed (2026-10-13 incident)
- **One failing chat turn no longer locks the whole app:** the turn job
  held its SQLite write transaction across minutes of provider retries, so
  every concurrent request failed with `database is locked`. The handler
  now commits the pre-engine writes before the turn engine starts, and the
  mention-registry refresh inside turn preparation commits immediately
  instead of flushing into a transaction that stayed open until the
  contract step. Regression tests probe the write lock from a second
  connection during a blocked model call, blocked preparation, and the
  retry window.
- **`touch_last_used` is throttled and fail-soft:** the per-request
  profile-timestamp write runs at most once a minute per profile and a
  busy database logs-and-skips instead of failing the request.

### Added (plan 26 Phase 3)
- **Decision models (Python decision reference):** `decision` joins the
  model-capability vocabulary (explicit only) and `models.decision_transport`
  (`systemone`) is the transport seam (migration 0069, tested downgrade);
  assignment moves to four `decision:tool-dispatch | decision:boolean-gate |
  decision:choice | decision:score` slots (primary + fallback) in
  `DefaultTaskAssignment`/course defaults. Setup gains `bind_decision`
  (capability-aware gap-fill, never a live slot or `open-args`), decision
  rows persist from preset `decision_models`, and the provisional
  decision-only `typesafe` preset validates via the 10 s decision probe
  (classified failure persists nothing; it renders no tile). New
  `app/ai/decide/` funnel: transport registry over the slots (D2b routing,
  fallback chain, per-assignments-revision cache), `typesafe-sdk` client
  behind a typed seam, the tool-dispatch projection, `run_decision` with one
  audit row per invocation, and the shared conformance suite. Settings UI:
  *Decision models* group (library pickers, decision-only filtering, privacy
  notice at the group), decision rebind rows in the setup success panel, and
  the re-run review's five-bind body. Contract-test matrix grows to 20 cases
  (bind_decision, probe, slot separation, presets-v2 shape).

### Changed (plan 26 Phase 3)
- `scripts/check-ai-alignment.sh` re-vendored after a dev-master fix: R1's
  Python scope sanctions `typesafe_sdk` inside the whole `app/ai` layer
  (matching desktop's JS scope and the frozen §3.7 text) instead of the chat
  factory file alone. `typesafe-sdk>=0.7,<0.8` added (AI-layer confined).
- `pnpm api:types` works headless again: `scripts/export-openapi.py` now
  migrates its scratch database and pins `app_env=development` (the startup
  seed needs tables; the production boot guard no longer trips on export).
- `pnpm-lock.yaml` resolved the published `@neuronection/assistant-ui@0.54.0`
  integrity (owner published the RC; the Phase 2 registry-pin follow-up).

### Changed (plan 26 Phase 2)
- **Setup UI swaps to the library kit:** `ProviderSetupModal`'s tiles and
  guided form and `ReRunSetupDialog`'s review now render
  `@neuronection/assistant-ui` components (`provider-setup-tiles` with the
  manual tile, `provider-setup-form` with hosting/country riding
  `advancedExtra` and §15 error-enum copy via `errorLabels`,
  `setup-review` over the library switch row); the local `ProviderLogo.tsx`
  and the hand-rolled review `SwitchRow` are deleted in the same commit.
  The review keeps its four-key snake_case wire body (`bind_decision`
  arrives with the Phase 3 decision port). Dep pin `^0.51.0` → `^0.54.0`
  (0.54.0 pending publish — verified against the packed release-candidate
  tarball: frontend lint + typecheck + 1429/1429 tests + build, backend
  1407 passed + 4 skipped, byok R1–R7 + alignment gates green;
  `minimumReleaseAgeExclude` gains 0.54.0).

### Fixed (plan 20 S14 residual)
- **The §4.5 control now knows the entrypoint mode:** the public
  `GET /api/v1/instance/config` reports `identity_mode` (from the auth
  kit — public fact, not secret), and the settings Users tab passes
  `serverIdentity` to `InstanceModeControl` — "Remove login" is blocked
  with the server reason on server instances instead of being offered
  and failing at the API. OpenAPI types regenerated (`pnpm api:types`).

### Security (plan 21)
- **App-level rate limiting + hardened response headers (new coverage;
  kit v0.4.0, re-pinned `eb3499103ce91cb52e3282c72129f72ed419f3bb`).**
  Study previously had no limits above the auth surface and no response
  hardening. The kit's family limiter + `SecurityHeadersMiddleware` now
  mount with study's policy: `SA_RATELIMIT_{ENABLED,AUTH,AUTH_EMAIL,AI,
  MCP,DEFAULT}` ceilings (requests/minute; `0` disables a general
  bucket), login-shaped endpoints → AUTH, AI surfaces (`/ai`, `/chat`) →
  AI, other `/api/` → DEFAULT, trusted-proxy per-IP identity, and the
  family header baseline with the web/desktop CSP split (`'unsafe-eval'`
  only for the valid per-boot `?shell=` marker — the desktop shell
  document). New `tests/test_rate_limit.py` +
  `tests/test_security_headers.py` pin the R1–R7 / H1–H3 matrix rows as
  contract cases (§18.19–22).

### Security (plan 19 Phase 4)
- **At-rest secrets now sealed with the family cipher:** values stored in
  the OS keyring (AI provider keys, the web-search key, MCP server
  tokens/env) are written as `enc::<fernet-token>` strings under the
  per-instance `SA_DATA_KEY` (`nx_auth.atrest`, the shared audited
  implementation) instead of plaintext keyring entries — the keyring
  stays the only storage. Existing plaintext entries keep reading
  verbatim (study's values are keyring-held; there is no database
  ciphertext to migrate), and values that cannot be decrypted read as
  empty — never a guess.
- **At-rest key rotation:** set `SA_DATA_KEY_PREVIOUS` (comma-separated)
  to prior keys to keep old sealed entries readable after swapping
  `SA_DATA_KEY`; the production boot guard now validates every prior
  entry too. Runbook: `docs/dev/security.md` "Rotating the at-rest key".
- The legacy pre-rename `CourseAssistant` keyring-service fallback is
  gone (plan 20 §6c, folded into this phase): keyring entries written
  under the old service name are no longer copied forward.
- The pre-rename `CourseAssistant` data directory is no longer migrated:
  `default_data_dir()` is a pure path computation now (plan 20 §6c,
  folded into this phase). A machine still on the old directory name
  moves or re-links it manually (`SA_DATA_DIR` also relocates it).

### Changed (plan 24 V2)
- **One family chat vocabulary on the chat stream:** the WS chat topic now
  carries only the family events (`flow_started` / `node_started` / `delta`
  / `tool_call` / `flow_finished` / `flow_failed` / `flow_interrupted`) —
  the legacy names (`stream_start`, `phase`, `stream_delta`,
  `assistant_message`, `turn_error`, `stream_interrupted`) and the
  dual-emit mapper are gone, backend and frontend in the same change. A
  stopped generation now ends through the terminal `flow_interrupted`
  event (library ≥ 0.51.0), so every consumer of a turn learns about the
  stop; chat behavior is otherwise unchanged (same reasoning stream, tool
  cards, stop UX, edit/regenerate).

### Fixed
- **Dev-db interpolation could read the prod env file:** `docker compose -f
  docker/docker-compose.dev-db.yml` interpolates `${POSTGRES_DB}` /
  `${POSTGRES_TEST_DB}` / `${SA_DB_PORT}` from the compose file's *directory*
  `.env` — i.e. `docker/.env`, the standalone/prod stack's env file — so a
  prod value could silently reshape the dev DB that `run-dev.sh` then
  connects to (the bootstrap password was already pinned in the compose
  file against exactly this mismatch). `run-dev.sh` now pins the
  interpolation to the dev root `.env` (empty env when absent); shell
  exports (worktree-style `SA_DB_PORT`/`COMPOSE_PROJECT_NAME` overrides)
  still win over it.

### Changed (plan 20 Phases 6–7)
- **No-legacy sweep (D10):** the CourseAssistant-era surface is gone —
  `ca-drawing://` / `ca-image://` / `ca-material://` → `sa-*` schemes,
  `ca-course/v*` / `caq/v1` / `ca-backup/v1` / `ca-skills/v1` → `sa-*`
  format markers, legacy card kinds `basic`/`cloze`/`reverse` →
  `card_basic`/`card_cloze`/`card_reverse` (one-shot migration `0068`
  rewrites stored strings; the LLM card prompts speak `card_*` now).
  `LEGACY_CARD_KIND_MAP` and its two bridge functions are deleted; the
  `ca-*` storage-key namespace, drag MIME types and `CaMath` component
  drop the prefix.
- **Family convergence gate** (`check-family-convergence.sh`, vendored +
  CI).

### Fixed
- Migration `0068` is PostgreSQL-safe (json columns cast to text and
  back — `replace()` has no json form) and the deploy path works
  end-to-end: `entrypoint.sh` drops a bash-only substitution, the
  compose services pass the §8 key pins into the app container, and
  `sqlalchemy[asyncio]` is a declared dependency. Found by the
  standalone stack boot smoke (migrate → app healthy → nginx).


### Changed
- **Plan 20 Phase 4 — uniform family skeleton:** `main.py` is wiring
  only (≤250 lines): identity install → `app/auth/install.py`, profile
  binding + SPA fallback → `app/middleware.py`, per-boot seeding →
  `app/seeds.py`, job handlers → `app/jobs/registry.py`. The desktop
  bootstrap moves to `app/local.py` (career's reference shape: data dir,
  `SA_IDENTITY_MODE=desktop` env defaults, migrations) and
  `studyassistant` runs it before any `Settings` is built.
- **Migrations are never run by app code (D6):** `create_app` no longer
  runs `alembic upgrade head`. The desktop entrypoint migrates
  (`app/local.py:run_migrations`), the docker stack gained a one-shot
  `migrate` service (`entrypoint.sh migrate` / `serve` modes; `app`
  depends on its successful completion — the owner-role two-role split
  is unchanged), `scripts/run-dev.sh` migrates explicitly, and the
  backup **restore** flow migrates the restored DB through the same
  helper.
- **`.env` resolution (ADR-0028 §4):** explicit `SA_ENV_FILE` →
  source-anchored walk-up → none — and the walk-up is **disabled outside
  dev/test**, so a baked-in `.env` can never downgrade a production boot
  (health audit rule C-5). Production operators point `SA_ENV_FILE` at
  the deployment file explicitly.

### Added
- `tests/test_local.py` (bootstrap: desktop env defaults, entrypoint
  migrations) and S9 coverage for the `.env` resolution rules.

### Changed
- **Identity glue unified on the auth-kit (plan 20 Phase 2, ADR-0028):**
  the instance-init logic is now `nx_auth.instance.initialize_instance`
  — fixing two contract bugs in the old inline copy:
  - **§4.4 violation fixed (B1):** `SA_AUTH_MODE=open` with server
    identity used to seed an **open server instance**; it now initializes
    `authenticated` with a loud warning (desktop `open` is unaffected).
  - **`.env` knobs reached dead code (B2):** the kit config was built
    from `os.environ` only, so `SA_COOKIE_SECURE`, TTLs, lockout, etc.
    set in `backend/.env` were silently ignored. All §16 knobs are now
    routed from `Settings` through `nx_auth.config.knob_overrides` (OS
    env still wins per key).
- **New `Settings` fields (ADR-0028 §16):** `SA_APP_ENV` (fail-safe
  `production` default; `scripts/run-dev.sh` sets `development`),
  `SA_AUTH_ACCESS_TTL_MINUTES` / `SA_AUTH_REFRESH_TTL_DAYS` /
  `SA_AUTH_REFRESH_ABSOLUTE_DAYS` / `SA_AUTH_LOCKOUT_THRESHOLD` /
  `SA_AUTH_LOCKOUT_MINUTES` / `SA_AUTH_PASSWORD_MIN_LENGTH` /
  `SA_REGISTRATION_ENABLED` / `SA_COOKIE_SECURE` /
  `SA_TRUSTED_PROXY_COUNT` / `SA_RATELIMIT_AUTH` /
  `SA_RATELIMIT_AUTH_EMAIL`, and the §8 key pins `SA_SESSION_KEY` /
  `SA_REFRESH_KEY` / `SA_DATA_KEY` (all three or none). `SA_AUTH_MODE`
  is now validated fail-closed by the kit instead of raising at settings
  load.
- **Production boot guards (nx_auth.boot):** production boots abort on
  partial/weak key pins, non-Fernet `DATA_KEY`, `SA_DEBUG=1` or
  `SA_DEMO_MODE=1`; server boots require pinned keys (desktop keeps its
  generated 0600 `auth_keys.json`). Key resolution is
  `KeyRing.load_for("SA", config_dir, pinned=…)` (Settings-backed, so
  `.env` pins work like env pins).
- **`studyassistant web`** now declares desktop-class identity like the
  `app` mode (local entrypoint ⇒ `SA_IDENTITY_MODE=desktop`); docker/
  uvicorn runs stay server-class. `identity_mode` parsing fails closed to
  `server` on unknown values.

### Added
- `tests/test_contract_identity_glue.py` (§18 contract cases S1, S2,
  S13-S15) and `tests/test_sec16_env.py` (§18.14 knob-routing matrix,
  ported from career's `test_sec16_env.py`).

## [v0.12.1] - 2026-10-01

**Operational notes for deploy:** the v0.12.0 release's GHCR job failed
(no Docker image was published for v0.12.0) — v0.12.1 ships the first
image of the 0.12 line.

### Fixed
- **GHCR image build fixed (auth-kit git pin):** the Docker build still
  wired the family auth-kit as an editable `../auth-kit` path dep (named
  `auth-kit` build context, release workflow + compose flavors) while
  `pyproject.toml`/`uv.lock` had moved to a git-SHA pin — `uv sync` then
  cloned from GitHub and failed on the missing `git` binary, so no Docker
  image was published for v0.12.0. The Dockerfile now installs `git`
  transiently for the sync (purged before the layer commits), the obsolete
  build context is gone everywhere, and building needs network access to
  GitHub instead of a sibling `../auth-kit` checkout.

## [v0.12.0] - 2026-10-01

**Breaking changes:** web/server deployments now enforce the login gate
(identity class D — `users`/`auth_sessions`/`instance_settings`/
`audit_events`, cookie sessions + CSRF), and the web datastore was renamed
`neuro_*` → `neuronection_*` (ADR-0022 revision).

**Operational notes for deploy:** existing installs migrate the datastore
names automatically (`run-docker.sh` / `update-docker.sh` boot hook;
manual recipe in `docker/README.md` → "Renaming `neuro_*` →
`neuronection_*`"). Web deployments surface the login gate on upgrade —
the first registered user bootstraps as admin (§12).

### Added
- **Demo scripted tutor + use-case tour:** the local mock provider
  (frontend/e2e/mock_provider.py) gained prompt-keyed demo answers that
  the real pipeline renders as KaTeX math, a Plotly chart, a flashcard
  proposal card and grounded citations; `scripts/ui-capture/seed-demo-ai.py`
  provisions it as the demo instance's text/embeddings model (guarded,
  idempotent). The tour grew to 13 scenes including the node workspace,
  study session, material detail and a revealed flashcard with FSRS
  ratings.
- **Demo tour capture pipeline (family demo-tour standard):** reproducible
  screenshot gallery + `visual-tour.gif` generated from a seeded demo
  workspace via `./scripts/capture_ui.sh` (`scripts/ui-capture/`, family
  template v1.2.0). Cookie-session auth as the demo users, webapp-mode
  single-origin capture, `tour.manifest.json` emitted for the website; boot
  recipe in `docs/dev/visual-tour.md`. The capture seed also provisions the
  local scripted tutor (`scripts/ui-capture/seed-demo-ai.py` +
  `frontend/e2e/mock_provider.py` demo scripts) so the tutor chat demo
  renders math, charts and flashcard proposals with no AI configured.
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
- **Family datastore naming amended (ADR-0022 revision): `neuro_` →
  `neuronection_` prefix.** The truncated prefix read as meaningless to
  users — "neuro" suggests neurology, not the Neuronection family — and
  self-hosters see these names in psql, backups and error messages. The
  pattern shape is unchanged: study's database is `neuronection_study`
  (+ `neuronection_study_test` / `neuronection_study_demo`) with roles
  `neuronection_study_owner` / `neuronection_study_app`. Family law
  (ADR-0022 clause 5 + `guidelines/deployment.md`) was amended first;
  this repo adopts it across compose defaults (`standalone` / `prod` /
  `dev-db` / `demo`), `init-db.sh` / `init-dev-db.sh`, the
  backup/restore scripts, CI + release test jobs (test database *and*
  the bare `postgres` bootstrap user moved onto the family owner role),
  `config.py`, seeder messages, SECURITY and docs. **Existing installs
  migrate automatically**: `run-docker.sh` / `update-docker.sh` gain
  `migrate_legacy_db_names()` (`scripts/lib-docker.sh`) — a guarded,
  idempotent `ALTER DATABASE` / `ALTER ROLE` rename run before the stack
  boots; PostgreSQL can't rename the session's own user, so the owner
  role goes through a throwaway `sa_db_migrator` superuser. Fresh or
  already-renamed stacks no-op; an old+new pair that both exist aborts
  with instructions. Dev DBs are disposable (recreate with
  `docker compose -f docker/docker-compose.dev-db.yml down -v`), and the
  demo database is renamed by the manual recipe or re-seeded — recipes
  in `docker/README.md` → "Renaming `neuro_*` → `neuronection_*`".
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
- **Chat streaming no longer drops an answer's tail chunk** (the
  `test_stream_deltas_are_coalesced` CI flake): LangGraph's merged
  `updates`/`messages` queue can deliver a round's final token chunk
  after the last `updates` tuple, and the chat engine's teardown then
  flushed only the assembled buffer, silently dropping the pending
  tail. Teardown now flushes the pending line at round-end semantics,
  and the delta pump's buffers — shared between the node worker thread
  and the event loop — are serialized under a lock (the unlocked
  read-then-clear windows dropped text under thread interleaving).
- **auth-kit contract drift closed (identity kit refresh):** the
  `UserStore.create` adapter follows the kit's tri-state `is_admin`
  (`None` = §12 first-user-admin bootstrap; `False` = never admin — the
  demo principal stays a non-admin even as user #1, which the old
  `False`-as-unspecified coercion could bootstrap to admin; `True` =
  forced admin), and the instance-transition contract test follows §11.3:
  an `open` instance answers 404 to `/auth/register`, so the second
  account is now created after the open→authenticated flip. Green again
  under mypy strict and the full suite against auth-kit 0.1.0.
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
