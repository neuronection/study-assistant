# Extension SDK overview

Study Assistant's extensibility surface is a **local-first, dual-mode
desktop host for the family extension charter** (one contract across the
Neuronection products): an *extension* is a declared artifact — a
validated manifest (`extension/v1` envelope, kind `connector` in study's
profile) whose declared capabilities gate what it may do, never probed.
The subsystem lives at `backend/app/extensions/` — the vendored family
contract modules (`contract.py`, `polite_http.py`, `conformance.py`),
the registry that validates every bundled manifest at registration, the
ADR-0035 web-search trio under `search/`, the bundled connectors under
`builtin/`, and the MCP instance lifecycle (`mcp_servers.py`,
`runtime/mcp_parse.py`).

The mental model in three bullets:

- **Connectors feed the content pipeline; they are not the pipeline.**
  A connector's rows land as *suggestions* in the Discover funnel or as
  parser output inside Import & parse — never as materials, never as an
  LLM call. The app owns validation, dedupe, and what becomes a course
  node. (In family vocabulary study's connector surface is the
  "source engine" alias — the noun is connector everywhere in code.)
- **What an extension may do is declared, not discovered.** Bundled
  manifests validate at registration against the vendored envelope
  schema; capability use is gated by the registry's declared data (D3).
  External code is T3 (an MCP server process) — never an in-process
  plugin.
- **The wire contracts are vendored family law.** The web-search trio
  and the charter artifacts are byte-identical copies of the dev
  canonicals, drift-walled by sync scripts. Their vocabularies (error
  kinds, statuses, tool contracts) are data, not prose.

## The surface today

| Extension | id (kind `connector`) | What it does |
|---|---|---|
| External web sources | `external-sources` | Bundled: RSS/Atom feeds, YouTube channels/playlists, site-filtered searches — polled into suggestions on a schedule (declares `sync`). |
| Discovery | `discovery` | Bundled: one normalized-result registry over pluggable providers — web (the ADR-0035 trio), YouTube flat search, site presets, external MCP servers (declares `chat-tools`, the read-only DISCOVER tool). |
| MCP servers | `mcp` | The T3 instance surface: every registered external MCP server is one *instance* of this connector — its own transport config, a keyring-sealed token/env slot, a per-tool allowlist with declared contracts (declares `secrets`). |

Beside the bundles, **two configuration-only families** use the same
subsystem without spawning anything: the web-search providers (ordered
Tavily/SearXNG/Brave/Exa/Serper/Google-PSE rows behind chat SEARCH/FETCH
and discovery) and the discovery provider toggles (which channels feed
suggestions).

## When to build an extension vs a core feature

**Write an extension when** the thing you want is a *source that varies
per user or per deployment*: a site with course pages worth parsing, a
private search endpoint, a feed of lecture videos, an internal API that
should surface in Discover. Extensions meet the app at two honest
seams — the discovery contract (rows become suggestions) and the parse
contract (a tool imports one URL like a built-in parser) — and external
code runs in its own process (T3), governed only by what it returns.

**Write a core feature when** the behavior must hold for every study
session and needs the service layer: grading, scheduling, FSRS,
math verification, the import/export formats. Those carry product law
(determinism-before-LLM, schema discipline) that must not live in an
external process. Don't reach for a connector to add a UI page or an
endpoint — there is no in-process plugin tier, by charter.

**Distributing connectors** rides git, family-style: the reference
template ([`career-connector-template`](https://github.com/neuronection/career-connector-template)
— its `server.py` is this set's quickstart vehicle) is cloned, renamed,
and its tool edited to speak the host's contract; each user registers
their copy through the Tools tab. Study's host profile records this as
*managed MCP servers from sources* — there is no career-style
install-from-git extension import today (see the
[git-distribution recipe](examples-and-use-cases.md#recipe-5--git-as-the-distribution-vehicle)).

## Where to go next

- Impatient? The [Quickstart](quickstart.md) takes you from a scratch
  checkout to DISCOVER using your own MCP server in about ten minutes.
- Building a connector? Read [Core Concepts](core-concepts.md), then
  [Authoring & Configuration](authoring-and-configuration.md), then the
  [recipes](examples-and-use-cases.md).
- Using the app's Tools tab? Start at the user side:
  [Add an MCP connector](../../user/add-an-mcp-connector.md),
  [Add a search provider](../../user/add-a-search-provider.md),
  [Manage web sources](../../user/manage-web-sources.md),
  [Troubleshooting](../../user/extension-troubleshooting.md).
