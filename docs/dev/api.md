# REST API

The backend exposes one versioned JSON API under `/api/v1`, plus a WebSocket at
`/ws`. **Every request is authenticated** (identity-auth ADR-0013, §4): browser
sessions ride the §10 cookie triple (`nx_access` / `nx_refresh` / `nx_csrf`)
with double-submit CSRF; non-browser clients may use
`Authorization: Bearer <session token>`. Unauthenticated calls ⇒ 401. The
identity surface itself is the family §12 API (`/api/v1/auth/*`,
`/api/v1/me/*`, `/api/v1/admin/*`, implemented by the auth kit) plus
`GET /api/v1/instance/config` (public: `{demo_mode, auth_mode,
registration_enabled}`). The frontend never talks to anything else; the typed
client in `frontend/src/lib/api/` is generated from this surface. See
[frontend.md](frontend.md) for the client side and [jobs.md](jobs.md) for
background work.

## Shape

- **Base path:** `/api/v1`. Interactive docs are served at `/api/docs` only when
  `SA_DEBUG=1`.
- **App factory:** `backend/app/main.py` builds the app, runs migrations, seeds
  the default profile and task registry, and includes `api_router`.
- **Router map:** `backend/app/api/router.py` registers the area routers in
  order. The areas are:

| Area | Router(s) | Covers |
|---|---|---|
| System | `health`, `config`, `desktop` | Health, app config, desktop-shell helpers |
| Jobs | `jobs` | List/summary, retry, retry-failed |
| Materials | `materials`, `blobs_router` | Upload, detail, extraction versions, drawings, blob serving |
| Search | `search` | Hybrid search hits with node placements |
| Discovery | `discovery`, `external_sources`, `mcp_servers` | Provider search, external sources, MCP connectors |
| Library | `folders`, `sources`, `fs` | Folders, linked sources, filesystem browsing |
| Courses | `courses` | Courses, tree nodes, tree operations |
| Chat | `chat` | Sessions, turns, proposals, tools |
| Study | `quiz`, `review`, `exercises`, `notes`, `flashcards`, `study`, `study_sessions` | Quizzes, review, exercises, notes, cards, Study-now, sessions |
| Analytics | `analytics`, `notifications` | Scores, metrics, notification aggregate |
| Data | `backup`, `trash`, `profiles` | Backups, trash/restore, profiles |
| Planner | `plan` | Plan items and the upcoming view |
| AI | `ai`, `ai_settings`, `skills` | Tools catalog, providers/models/tasks, skills |
| Onboarding | `onboarding` | First-run state |

DTOs are Pydantic models; shared schemas live in `api/schemas.py` and
`api/courses_schemas.py`, area-specific shapes in their router module.

## Profile scoping

Every domain call is bound to a **profile owned by the session user**
(identity-auth §15, `ProfileBindingMiddleware`): `x-profile-id` must
reference an owned profile — **absent ⇒ 400, malformed/unknown/foreign ⇒ 403**
(server mode); desktop falls back to the last-used profile. Profile
scoping is a data partition; the ownership check **is** part of
authorization — see [security.md](security.md).

### Identity & account surface (§12, family contract)

`/api/v1/auth/*` (register — first user becomes admin —, login, refresh
with rotation + reuse detection, logout/-all, me, desktop exchange in
`open` desktop mode), `GET|DELETE /me/sessions`, `PATCH /me/password`,
`DELETE /me`, `/api/v1/profiles` CRUD (1:N per user, Default
auto-provisioned), `GET|PATCH /api/v1/admin/users*` (guard rails), and
`GET /api/v1/instance/config`. MFA (TOTP) is available via the kit's
extension point; see [security.md](security.md) for the threat model.

## Errors

Errors are standard FastAPI `HTTPException`s with a `detail`:

- `422` — validation failure (bad payload, unparseable import, invalid
  vocabulary value). Some endpoints return a structured detail object; the BYOK
  setup endpoint returns `{code, suspected_vendor, detail}` and persists nothing
  on a classified failure.
- `404` — missing entity (or missing profile).
- `409` — conflict (for example cross-provider default assignment).
- `502` — an upstream provider or fetch failed; the error text is passed
  through and, where applicable, recorded on the row.

Handlers translate domain exceptions to these codes; keep new endpoints
consistent with the surrounding router.

## Pagination

List endpoints take an explicit `limit` (bounded, for example `Query(default=50,
ge=1, le=100)`) and either an offset or an id cursor. The chat proposals list
uses an id cursor; most library/course lists return the full scoped set. Prefer
a bounded `limit` for any new list endpoint and document the ordering.

## WebSocket

`/ws` (see `api/ws.py`) uses subscribe/unsubscribe/publish/ping frames. The
backend `EventBus` bridges worker threads to subscribers via
`publish_threadsafe`, and topics are built by `WsTopic` factories in
`core/vocab.py` (`jobs:{id}`, `chat:{id}`, `source:{id}`, `externalsource:{id}`,
`note:{id}`). The frontend mirrors these builders in `lib/constants.ts`. Job and
chat progress stream over these topics.

## OpenAPI and generated types

The contract is generated, not written by hand:

```bash
pnpm api:types
```

This runs `scripts/export-openapi.py` (which boots the app against a temp data
dir and writes `frontend/openapi.json`) and then `openapi-typescript` to produce
`frontend/src/lib/api-schema.d.ts`. Commit both; CI drift-guards them. Never
hand-edit either file — change the Pydantic model instead.

## Adding an endpoint

1. Add the handler to the right area router and the DTOs beside it.
2. Wire the router into `api/router.py` if it is a new area.
3. Run `pnpm api:types` and commit the schema + types.
4. Add a backend test with the `client` fixture (see [testing.md](testing.md)).
5. Update this page's router map and `docs/STATUS.md` in the same commit.
