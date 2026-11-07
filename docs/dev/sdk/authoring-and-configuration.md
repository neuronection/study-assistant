# Authoring & configuration

The reference for every config shape the extension surface accepts.
Nothing here is a plugin API — you configure instances of the bundled
connectors and write external MCP servers against two small wire
contracts. Every table below is the validation code's actual law
(`backend/app/extensions/mcp_servers.py`, `search/provider.py`,
`search/providers_contract.py`, the bundled manifests).

## 1. The MCP registration shape

`POST /api/v1/mcp/servers` (the connector card's add dialog):

| Field | Type / bounds | Default | Notes |
|---|---|---|---|
| `name` | string, 1–80 chars | — | required; the provider prefix `mcp.<name>.<tool>` |
| `transport` | `stdio` \| `http` \| `sse` | `stdio` | `http` = Streamable HTTP |
| `command` | string ≤ 500 | — | **required for stdio**; ignored for remote transports |
| `args` | list ≤ 20 items, each ≤ 500 chars | `[]` | argv for stdio |
| `url` | string ≤ 500, `http(s)://` | — | **required for `http`/`sse`**; anything else is a 422 |
| `token` | string | — | bearer token for remote transports; sealed `mcp:<id>:token`, never returned (surfaces as `has_token`) |
| `env` | object of string → string | — | stdio process environment overlay; sealed `mcp:<id>:env` as JSON |
| `timeout_sec` | int 5–120 | 30 | per-call MCP timeout |
| `max_concurrent` | int 1–8 | 4 | concurrent-call cap per server; over-cap calls fail `busy`, they never queue |

Transport rules, exactly as enforced: `stdio` keeps `command` and drops
`url`; `http`/`sse` require an http(s) `url` and drop `command`. A
profile may hold at most **10 servers**. Servers launch lazily per call
and are reaped when it ends — no resident process fleet; remote
transports send the sealed token as `Authorization: Bearer …`, stdio
servers get the minimal default environment plus your `env` map.

`PATCH /api/v1/mcp/servers/{id}` updates any of the above (patching
`token`/`env` re-seals; `token: null` clears the slot) plus the tool
rows; unknown tool names 422 with "refresh first".

## 2. Per-tool contracts and url_patterns

Refresh (`POST …/{id}/refresh`) lists tools; each tool row is
`{name ≤120, description ≤300, enabled, contract, url_pattern}`. You
then assign each tool exactly one contract:

| Contract | The app calls it with | Its output must be | It feeds |
|---|---|---|---|
| `none` (default) | — (never called by a pipeline) | — | nothing; listed for your bookkeeping |
| `discovery` | `{"query": str}` | JSON text: a list (or `{"results": [...]}`) of rows — `title` (required, ≤300), `url` (required, http(s), ≤2048), `kind` (`video` \| `course` \| `article` \| `exercise` \| `other`), `description` (≤800) | DISCOVER (chat tool + Discover dialog), capped at the request cap |
| `parse` | `{"url": str}` | JSON object: `title` (≤300), `markdown` (required, non-empty), optional `metadata` object | Import & parse, like a built-in parser |

Validation is app-side and strict: a bad row is dropped with a logged
warning (discovery) or the whole result refused (parse — non-JSON, no
markdown, and shape violations are hard `ParserError`s). Invalid kind
values fall back to `other` rather than failing the batch.

**`url_pattern`** (parse tools, required in practice): an
[`fnmatch`](https://docs.python.org/3/library/fnmatch.html) pattern
matched against `host + path` (lowercased host, query string excluded)
— e.g. `coursehub.example/learn/*` matches
`https://coursehub.example/learn/42?ref=x`. MCP parse tools register
**ahead of** built-in parsers, so a matching pattern wins for its site.
Keep the pattern tight: everything it matches routes through your
external process.

## 3. The web-search provider config

`Profile.preferences["search_providers"]` rows, edited through
Settings → Tools → Web search (the catalog-driven panel; one
description of every provider lives in
`extensions/search/providers_catalog.json`, the vendored family
catalog):

| Field | Type / bounds | Default | Notes |
|---|---|---|---|
| `type` | `searxng` \| `tavily` \| `brave` \| `exa` \| `serper` \| `google-pse` | — | required; anything else is `unknown_type` |
| `name` | string | the type label | display only |
| `enabled` | bool | `true` | disabled rows are skipped by fallback |
| `base_url` | http(s) URL | the hosted default per type | **required for `searxng`** (self-hosted); trailing `/` stripped |
| `google_cx` | string | — | required for `google-pse` (the engine id) |
| `timeout_ms` | int 500–30000 | 8000 | clamped, not rejected |
| `max_results` | int 1–10 | 5 | clamped |
| `key_hint` | string | — | masked tail (`••••1234`), display only |

API keys never appear in these rows: the panel sends `api_key`
separately and the backend seals it into the keyring slot
`search:<provider id>` (absent keeps the stored key, empty string
clears it, a value stores it — desktop-parity semantics). SearXNG is
the only keyless type and needs its instance's JSON format enabled
(`settings.yml: search.formats: [json]`).

**Fallback law:** providers are an ordered list; the first *enabled*
provider that answers wins. If every enabled provider fails, the last
error surfaces (as kind `unreachable`, so chat-side callers skip
cleanly). Reordering is a first-class operation (move up/down).

## 4. External-source kinds and the envelope manifest

Web sources are instances of the bundled `external-sources` connector,
configured per source (Settings → Tools → Web sources):

| Field | Type / bounds | Default | Notes |
|---|---|---|---|
| `kind` | `rss` \| `youtube_channel` \| `youtube_playlist` \| `site_search` | — | required |
| `url` | string 1–2048 | — | the feed/channel/playlist URL; for `site_search`, the site to filter |
| `label` | string ≤ 200 | derived | display |
| `enabled` | bool | — | per-source toggle |
| `scan_interval_sec` | int ≥ 900 | 21600 | the politeness floor is enforced |

The bundled manifest (`backend/app/extensions/builtin/
external_sources/manifest.json`) is the envelope reference for this
connector: its `itemSchema` documents the suggestion row exactly as the
scan legs produce it — `provider` (`rss:label` | `youtube:kind` |
`site:domain`), HTML-stripped `title`, http(s)-validated `url`, a
discovery-vocabulary `kind`, a `snippet` capped at 2000 chars, and a
RFC3339 `published` when the source declares one. Fetch metadata is
untrusted input: titles are stripped, URLs re-validated before upsert,
errors isolate per source into `last_scan_error` (surfaced on the row,
published on WS `externalsource:{id}`), and an overlap guard prevents
stacked scans of one source.

Writing a **new bundled connector** (a contributor act, not a user
act): one directory under `builtin/` with its `manifest.json` —
`apiVersion: extension/v1`, `kind: connector`, an id that matches the
directory slot, capabilities ⊆ the study host profile's `honors`, a
`configSchema` (`x-secret: true` on credential fields), an
`itemSchema` for its rows, i18n labels. Registration validates it
against the vendored envelope schema and throws on drift. External
code, by contrast, never lands here — it is T3 by shape.
