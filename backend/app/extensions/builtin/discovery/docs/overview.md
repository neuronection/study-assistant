# Overview

The **discovery** connector is one normalized-result registry over
pluggable providers. When you ask a question in chat and trigger
**DISCOVER** (the connector's read-only chat tool), the app fans the
query out to every enabled provider and renders one merged suggestion
list: web results, YouTube videos, site presets and results from your
own MCP servers that speak the discovery contract.

- **Providers are pluggable** — web (the bundled search-trio
  providers), YouTube flat search, site-filtered presets (Khan Academy
  by default) and `mcp.<server>.<tool>` legs.
- **Suggestions, never state** — results are rendered in chat and then
  gone: nothing is persisted, imported or auto-downloaded.
- **Read-only by declaration** — the connector declares only the
  `chat-tools` capability, and its single tool carries the `read-only`
  risk class.

## When to use it

- You want "find me material about X" to cover the open web and your
  own curated sources in one step.
- You registered an MCP server whose tool returns normalized rows and
  want it to appear in the same list as the built-in providers.

## When NOT to use it

- You want *ongoing watching* of a feed or channel — that is the
  external web sources connector, which polls on a schedule.
- You want content pulled into your library without clicking — discovery
  results never leave the chat surface on their own.
