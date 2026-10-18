# Examples & use cases — five recipes

Every recipe carries the four-part frame: **when to use**, **when NOT
to use**, **complete code**, **what to be careful at**. Runnable cores
are pinned by the suite (each recipe names its wall); where a transcript
exists it is in the [Quickstart](quickstart.md).

## Recipe 1 — an MCP discovery tool (the family template)

**When to use.** You want a source — a course hub, an internal search
API, a library catalogue — to surface in the Discover dialog and behind
chat DISCOVER, without touching the app. Clone the family template
([`career-connector-template`](https://github.com/neuronection/career-connector-template)),
keep its `server.py` shape, swap the tool for one speaking study's
discovery contract.

**When NOT to use.** Don't build one for a site that is already
searchable via the web-search providers — a `site:`-filtered preset or
a site-search source covers it with zero code (see recipes 3–4). Don't
use the discovery contract to push data *into* the library — discovery
rows are suggestions only; for importing whole pages you want recipe 2.

**Complete code.** The quickstart's server — the template's `server.py`
with its tool swapped — is the whole thing (see
[Quickstart step 1](quickstart.md#1-the-server-the-family-template-tool-swapped));
the dependency-free twin in the repo is
`backend/tests/fixtures/mcp_discovery_server.py`. Register → refresh →
declare `discovery` → search, exactly as the quickstart shows.

**What to be careful at.** The contract is validated, not trusted:
rows without a title or with a non-http(s) URL are silently dropped
(logged `mcp_discovery_invalid_row`) — watch the server log when a
result count looks wrong. `kind` must be one of the five discovery
kinds or it falls back to `other`. Your process runs outside the app's
perimeter (T3) and opens its own connections — the
[disclosure](security-and-gotchas.md) applies verbatim. One audit row
lands per call; queries are user-initiated, so cost/quota is your
server's own bill.

## Recipe 2 — a parse-contract parser for one site

**When to use.** A site you import from repeatedly (a course platform's
lesson pages) whose pages the built-in HTML parser handles badly — one
MCP tool keyed by URL pattern can render the page however that site
needs (its own scraper, a readability pass, a headless browser you
operate).

**When NOT to use.** For a one-off URL, plain Import & parse is
better — no server, no contract. For PDFs/DOCX/EPUB, the built-in
parsers already run; a parse tool never sees those URLs (patterns match
http(s) only). Don't use a parse tool to bypass upload guards — output
caps and validation still apply app-side.

**Complete code.** Same server shape as recipe 1, tool swapped for the
parse contract (`{"url": str}` → `{title, markdown, metadata?}`):

```python
from __future__ import annotations

import json

from fastmcp import FastMCP

mcp = FastMCP("coursehub")


@mcp.tool
def fetch_lesson(url: str) -> str:
    """Return one lesson page as markdown (the parse contract)."""
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    return json.dumps(
        {
            "title": f"Lesson {slug.replace('-', ' ').title()}",
            "markdown": f"# Lesson {slug}\n\nRendered by your site-specific parser.",
            "metadata": {"level": "intro"},
        }
    )


if __name__ == "__main__":
    mcp.run()
```

Register it, refresh, then declare the tool with `contract: "parse"`
and a `url_pattern` like `coursehub.example/learn/*`. Importing
`https://coursehub.example/learn/42?ref=x` now routes through the tool
(the pattern matched `coursehub.example/learn/42`), lands as a normal
parsed material with `metadata.mcp_tool = mcp.<server>.<tool>`, and the
import runs inside the standard url_import job.

The wire shapes and routing are walled by
`backend/tests/test_mcp_connectors.py`:
`test_mcp_parse_parser_matches_and_validates_contract` (pattern
matching, markdown-required, metadata merge),
`test_parse_contract_lands_in_url_import` (a full import through the
job), and `test_mcp_parse_parser_rejects_contract_violations`
(non-JSON, no-markdown refusals).

**What to be careful at.** MCP parse tools register *ahead of*
built-in parsers — a greedy pattern silently captures URLs you meant
for the built-ins. Non-JSON output or missing markdown is a hard
refusal (the import fails honestly, never a half-parsed material).
`metadata` is merged into the material row — keep it small and
string-valued.

## Recipe 3 — a web-search provider via the catalog (Tavily, SearXNG)

**When to use.** Chat research (SEARCH/FETCH), discovery's web channel
and site presets all need a search backend; you add one from the
six-type catalog — no code, pure configuration.

**When NOT to use.** Don't add a provider *and* an MCP discovery tool
for the same source — the provider (with a site preset or a site-search
source) is the zero-code path. Don't reach for this to search *your own
library* — that is the app's hybrid retrieval, unrelated to web search.

**Complete code.** No code — the catalog *is* the recipe (the vendored
`providers_catalog.json` drives the panel's fields per type). The two
canonical walks:

- **Tavily** (any hosted key type — Brave, Exa, Serper work the same):
  Settings → Tools → Web search → Add → type `tavily`; paste the API
  key (it goes straight to the keyring — the row only ever shows
  `••••1234`); probe runs one benign search and shows latency + result
  count. `base_url` is optional (hosted default); a Tavily-compatible
  endpoint overrides it.
- **SearXNG** (self-hosted, keyless): type `searxng`, set `base_url`
  to your instance (required — there is no hosted default), no key.
  If the probe answers `json_disabled`, enable the instance's JSON
  format (`settings.yml: search.formats: [json]`) — the error message
  says exactly this.

Order matters: the first enabled provider that answers wins, so put
the fastest one first and keep a second as fallback. The wire behavior
of all six adapters is frozen by the vendored fixture suite
(`backend/tests/test_search_providers_contract.py` — same requests
out, same normalized hits or the same error kind, as the desktop TS
reference implementation), and the fallback + key-presence semantics
are walled by `test_discovery.py`.

**What to be careful at.** Keys are per-provider keyring slots
(`search:<id>`) — exporting a profile carries provider *rows*, never
keys; re-enter them per machine. All-failing surfaces as `unreachable`
(chat skips search for that turn). Rate limits (`rate_limit`, HTTP
429) carry `retry_after_ms` where the provider sends one — respect it
before re-probing.

## Recipe 4 — an external RSS or YouTube source

**When to use.** A feed or channel that regularly publishes study
material — a lecture podcast RSS, a course playlist — and you want new
items *suggested* on a schedule instead of checking by hand.

**When NOT to use.** For a channel you import from once, use Import →
URL once (the built-in YouTube parser handles single videos). For a
site with no feed and no search value, a `site_search` source needs a
configured search provider (recipe 3) — order your setup accordingly.
Never use a source when you want automatic import: sources suggest,
you decide.

**Complete code.** Configuration through Settings → Tools → Web
sources: pick the kind, paste the feed/channel/playlist URL, optionally
scope it to a course and label it; the interval floor is 15 minutes
(default 6 h). The scan legs and their validation are walled by
`backend/tests/test_external_sources.py` — its RSS fixture is the
honest shape of what the leg accepts (HTML in titles stripped, tracking
params normalized away, `etag`/`last-modified` resume, dedupe on the
normalized URL, previously-saved-or-dismissed items never re-surfaced).

**What to be careful at.** Feed and yt-dlp metadata is untrusted input
— titles are HTML-stripped and URLs re-validated before anything is
stored. A dead feed shows its `last_scan_error` on the row (per-source
isolation — one bad source never blocks the scan). YouTube legs run
yt-dlp as a subprocess outside the app's perimeter; keep it updated on
your machine when extractors break.

## Recipe 5 — git as the distribution vehicle

**When to use.** You wrote a connector (recipes 1–2) and want to ship
it to your other machines or other people: push the server to a git
repo, register from a clone everywhere. This is the family's
recorded distribution story for study — the host profile's source
answer is *managed MCP servers from sources* — and the reference
artifact is the template repo itself: `server.py` + `manifest.json` +
a README, MIT-licensed, clonable.

**When NOT to use.** Study has no career-style install-from-git
extension import (no consent ledger, no content-addressed install tree,
no per-digest enable) — do not promise one; a repo here is just *where
the code lives*, and each host registers it explicitly. If you find
yourself wanting install-time trust decisions, that is a family
charter conversation, not a study-side hack.

**Complete code.** The template repo *is* the complete artifact —
clone it, rename the id in `manifest.json`, edit `server.py`'s tool to
the host's contract, push. Registering from the clone is exactly the
quickstart flow with `$QS` pointed at your checkout:

```bash
git clone https://github.com/your-org/your-connector "$QS/your-connector"
uv venv "$QS/.venv" && uv pip install --python "$QS/.venv/bin/python" fastmcp
# then register: command = $QS/.venv/bin/python, args = [$QS/your-connector/server.py]
```

**What to be careful at.** You are running a checkout — `git pull`
silently changes what your study app executes on the next call. Pin a
tag or commit for anything you did not write yourself, and treat a
third-party connector as code you would run: it executes outside the
perimeter with its own network access. Rotation (token changes, URL
moves) is a PATCH away; deletion cleans the keyring slots with the
row.
