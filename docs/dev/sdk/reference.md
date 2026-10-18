# Reference

Tables, not prose: the vendored trio's API surface, the error taxonomy
and its charter projection, the tool-contract and status vocabularies,
the endpoints, and the limits.

## The vendored trio's API surface (`extensions/search/providers_contract.py`)

Pure functions over plain dicts; httpx is the only dependency and the
transport is injectable (`transport=` on every entry point — how the
suite runs it network-free). Canonical: `dev/contracts/
search_providers.py`, byte-identical here via the sync script.

| Symbol | What it does |
|---|---|
| `PROVIDER_TYPES` | `("searxng", "tavily", "brave", "exa", "serper", "google-pse")` |
| `normalize_provider_config(raw)` | validate + clamp one config row (raises `SearchError`); drops unknown keys |
| `perform_search(config, query, *, api_key, transport, limit)` | one search against one provider → normalized hits |
| `probe_provider(config, *, api_key, transport)` | one benign search → `{status, latency_ms, result_count, error}` for the connection-test row |
| `provider_catalog_summary()` | types + base-URL rules + defaults without the JSON catalog |
| `SearchError` | the one error type: `.kind` (taxonomy below), `.message`, `.http_status` |
| normalized hit | `{"title", "url", "content"}` — title falls back to the url, content caps at 800 chars |

App-side policy (`search/provider.py` — the ADR-0031 local half):
persistence in `Profile.preferences["search_providers"]`, keyring slots
`search:<id>`, the ordered-fallback `search_with_fallback*` (first
enabled that answers wins; all failing raises the last error as
`unreachable`), `perform_fetch` (http(s)-only FETCH with HTML→markdown,
capped), and the lazy migration from the pre-plan-28 single-provider
preference.

## The error taxonomy and its charter projection

The vendored `SearchError.kind` vocabulary (wire law, desktop's TS
adapters implement the same cases) and its D4 projection onto the
charter's 15-code model (`extensions/errors.py`) — the one-time
re-authoring recorded in the charter's `legacyMappingNote`:

| `SearchError.kind` | charter `ExtensionError.code` | retryable |
|---|---|---|
| `missing_key` | `needs-secret` | `after-config-change` |
| `missing_config` | `invalid` | default |
| `unknown_type` | `invalid` | default |
| `bad_request` | `invalid` | default |
| `auth` | `auth` | `after-config-change` |
| `rate_limit` | `rate-limited` | `after-delay` |
| `unreachable` | `unreachable` | default |
| `json_disabled` | `protocol` | `after-config-change` |
| `protocol` | `protocol` | default |

The charter codes (closed set, `polite_http.ERROR_CODES`):
`not-ready · needs-secret · invalid · unsupported · io · not-found ·
path-denied · net-denied · auth · rate-limited · unreachable ·
protocol · provider · budget · canceled`, with the closed `retryable`
sub-enum `yes · no · after-delay · after-config-change` and optional
`retry_after_ms` (429 payloads) + upstream `status`.

## The tool-contract vocabulary

| Value | Call shape | Output shape | Feeds |
|---|---|---|---|
| `none` | — | — | listed only |
| `discovery` | `{"query": str}` | JSON list or `{"results": [...]}`: `title` ≤300 · `url` http(s) ≤2048 · `kind` ∈ `video`/`course`/`article`/`exercise`/`other` · `description` ≤800 | DISCOVER |
| `parse` | `{"url": str}` | JSON object: `title` ≤300 · `markdown` (non-empty) · `metadata?` object | Import & parse (url_import job) |

`url_pattern`: fnmatch over lowercased `host + path` (query excluded),
≤300 chars; parse tools order ahead of built-in parsers.

## The instance-status vocabulary (D7/D21)

`GET /api/v1/mcp/servers` rows carry the family surface, derived from
the preference row without a migration:

| Field | Values / meaning |
|---|---|
| `status` | `ok` · `degraded` (last refresh failed) · `failing` (reserved — study does not yet track consecutive failures) · `stale` (no successful refresh within 24 h) |
| `last_success_at` | RFC3339 of the last successful refresh |
| `consecutive_failures` | 0, or 1 while `last_error` is set |
| `conditions` | `["needs-config"]` when the stored config no longer satisfies the transport rules (stdio without command, remote without url) |

## Endpoints

| Route | Purpose |
|---|---|
| `GET /api/v1/mcp/servers` | list instances + status surface + `declared_contracts` |
| `POST /api/v1/mcp/servers` | create (disabled; validates transport rules + bounds) |
| `PATCH /api/v1/mcp/servers/{id}` | update config, enable/disable, per-tool `enabled`/`contract`/`url_pattern` |
| `DELETE /api/v1/mcp/servers/{id}` | remove row + keyring slots |
| `POST /api/v1/mcp/servers/{id}/refresh` | spawn + list tools (explicit; never auto-enables) |
| `GET /api/v1/mcp/charter` | the T3 perimeter disclosure verbatim + the mcp connector's capabilities |
| `POST /api/v1/discovery/search` | run DISCOVER (`query`, optional `providers` filter by provider id) |

Errors surface the charter typed model (`ExtensionError` → HTTP 422
`invalid`, 502 on spawn/tool failures with `last_error` recorded).

## Limits

| Limit | Value |
|---|---|
| servers per profile | 10 |
| server name / tool name / tool description | 80 / 120 / 300 chars |
| command / url / arg / url_pattern | 500 / 500 / 500 (≤20 args) / 300 chars |
| `timeout_sec` / `max_concurrent` | 5–120 (default 30) / 1–8 (default 4) |
| search `timeout_ms` / `max_results` | 500–30000 (default 8000) / 1–10 (default 5) |
| search hit `content` cap | 800 chars |
| discovery row `description` cap · result cap | 800 chars · request cap (rows scanned: 2× cap) |
| parse `title` / source `snippet` | 300 / 2000 chars |
| external-source scan interval | ≥ 900 s (default 6 h) |
| FETCH content cap | 4000 chars |

## Where the audit lands

`ai_interactions`: `context_type="mcp"`, `task="mcp_tool_call"`,
`model="mcp.<server>.<tool>"`, latency and ok/error per call — written
by both the discovery leg and the parse leg, from the same
`audit_mcp_invocation` helper.
