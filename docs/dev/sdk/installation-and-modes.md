# Installation & modes — internals

The user-facing half of this chapter is
[Add an MCP connector](../../user/add-an-mcp-connector.md) (plus
[Add a search provider](../../user/add-a-search-provider.md) and
[Manage web sources](../../user/manage-web-sources.md)); this page
covers what those flows do underneath: the modes a host runs in, where
artifacts live on disk, and the bundled-catalog steady state.

## Modes × artifacts

Study is a **dual-mode product** — the same backend serves both:

| Mode | Identity | Datastore | Extension surface |
|---|---|---|---|
| Desktop (`pnpm app`, pywebview) | `auth_mode=open` — implicit local owner + Default profile, zero auth UI | SQLite (`study.sqlite3`) under the working directory | The full Tools tab; stdio spawns run as your user |
| Web/server (browser, `pnpm webapp`) | Authenticated, user management | PostgreSQL 16 | Same surface; `X-Profile-Id` scopes every instance to the session user's profile |

Instances are **per-profile** config, not machine config: MCP servers
live in `Profile.preferences["mcp"]["servers"]`, web-search providers in
`Profile.preferences["search_providers"]`, discovery toggles in
`preferences["discovery"]`. Two profiles on one machine have entirely
separate connector sets. External web sources are profile-owned rows in
the `external_sources` table and ride `sa-course/v2` course bundles on
export/import.

## Where things live on disk

| Artifact | Location |
|---|---|
| Database (desktop) | `<working directory>/study.sqlite3` (WAL) |
| The working directory | user-visible and changeable — pointer file in the platform config dir (`Settings → Data`); `SA_CONFIG_DIR` overrides for tests/packaging |
| Sealed secrets | OS keyring services under the app identity, sealed at-rest via `SA_DATA_KEY` (Fernet); **never** the DB, a file, or env blocks |
| Bundled manifests | in-repo: `backend/app/extensions/builtin/<id>/manifest.json` — no runtime copy |
| Vendored contracts | repo-root `contracts/` + the `extensions/` modules (byte-identical dev canonicals) |
| Audit rows | `ai_interactions` (`task = mcp_tool_call`, one per MCP tool call, latency + ok/error) |

There is no per-extension content directory today: bundled extensions
are in-repo reviewed code, and T3 servers run from wherever **you**
pointed their command (a cloned git checkout, a venv script, a packaged
binary — the app never copies or manages them).

## The bundled-catalog steady state

Study's steady state is **bundled-only, user-configured**: the three
bundled connectors ship with the app and register at boot; what varies
per user is *instances* (servers, provider rows, source rows) — added
through the Tools tab surfaces, never by dropping files into a
directory. The settings surfaces follow the family settings map
(`tools.*` domains live in the Tools tab: `tools.web-search`,
`tools.discovery`, `tools.web-sources`, `tools.connectors`).

The instance lifecycle, end to end:

1. **Create (disabled)** — `POST /api/v1/mcp/servers` validates the
   shape (transport rules, limits from the
   [Authoring tables](authoring-and-configuration.md)), stores the row
   with `enabled: false`, seals token/env into the keyring.
2. **Refresh (explicit)** — `POST …/{id}/refresh` spawns the server,
   MCP-handshakes, lists tools; every tool lands disabled with contract
   `none`. A failed refresh records `last_error` on the row (status
   `degraded`) — honest, visible, retryable.
3. **Enable (per tool)** — `PATCH …/{id}` sets `enabled` on the server
   and per-tool `enabled` + `contract` (+ `url_pattern` for parse).
   Nothing auto-enables, ever.
4. **Run** — pipelines call only enabled tools with a declared
   contract, one audit row per call; results validated and capped.
5. **Delete** — `DELETE …/{id}` removes the row and its keyring slots.

Web-search providers and web sources follow the same create/list/scan
shape without the spawn step (providers are pure config + keyring;
sources are scanned rows in the scheduler).
