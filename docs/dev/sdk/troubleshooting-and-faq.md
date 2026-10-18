# Troubleshooting & FAQ — developer diagnostics

The user-facing half of this chapter is
[Extension troubleshooting](../../user/extension-troubleshooting.md);
this page decodes every failure mode the suite walls test, plus the
questions authors actually ask.

## Symptom → cause → fix

| Symptom | Cause | Fix |
|---|---|---|
| Refresh returns 502, `last_error` set, status `degraded` | the spawn failed — command not found, interpreter without deps, server crashed at boot | run the registered command yourself in a shell; fix the venv/path; refresh again (the row kept your settings) |
| Refresh lists tools but every call times out | `timeout_sec` below the tool's real latency, or the server hangs on calls | raise `timeout_sec` (≤120); test the tool outside the app; a genuinely hung process is reaped per call — nothing queues |
| `discovery/search` returns fewer rows than the server sent | app-side validation dropped rows (empty title, non-http(s) url, non-dict row) | it is working as designed — check the server log (`mcp_discovery_invalid_row`); fix the rows your tool returns |
| `MCP tool … returned non-JSON output` | discovery/parse contract violation | return `json.dumps(...)` text exactly once; no prose around the JSON |
| `… returned no markdown` / `must return an object with title and markdown` | parse contract violation | the object needs non-empty `markdown`; `title` may be empty (capped at 300 when present) |
| Import routed to the built-in parser instead of your tool | `url_pattern` didn't match (host+path, lowercased host, query excluded) | test the pattern with `fnmatch("coursehub.example/learn/42", pattern)` semantics; re-declare on the tool row |
| Import routed to your tool for URLs you didn't intend | parse tools order ahead of built-ins; pattern too broad | tighten the pattern (`site.example/learn/*`, not `site.example/*`) |
| Search probe: `SearXNG returned HTML — enable the json format` | the instance's JSON format is off | `settings.yml: search.formats: [json]` on the instance, then re-probe |
| Search probe: `… needs an API key` (`missing_key`) | key absent for a keyed type | enter the key in the panel (keyring slot `search:<id>`); absent key ≠ empty key |
| Search probe: `auth` (401/403) | wrong or expired key, wrong vendor | re-paste the key; check the provider console |
| Search probe: `rate_limit` (429) | quota/quota window | wait `retry_after_ms` when present; lower `max_results`; check plan limits |
| Web search returns nothing, `errors: []` | every enabled provider failed → surfaced as `unreachable`, chat skips | check the first enabled provider's probe; reorder; `search_with_fallback` raises the last error — the log has it |
| `unknown tool '<name>' — refresh first` on PATCH | the tool list changed since your last refresh | refresh, then patch against the fresh list |
| `unknown contract '…'` / `unknown transport '…'` (422) | closed vocabularies | contracts are `none|discovery|parse`; transports `stdio|http|sse` |
| `at most 10 servers can be registered` | per-profile cap | delete a server you no longer use (its keyring slots go with it) |
| `MCP server '<name>' is busy — max N concurrent call(s)` | over `max_concurrent` | raise it (≤8) or stop issuing parallel calls; over-cap fails, never queues |
| Source row shows `last_scan_error` | one feed/channel failing (dead URL, extractor rot) | per-source isolation — fix or disable that source; others keep scanning |
| `conditions: ["needs-config"]` on a row | stored config no longer satisfies transport rules (stdio without command, remote without url) | re-save the server with the required field |

## FAQ

**Is my server's code ever uploaded or copied?** No. Study spawns what
you pointed at, on your machine; nothing about your code leaves it.
What leaves the machine is whatever *your server* fetches/calls on its
own — see the disclosure.

**Do MCP tools get model context or my notes?** No. Discovery tools
receive `{"query": …}` and parse tools `{"url": …}` — one argument,
nothing else. The app treats their output as untrusted data.

**Can a connector write into my courses?** No. The only path from a
connector to your library is a suggestion you keep, or an import you
started. Proposals in chat are the same law one level up (approval is
the only write path).

**Why did my tool disappear after refresh?** Refresh replaces the tool
list with what the server reports now; settings for tools that persist
by name are kept, gone tools drop. Renaming a tool in your server
resets its enable/contract state.

**Providers vs sources vs MCP — which one do I need?** Zero-code
first: a search provider (chat research + discovery web channel), then
a source (scheduled suggestions from a feed/channel), and an MCP server
only when you need code running outside the app (custom source,
site-specific parsing). The [recipes](examples-and-use-cases.md) pick
per situation.

**Where do I see what was called?** The Tools tab surfaces per-server
health; every call is one `ai_interactions` row (`task=mcp_tool_call`)
with latency and ok/error — the same funnel as AI calls.

**Is the keyring shared between profiles?** Slots are keyed by server
id / provider id — instances are per-profile, but the keyring is per
*machine*: deleting the instance deletes its slots; the same server id
cannot exist twice, so cross-profile collisions cannot happen.

**Web vs desktop — same connectors?** Yes: same endpoints, same
validation, per-profile scoping (`X-Profile-Id`). Desktop additionally
allows stdio spawns as your local user; server mode runs them as the
backend service user — mind the paths and venvs in registered commands.
