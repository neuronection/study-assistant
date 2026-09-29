# Security Policy

## Reporting a vulnerability

Please report security issues privately rather than opening a public issue:

- **Email**: constliakos@gmail.com (put "study-assistant security" in the subject), or
- **GitHub Security Advisory**: use "Report a vulnerability" on the
  [Security tab](https://github.com/neuronection/study-assistant/security/advisories/new).

Include a description, the affected version (`python -m studyassistant` prints
it; also in Settings → About), and reproduction steps. You will get an
acknowledgement within a few days and a fix timeline once the issue is
triaged. Fixes land as patch releases; reporters are credited in the release
notes unless they prefer otherwise.

## Scope

Study Assistant is a **dual-mode product** (family identity class D): a
local-first desktop app (`python -m studyassistant app`) and a self-hosted
web/server deployment (`docker/`, `python -m studyassistant web`). The
supported security scope is:

- the FastAPI backend and its API (loopback + per-boot shell secret on
  desktop; nginx-fronted in the Docker stacks), including the family
  identity surface — accounts, sessions, profiles, admin user management
  (`/api/v1/auth/*`, `/api/v1/me/*`, `/api/v1/admin/*`),
- the datastore: SQLite (`study.sqlite3`) on desktop/tests, PostgreSQL 16
  (`neuro_study`) in web mode, the blob store, and backup archives
  (in-app `backups/`, `pg_dump` sidecar, `scripts/backup.sh` archives),
- the OS keyring integration (AI/search/MCP API keys are stored via the
  system keyring, never in files, environment blocks, or the database),
- the desktop shell (pywebview/WebKitGTK) and the served SPA,
- the deployment configurations (`docker/`, nginx configs, CI pipelines),
- the AI provider integrations (keys are sent only to the provider base URLs
  you configure).

Out of scope by design: multi-tenancy (there are no tenants — isolation is
`user → profile`, see the threat model below) and any exposure the operator
adds beyond what the shipped configs describe (reverse-proxy chains not
matching `SA_TRUSTED_PROXY_COUNT`, plain-HTTP internet exposure, and so on).

## Family baseline (enforced in CI where possible)

- Secrets never committed; `.env` gitignored; `.env.example` value-free.
- API keys: OS keyring — never in code, env files of clients, or logs. (The
  family baseline's "DB-config via admin UI" web alternative is **not**
  implemented in study — both modes use the keyring; see known gaps.)
- AI model output is untrusted input: schema-validated, allowlisted tools.
- CSP single-sourced in the serving config; no external origins.
- Dependencies: Dependabot + pip-audit; lockfiles committed.

## Threat model

The family identity & auth standard (identity-auth §20) defines these
surfaces; this table is the single source of truth for study's answers and
is linked from [docs/dev/security.md](docs/dev/security.md).

| Surface | Answers for this repo |
|---|---|
| Auth surface | Unauthenticated: `POST /api/v1/auth/register` (403 when `SA_REGISTRATION_ENABLED=false`), `/login`, `/refresh` (needs a valid refresh cookie or Bearer refresh), `/demo` (404 unless `demo_mode=true`), `/desktop/exchange` (mounted only in desktop + `auth_mode=open`; requires the per-boot `X-Shell-Token`); plus `/api/v1/health`, `/api/docs`, `/api/v1/shell/rendered`, and the static SPA. Everything else under `/api/` 401s in `SessionAuthMiddleware`; `/ws` requires the `Origin` gate **and** a valid access cookie. Rate limits: in-process sliding windows — 10/min per IP on register/login/refresh, 30/min per email on register/login (429 + `Retry-After`; ceilings are code defaults in `AuthConfig`, per-IP identity from the rightmost trusted proxy hop via `SA_TRUSTED_PROXY_COUNT`, default 0). Lockout: 5 consecutive failures ⇒ 423 for 15 min (`SA_AUTH_LOCKOUT_THRESHOLD` / `SA_AUTH_LOCKOUT_MINUTES`), generic `Invalid email or password`, dummy-hash verify against timing enumeration. Passwords ≥ 10 chars, bcrypt. |
| Instance mode | `auth_mode` / `demo_mode` are rows in `instance_settings` — DB is authoritative, read per request, unknown value fails closed to `authenticated`. `SA_AUTH_MODE` / `SA_DEMO_MODE` are consumed **only** when initializing an empty DB (first boot); later env flips are ignored with a warning. Runtime changes: `PATCH /api/v1/admin/instance` only (admin + current password re-verification, §4.5 transitions, audited `admin.instance_transition`) — `open → authenticated` sets credentials for the implicit owner; `authenticated → open` is refused on server entrypoints, needs explicit confirmation + the current password, is refused while other user rows exist, and revokes every session (+ `token_version` bump). `demo_mode` has **no** runtime API. A copied/restored DB keeps its mode, users, and settings (a restored authenticated backup stays authenticated — test kit §18.6); token keys are not in the DB, so a bare DB copy cannot mint tokens. The production container aborts if started with `SA_DEMO_MODE=true` unless `SA_APP_ENV=demo` (`docker/entrypoint.sh`). |
| Session storage | Cookies: `nx_access` (`__Host-nx_access` when `SA_COOKIE_SECURE=true`, i.e. TLS), `nx_refresh` (Path `/api/v1/auth`), `nx_csrf` (JS-readable). Access/refresh are HttpOnly + SameSite=Lax (+ `Secure` under TLS); access 60 min (24 h hard cap), refresh 7-day rolling / 30-day absolute, rotated on every use — replay of a rotated `jti` revokes the whole family + bumps `token_version` (423). CSRF: double-submit — non-GET must echo `nx_csrf` in `X-CSRF-Token` (403 on mismatch); no tokens in localStorage. Revocation paths: `POST /auth/logout` (one family), `/auth/logout-all` (+ `token_version` bump = global sign-out), `DELETE /api/v1/me/sessions/{id}`, admin `PATCH /users/{id}` + `POST /users/{id}/force-logout` (bump), `DELETE /api/v1/me` (cascade), and the `authenticated → open` transition (all sessions). Non-browser clients may send a Bearer refresh token to `/auth/refresh`; access tokens are verified from the cookie (and accepted as Bearer at dependency level, see known gaps). |
| Trust boundaries | **Shell ↔ backend (ADR-0010 shape):** study is not Electron — the pywebview window loads the same SPA over a random loopback port; every desktop request carries the per-boot `X-Shell-Token` (process-memory secret, rotates each boot), and `/api/v1/desktop/*` mounts only when `SA_IDENTITY_MODE=desktop`. **User ↔ agent tools (ADR-0011):** model output is untrusted input — chat tools are read-only or propose-first; state-changing actions reach the user as HITL proposal cards (ADR-0015 Class-B) applied only after explicit approval; the MCP resource server (`python -m studyassistant mcp`) is read-only stdio; deterministic validators (math equivalence chain, pydantic contracts, import validators) gate model output before it can affect grading, storage, or exports. **Client ↔ server:** cookie sessions + CSRF, deny-by-default CORS (`SA_CORS_ORIGINS` — no CORS headers unless listed), WS `Origin` + session gate, file browsing confined to granted roots (data dir + home + `SA_FS_ROOTS`; no HTTP grant endpoint). **Device ↔ integration API:** none — study has no machine/device credentials or inbound integrations (that transport class is health's); provider/search traffic is outbound-only with keys read from the keyring. |
| Data isolation | No tenants. Every domain row hangs off exactly one `(user, profile)`: `profile_id` UUID FKs with `ON DELETE CASCADE`, profile-scoped queries filter on `profile_id` everywhere. `X-Profile-Id` is ownership-bound per §15 — server: absent ⇒ 400, malformed/foreign/unowned ⇒ 403; desktop: falls back to the last-used profile; auth, `/me`, `/profiles`, `/admin`, health/docs are exempt so the SPA can always discover its profiles. Out-of-ownership domain resources answer a hidden **404** ("course not found") so existence never leaks; **403** is reserved for "authenticated but this binding is not allowed" (foreign profile header, admin-only routes); **401** means unauthenticated. |
| Secrets at rest | AI/search/MCP API keys live **only** in the OS keyring (`backend/app/core/secrets.py`, service `StudyAssistant`, legacy `CourseAssistant` copied forward) — never in DB columns, files, env blocks, or logs; responses mask them (`••••1234`). Token material is three independent per-instance keys (`nx_auth.keys.KeyRing`): `SA_SESSION_KEY` (signs session JWTs) / `SA_REFRESH_KEY` (signs refresh JWTs) / `SA_DATA_KEY` (Fernet, encrypts at rest — never signs), never derived from each other; stored env-first, else generated `auth_keys.json` at 0600 in the config dir. A disk thief with read access to the data dir **and** the config dir gets DB + blobs + signing keys (can forge sessions); keyring entries stay behind the OS login. Backup archives (in-app `backups/`, `pg_dump` sidecar, `scripts/backup.sh`) contain DB + blobs but never keyring entries or `auth_keys.json`. |
| Audit | `audit_events` (append-only) via the kit's audit sink covers the identity/admin surface: `auth.register`, `auth.login` (ok/denied), `auth.refresh` (incl. `reuse-denied`), `auth.logout`, `auth.logout_all`, `auth.demo_login`, `auth.session_revoke`, `auth.password_change`, `auth.account_delete`, `admin.user_update`, `admin.password_reset`, `admin.force_logout`, `admin.instance_transition` — actor, action, resource, outcome, timestamp. Domain reads/writes (materials, notes, chat) are **not** audited (that's health's §17 extension). No API endpoint edits or deletes audit rows; the trail can only be erased by direct database access or backup-retention expiry. |
| Admin surface | Server: the **first registered user becomes admin** (transactional first-row check in `StudyUserStore.create`, with Default profile) — on a fresh public deployment, register first or disable registration (`SA_REGISTRATION_ENABLED=false`) before exposing the port. Afterwards only admins promote/demote (`PATCH /api/v1/admin/users/{id}`; guard rails: no self-demotion/self-deactivation, no demoting the last admin, `token_version` bump on change). Desktop `open`: the implicit local owner (`owner@local`, password-less until `open → authenticated`) is the admin. Blast radius: reset any password, force-logout anyone, deactivate accounts, and flip instance `auth_mode` (with the admin's own password re-verification). |
| Deployment exposure | **Desktop:** `127.0.0.1` on a random port + per-boot shell secret; the OS user's data dir is the security boundary. **Web:** `docker-compose.standalone.yml` (db + app + nginx + optional `pg_dump` backup sidecar), `SA_HOST=0.0.0.0` behind nginx; the shipped `nginx.conf` is **HTTP-only** (loopback/VPN/dev) — internet-facing deployments must use `nginx-TLS.conf` (certbot ACME + HSTS) and set `SA_COOKIE_SECURE=true`; `SA_TRUSTED_PROXY_COUNT` must match the proxy chain or per-IP rate limits key on the proxy. **Datastore:** PostgreSQL 16 `neuro_study` with owner (migrations) / app (runtime) roles; backups are unencrypted `pg_dump -Fc` + data tars (`scripts/backup.sh`/`restore.sh`, restore drill in `docker/README.md`) — protect the backups directory like the database. **Demo:** `SA_DEMO_MODE` is init-only and admits one fixed credential-free `demo` principal via `POST /auth/demo` while enabled; the production entrypoint refuses demo configuration, and the demo stack (S8) is isolated and never production. |

Known gaps (documented, not papered over): the rate-limit ceilings are
install-time code defaults (`AuthConfig`) with no `SA_RATELIMIT_*` env
knobs yet; and the web Docker image ships no keyring backend (slim base,
no D-Bus), so BYOK key writes raise "no usable OS keyring backend" there
— keyless local providers work, keyed providers need a keyring backend
added to the image or the family's DB-config path implemented. (Closed
since the §20 pass: Bearer session access works on enforced routes —
kit §9; WS topics are owner-scoped per subscriber (ADR-0025-era
hardening); error details are sanitized before persist/emit.)

## AI-specific notes

The AI trust boundary is documented in the repository: model output is
untrusted input. Deterministic validators (math equivalence chain, prompt
contracts, import validators) gate everything the model produces before it can
affect grading, storage, or tool execution. Reportable issues include any path
where model output reaches deterministic grading, the tool sandbox, or file
exports without passing those gates. Provider keys are read from the OS
keyring only at the moment of an outbound gateway call (see
[docs/dev/security.md](docs/dev/security.md) and
[docs/dev/ai.md](docs/dev/ai.md)).

## Supported versions

The latest `main` and the most recent release tag receive security fixes.
