# Security model

Study Assistant is a **dual-mode product** (family identity class D): a
local-first desktop app and a self-hosted web/server deployment, both with
accounts — sessions, profiles, and admin user management come from the
family auth-kit mounted at `/api/v1/auth/*`, `/api/v1/me/*`, and
`/api/v1/admin/*` (family plan 16, ADR-0013). The security work is about
protecting local and in-transit secrets, enforcing user → profile
ownership, treating AI output as untrusted, and keeping user data and
tests isolated. This page is the map; the secrets rule is also in the
[repository `AGENTS.md`](https://github.com/neuronection/study-assistant/blob/main/AGENTS.md).

## Threat model

The threat model (identity-auth §20 — auth surface, instance mode, session
storage, trust boundaries, data isolation, secrets at rest, audit, admin
surface, deployment exposure) lives in the repository's
[`SECURITY.md`](../../SECURITY.md) — **one source of truth**; keep this
page's sections below in sync with it when security behavior changes.

## Secrets

- API keys live **only in the OS keyring**, accessed through
  `backend/app/core/secrets.py` (`keyring`, service `StudyAssistant`). They are
  never written to files, env blocks or the database.
- Secrets are masked in every API response (for example `••••1234`); the full
  value never leaves the keyring except on the outbound provider call.
- A pre-rename `CourseAssistant` keyring service is read as a fallback and
  copied forward on first read; the legacy entry stays as a backup.
- **Token material is separate**: three independent per-instance keys
  (`nx_auth.keys.KeyRing`) — `SA_SESSION_KEY` (session JWTs), `SA_REFRESH_KEY`
  (refresh JWTs), `SA_DATA_KEY` (Fernet at-rest sealing) — env-first, else a
  generated `auth_keys.json` at 0600 in the config dir
  (`~/.config/StudyAssistant/`); no key is derived from another. They never
  appear in backup archives or the database.
- **Tests must never touch the real keyring.** `backend/tests/conftest.py`
  installs an in-memory backend for the whole suite; any new secret read/write
  goes through `secrets.py`, which that fixture isolates.

## Identity glue & boot guards (ADR-0028, plan 20)

- **One §4 implementation.** Instance init (`instance_settings.auth_mode`
  / `demo_mode`) runs through `nx_auth.instance.initialize_instance` —
  §4.4 coerces `SA_AUTH_MODE=open` on a server entrypoint to
  `authenticated` with a loud warning, unknown values fail closed, and
  post-init env flips are ignored loudly (mode changes are admin actions,
  `PATCH /api/v1/admin/instance`). The pre-plan-20 inline copy seeded an
  open server on `SA_AUTH_MODE=open` (bug B1) — fixed and pinned by
  `tests/test_contract_identity_glue.py`.
- **§16 knobs are Settings-routed (bug B2, fixed).** The kit config is
  built through `nx_auth.config.knob_overrides` from `Settings`, so
  deployment `.env` values (`SA_COOKIE_SECURE`, TTLs, lockout,
  `SA_REGISTRATION_ENABLED`, `SA_TRUSTED_PROXY_COUNT`, `SA_RATELIMIT_*`)
  reach the kit exactly like OS-environment ones (OS env wins per key).
  Pinned by `tests/test_sec16_env.py` (§18.14).
- **Production boot guards.** `nx_auth.boot.validate_boot_config` runs at
  app construction and aborts production boots (`SA_APP_ENV=production`,
  the fail-safe default) on partial/weak key pins, non-Fernet
  `SA_DATA_KEY`, or `SA_DEBUG`/`SA_DEMO_MODE`; server boots require
  pinned keys while desktop self-hosting keeps its generated
  `auth_keys.json` (warning). `scripts/run-dev.sh` sets
  `SA_APP_ENV=development`.
- **Key pins** (`SA_SESSION_KEY`/`SA_REFRESH_KEY`/`SA_DATA_KEY`) resolve
  through `KeyRing.load_for("SA", config_dir, pinned=…)` — all three or
  none, from env **or** the deployment `.env`, else the 0600
  `auth_keys.json`.


### Turning on login (the "desktop app with users" story)

- **At initialization:** set `SA_AUTH_MODE=authenticated` before the
  first boot of an empty DB (or answer "Shared device" in the first-boot
  wizard) — the desktop instance then shows the login screen instead of
  booting straight into the last-used profile. DIM auto-login stops
  applying (§11.5): no `local-boot` token is ever valid again.
- **At runtime:** Settings → Users → *Access mode* (the shared
  `InstanceModeControl`, §4.5): "Require login" sets the owner password
  and flips `open → authenticated` in one audited admin action;
  "Remove login" needs the current password plus an explicit
  acknowledgement, and is refused while other accounts exist (and always
  on server entrypoints).
- Mode changes are **never** launch-time actions — env flips after init
  are ignored with a loud warning (§4.1). Multi-user works once login is
  on: users register (while enabled) or are created through the admin
  surface, and every user gets an auto-provisioned Default profile (§6).

## Network exposure & access control

- Desktop binds `127.0.0.1` on a random port and every request carries the
  per-boot `X-Shell-Token`; the Docker stack runs `SA_HOST=0.0.0.0` behind
  nginx and terminates there. The shipped `nginx.conf` is HTTP-only
  (loopback/VPN/dev); internet-facing deployments use `nginx-TLS.conf`
  (certbot ACME + HSTS) and `SA_COOKIE_SECURE=true`.
- **Every `/api/` route requires a session** (family `SessionAuthMiddleware`,
  deny-by-default 401) except the explicitly exempt auth/health/docs/shell
  prefixes; `/ws` requires the `Origin` gate and a valid access cookie.
  Auth, sessions, and admin user management come from the family auth-kit
  (`/api/v1/auth/*`, `/api/v1/me/*`, `/api/v1/admin/*`) — cookie sessions +
  double-submit CSRF, lockout and rate limits. See
  [`SECURITY.md`](../../SECURITY.md) for the full threat model.
- `X-Profile-Id` **is** an ownership boundary (identity-auth §15): the
  backend verifies the header names a profile the session user owns
  (server: absent ⇒ 400, foreign/malformed ⇒ 403; desktop: last-used
  fallback) and every domain query filters on `profile_id`. Out-of-ownership
  resources answer a hidden 404. Auth, `/me`, `/profiles`, `/admin` are
  header-exempt so the SPA can always discover its profiles.
- Uploads are capped at 200 MB (`MAX_UPLOAD_BYTES`); unknown types are refused
  at the door with a machine-readable reason.

## The AI trust boundary

Model output is **untrusted input**. The rules:

- Every model call goes through the gateway in `backend/app/ai/` — no provider
  SDK calls in application code (see [ai.md](ai.md)).
- Structured outputs are pydantic-validated before use; a response that fails
  its contract is rejected, not repaired silently.
- Chat proposals are never applied directly. They are grounded against the
  turn's real context, surfaced as review cards, and applied only after the
  user approves — see the HITL proposal section of [ai.md](ai.md).
- Externally fetched content (URL imports, discovery results, RSS/YouTube
  metadata) is untrusted too: HTML is stripped, URLs are http(s)-validated, and
  fetched pages are converted to markdown, never executed.
- The chat's math calculator runs deterministic SymPy evaluation with guards,
  not arbitrary code execution; grading never trusts the model's verdict (see
  [math-verification.md](math-verification.md)).

## Data and storage guards

- SQL is parameterized (SQLAlchemy core/ORM) — no string-built queries.
- Blob ids are validated against a strict sha256 pattern before serving;
  originals are content-addressed and never modified.
- The data directory (`~/.local/share/StudyAssistant/` by default) holds the
  SQLite database (`study.sqlite3`, desktop/tests), blobs, cache, thumbnails
  and backups; `SA_DATA_DIR` and the working-directory setting relocate it.
  Web mode runs PostgreSQL 16 (`neuronection_study`) instead — see ADR-0022 in
  [architecture.md](architecture.md).

## Network surface & access roots (family plan 16, S1; ADR-0013/0022)

- **Bind:** the API binds `127.0.0.1` (`SA_HOST` overrides); desktop mode
  (`pnpm app`) additionally listens on a random loopback port.
- **Filesystem browsing (`GET /api/v1/fs/dirs`) is confined to granted
  roots** (ADR-0011): the data dir and the user's home always, plus
  anything listed in `SA_FS_ROOTS` (comma-separated). Resolve first, then
  check — paths outside every root ⇒ 403, symlinked targets resolve before
  the check, and the returned `parent` never points outside the roots.
  There is deliberately **no HTTP grant endpoint** (a grant-all endpoint
  would itself need authentication); extra roots are configured via
  `SA_FS_ROOTS`, and a grant UI is still pending the family auth rollout.
- **WebSocket (`/ws`) verifies `Origin` and the session** (identity-auth
  §10): same-origin or an explicit `SA_CORS_ORIGINS` entry, otherwise the
  handshake is refused before accept (cross-site WebSocket hijack); then
  the access cookie must verify through the same path as the HTTP
  middleware (landed with plan 16 S4a/S6, `backend/app/api/ws.py`) —
  requests **without** an Origin (non-browser clients) pass the origin
  check but still need a valid session cookie. Known gap: bus topics are
  authenticated but not owner-scoped per subscriber.
- **CORS is explicit and deny-by-default:** no
  `Access-Control-Allow-*` headers are emitted unless `SA_CORS_ORIGINS`
  (comma-separated) lists the origin. The SPA is same-origin in every
  shipped mode (vite dev proxies `/api` and `/ws`), so the default (empty)
  needs no CORS at all.
- **Desktop file endpoints (`/api/v1/desktop/*`) mount only when
  `SA_IDENTITY_MODE=desktop`** — set automatically by the pywebview
  entrypoint. Web/server mode does not route them at all (in addition to
  the `state.desktop_files` guard).

## Test isolation

- Network is blocked for the whole backend suite (`socket.connect` is replaced
  with a raising function); HTTP must be injected as a mock transport.
- The keyring is in-memory (above), and each test gets an isolated data
  directory via `tmp_path` fixtures. See [testing.md](testing.md).

## Checklist for a security-relevant change

- [ ] No secret written to a file, env var, log line or DB column.
- [ ] New model calls go through the gateway and validate their output.
- [ ] New external fetches validate scheme/host and strip markup.
- [ ] Tests still never touch the real keyring or the network.
- [ ] Docs updated in the same commit (`docs/STATUS.md` + this page if the
      model changed).
