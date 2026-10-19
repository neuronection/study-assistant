# Overview

The **mcp** connector brings external MCP (Model Context Protocol)
servers into study. Each server you register is one *instance* of this
one bundled connector: its own transport configuration, a sealed
credential slot, a per-tool allowlist with declared contracts, and its
own status. Server tools can feed **discovery** (search suggestions in
chat) or **parse** (URL import extraction) — or stay disabled.

- **You bring the server** — study registers and governs servers you
  point it at (`stdio` command or `http`/`sse` URL); it never ships or
  downloads one for you.
- **Explicit over automatic** — tools are discovered only when you
  press Refresh, and nothing is enabled by a refresh. Disabled is the
  default for every server and every tool.
- **Governed return path** — server processes run outside the app's
  network perimeter (they are separate processes); everything they
  *return* is validated, capped and audited app-side.

## When to use it

- You run (or trust) an MCP server and want its tools as discovery or
  parse legs inside study.
- You want one audited, allowlisted surface for external tools with
  per-tool contracts instead of an all-or-nothing integration.

## When NOT to use it

- You just want web search — the bundled discovery connector and its
  web-search providers already cover that without a second process.
- You cannot review what the server does — a server you register can
  open its own network connections (see Security); only register
  servers whose behavior you accept.
