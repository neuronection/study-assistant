# Core concepts

Every noun the rest of this set uses, defined once. The vocabulary is
family law (the extension charter); study implements it as a
**connector-kind host at tiers T0/T1/T3** — vendored contracts (T0),
bundled connectors (T1), and external MCP server processes (T3). There
is no in-process plugin tier, by charter.

## The nouns

**Extension** — a declared artifact: a validated `extension/v1` envelope
manifest (`apiVersion`, `kind`, `id`, `version`, `capabilities`,
`configSchema` with `x-secret` marking, i18n labels, an `itemSchema`
describing its rows). In study, all extensions are kind `connector`.
Bundled ones live one directory per id under
`backend/app/extensions/builtin/` and validate **at registration** — a
manifest the study host profile does not honor throws, never
half-runs.

**Capability** — the closed charter taxonomy of what an extension may
do. The registry answers "can it do X?" only from declared manifest
data (`registry.has_capability`); what the study host implements comes
from the charter's study host profile (`honors`), not a hand-written
copy. Today's bundled declarations: `external-sources` → `sync`,
`discovery` → `chat-tools`, `mcp` → `secrets`.

**Instance** — one configured, enable-able row of an extension. Every
registered MCP server is one instance of the bundled `mcp` connector
(the D19 model): its own transport config and its own lifecycle
(disabled at creation → explicit refresh → per-tool enablement), stored
as a `mcp.servers` preference row on the profile. External web sources
are instances of `external-sources` (`external_sources` table rows).

**Tool contract** — what a registered MCP tool is *for*, declared per
tool by you, the user: `none` (default — listed but never called by a
pipeline), `discovery` (feeds DISCOVER), or `parse` (imports one URL
inside Import & parse). The contract is the whole integration surface —
study calls the tool with one argument shape and validates the output
against one row shape (the [Authoring](authoring-and-configuration.md)
tables).

**Provider** — a discovery channel resolved per search: the built-ins
(`web` over the ADR-0035 trio, `youtube` over yt-dlp flat search),
site-filtered presets (`site:<domain>`), and one per enabled
discovery-contract MCP tool (`mcp.<server>.<tool>`). Providers return
normalized rows; they are never persisted as materials.

**Source** — a standing external feed polled on a schedule (an
`external-sources` instance: RSS/Atom, YouTube channel/playlist,
site-filtered search). Every new item lands as a **suggestion** —
suggestions-never-auto-import is the invariant: a human keeps,
imports, or dismisses every row.

**Suggestion** — a `suggested` row in the Discover funnel
(`material_suggestions`, deduped on a normalized URL). Discovery
results and scanned source items both land here; importing one rides
the normal parse pipeline.

**Consent** — the T3 perimeter disclosure (charter
`t3PerimeterDisclosure`, rendered verbatim on the connector card and at
`GET /api/v1/mcp/charter`): an external server runs as a separate
process outside the app's network perimeter. Enabling a server is the
consent act; the disclosure text is data, not copy.

**Sealed secret** — a credential that never enters the database or a
file: provider API keys (`search:<id>` slots) and MCP tokens/env maps
(`mcp:<id>:token` / `mcp:<id>:env`) live in the OS keyring, sealed
at-rest by the family cipher (`SA_DATA_KEY`, ADR-0027). Stored rows
carry only `has_token`/`key_set` booleans and masked hints.

## The diagram

```text
                ┌─────────────────────────────────────────────────┐
                │              Study Assistant (app)              │
                │                                                 │
  chat tools ───▶ DISCOVER (bundled `discovery` connector)        │
  Discover UI ─▶   │  providers: web · youtube · site:<d> · mcp.* │
                │   │            each row validated + capped       │
                │   ▼                                            │
                │  suggestions ── never auto-imported ──▶ you     │
                │                                                 │
  Import&parse ▶ parser registry (ordered, first match wins)       │
                │   ▲ MCP parse-contract tools (url_pattern-keyed) │
                │                                                 │
                │  registry: declared capabilities gate everything │
                │  secrets: OS keyring (sealed) · audit: 1 row/call│
                └───────┬─────────────────────────┬───────────────┘
                        │ stdio/http/sse          │ schedule
                        ▼                         ▼
              T3 MCP server (your code)   external sources (rss/yt/site)
              outside the app perimeter   bundled fetch legs, untrusted input
```

Two seams in, one rule over both: **external output is untrusted
input** (the family AI trust boundary) — every row is validated and
capped app-side before it touches a suggestion, a parser result, or a
chat.

## The vendored-contract discipline

Three artifact families in this subsystem are byte-identical copies of
dev-repo canonicals, never edited in place (ADR-0031 sync-and-gate):

- the **charter set** (`contracts/extension-charter.json`, the manifest
  schema, fixtures, the Python validators in `extensions/`) — synced by
  `dev/scripts/sync-extension-contract.sh`, drift-walled by
  `verify-wiring.sh`;
- the **ADR-0035 web-search trio** (`extensions/search/
  providers_contract.py` + its fixtures and catalog) — synced by
  `dev/scripts/sync-search-providers.sh`, with desktop's TS adapters as
  the reference implementation of the same wire contract;
- the **docs-tree contract** (`contracts/docs-tree.schema.json` +
  fixtures) — the validated shape of this set's own navigation tree.

The practical consequence for an author: vocabularies you consume
(error kinds, statuses, provider types) change family-wide via the dev
canonical or not at all — see
[Versioning & Migration](versioning-and-migration.md).
