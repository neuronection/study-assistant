# Usage

## Refresh to discover tools

Nothing is known about a server's tools until you press **Refresh**.
Refresh connects (spawning a `stdio` process or calling the URL), lists
the server's tools, and merges them into the row:

- new tools appear **disabled** with contract `none`,
- tools you previously enabled keep their enabled state and contract —
  a refresh never flips anything on,
- tools the server no longer offers disappear from the row.

A failed refresh records the error on the row (and bumps its status)
instead of half-updating the tool list.

## Per-tool contracts

Every tool row has an enable checkbox and a contract selector:

| Contract | Meaning |
|---|---|
| `none` | Listed but unused — safe parking state. |
| `discovery` | The tool joins the DISCOVER fan-out; it receives `{"query"}` and must return JSON rows (see the discovery connector's docs). |
| `parse` | The tool is offered as a URL-import extractor; give it a **URL pattern** (≤300 chars, e.g. `example.com/learn/*`) so it only fires on matching URLs. |

Enabled `parse` results are validated app-side before anything enters
your library; malformed output is a typed error, not a silent import.

## Enable, disable, delete

- **Enable** a server to let its enabled tools participate. Calls to
  disabled servers are refused without spawning anything.
- **Delete** removes the row and its sealed token/env from the keyring.
- Every tool call (discovery or parse) writes one audit row — tool
  reference, latency, outcome — so "what did this server do" always has
  an answer.
