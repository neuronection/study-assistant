# Security & gotchas

The consent law here is user-facing and lives verbatim in
[Add an MCP connector](../../user/add-an-mcp-connector.md) too; this
page is the authoring-side deep dive: what each tier may do, what is
denied where, the disclosed residuals, and the sealing rules.

## The trust tiers, as study hosts them

| Tier | What runs where | What is denied | Residual risk |
|---|---|---|---|
| T0 vendored | validated data + contract code only (the web-search trio, the charter set) | anything not in the vendored wire contract — normalization rejects it | drift between copies (walled by sync, not by trust) |
| T1 bundled | in-process, reviewed with the product | n/a — it *is* the product | the review is the control |
| T3 external (MCP) | a separate process the app calls over stdio/http/sse | nothing at the perimeter — its sockets are its own; the host governs only returned rows (validated, capped) | the entire perimeter is the residual, disclosed verbatim below |

There is no T2 sandbox tier in study and no in-process plugin tier:
external code is T3 by shape, never imported.

## The T3 perimeter disclosure — verbatim

The charter's consent copy (ADR-0040 clause 21 /
`consent.t3PerimeterDisclosure`), rendered verbatim on the connector
card and served at `GET /api/v1/mcp/charter`; paraphrasing it away is a
conformance failure. Byte-verified against the vendored charter by
`backend/tests/test_extension_docs_tree.py`:

> This extension runs as a separate process outside the app's network perimeter. It opens its own network connections, with no SSRF guard, robots.txt check or rate limiting by the app. The app governs only what it returns: outputs are validated and capped.

What that means in practice, line by line:

- **"a separate process outside the app's network perimeter"** — the
  server is your software: it runs as your user, reads its own env and
  files, and the app cannot sandbox it.
- **"opens its own network connections, with no SSRF guard, robots.txt
  check or rate limiting by the app"** — study's in-app HTTP legs
  (search providers, RSS scans, FETCH) enforce schemes, timeouts and
  politeness; your server's calls enforce nothing unless *you* do.
- **"The app governs only what it returns: outputs are validated and
  capped"** — the entire trust model reduces to this: every row is
  re-validated app-side (title/url/kind caps for discovery;
  title/markdown presence for parse), invalid rows are dropped or the
  call refused, and one audit row (`ai_interactions`,
  `task=mcp_tool_call`) records every invocation.

## Secrets: sealed at rest, never in rows

- MCP **tokens and env maps** are written to the OS keyring under
  `mcp:<server id>:token` / `mcp:<server id>:env` the moment they are
  submitted — the stored preference row and every API response carry
  only `has_token` / `has_env` booleans. Deleting a server deletes its
  slots.
- Web-search **API keys** live in `search:<provider id>` slots; rows
  carry only a masked `key_hint`.
- Keyring values are additionally **sealed at rest** by the family
  cipher (Fernet under the keyring-held `SA_DATA_KEY`, ADR-0027) with
  plaintext-tolerant reads and rotation via `SA_DATA_KEY_PREVIOUS` —
  the runbook is in [the security model](../security.md).
- Tests never touch the real OS keyring (an in-memory backend is
  installed suite-wide by `backend/tests/conftest.py`); nothing in this
  subsystem may weaken that.

## SSRF and the in-app HTTP posture

The in-app legs are the contrast case to T3: search providers and the
RSS scan run through httpx with clamped timeouts, redirect-following
and the taxonomy's `unreachable`/`auth`/`rate_limit` semantics; FETCH
requires http(s), caps fetched content, and converts HTML to markdown
before it reaches a model. Remote MCP transports require `http(s)://`
URLs and send the sealed bearer token. What the app will *not* do is
pretend those guards extend past its own sockets — hence the
disclosure.

## Suggestions never auto-import

Every external row — discovery result, scanned feed item, site-search
hit — lands as a **suggestion** with keep/import/dismiss actions, deduped
on a normalized URL; the only path from a URL to a material is a human
import through the parse pipeline. Parse-contract tools are the same
rule one level deeper: they run inside an import *you* started. No
connector, provider or source ever writes a material, a course node or
a chat message on its own.

## Gotchas that bite

- **Refresh is honest about failure** — a spawn that dies records
  `last_error` and status `degraded`; the row keeps your settings.
  Re-enable after fixing the cause, not before.
- **`enabled` is per tool, not per server** — an enabled server with
  all tools disabled is inert; check the tool rows, not the toggle.
- **Parse patterns win over built-ins** — MCP parse tools sit at the
  front of the parser registry; a loose `url_pattern` captures traffic
  you meant for the built-ins.
- **Provider order is fallback order** — "first enabled that answers
  wins"; a dead first provider adds its timeout to every search.
- **`max_concurrent` fails loud** — over-cap calls raise `busy`; they
  never queue silently behind a stuck call.
