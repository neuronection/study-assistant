# Usage

## Running a discovery

In chat, ask for material and let the DISCOVER tool run (it is
read-only and never needs confirmation). The tool collects up to a
handful of results per provider, caps the merged list, and renders one
normalized suggestion set. Each row carries:

- **provider** — `web`, `youtube`, `site:<host>` or
  `mcp.<server>.<tool>`,
- **title** — capped at 300 characters,
- **link** — `http(s)`-validated, capped at 2048 characters,
- **kind** — `video`, `course`, `article`, `exercise` or `other`
  (site presets default to `course`),
- **description** — capped at 800 characters where the provider gives
  one (web and MCP legs).

Rows are suggestions: open them, import them through the normal URL
import, or ignore them. Nothing lands in your library without you.

## The discovery contract for MCP tools

An MCP tool joins the fan-out by receiving one argument,
`{"query": "..."}`, and returning **JSON as text** — either a bare
list of rows or an object `{"results": [...]}`. Every row must carry a
non-empty `title` and an `http(s)` `url`; optional `kind` and
`description` are honored (kind must be one of the five vocabulary
values, else the row falls back to `other`). Invalid rows are dropped
with a logged warning — never trusted, never faked — and valid rows
are trimmed to the result cap.

## What is logged

Every MCP discovery call writes one audit row (tool reference,
latency, outcome). Built-in provider calls use the web-search legs'
normal error handling; a failing provider degrades its own leg only —
the other providers still answer.
