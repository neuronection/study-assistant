# Security

## The perimeter, stated plainly

> This extension runs as a separate process outside the app's network perimeter. It opens its own network connections, with no SSRF guard, robots.txt check or rate limiting by the app. The app governs only what it returns: outputs are validated and capped.

That is the family's Tier-3 perimeter disclosure, rendered verbatim
from the extension charter (and from **Settings → Tools → Connectors**,
which shows the same text) — read it before registering a server, and
again whenever a server's code changes. The connector's manifest
deliberately declares **no** `net` capability: the server's own
sockets are outside the host perimeter, disclosed here instead of
smuggled in as a capability.

## What the app governs

- **Explicit activation** — servers and tools start disabled; a
  refresh lists tools but never enables anything.
- **Per-tool allowlist + contracts** — only tools you enabled with a
  `discovery` or `parse` contract are ever called, and `parse` tools
  only fire on URLs matching their declared pattern.
- **Row validation + caps** — discovery rows must carry a title and an
  `http(s)` URL, and are length-capped; parse results are validated
  before import. Malformed output is a typed error, never silently
  coerced.
- **Sealed secrets** — the bearer token and env map live in the OS
  keyring, sealed at rest; they are injected at call time and never
  enter stored config or the audit log's visible fields.
- **One audit row per call** — tool reference, latency, outcome.
- **Resource caps** — per-call timeout (5–120 s), concurrency cap
  (≤8), and at most 10 registered servers.

## What only you can govern

- **The server's behavior** — what it fetches, where it sends data,
  what it executes. The app sees only the wire it speaks to you.
- **The command you register** — a `stdio` entry runs with your user's
  privileges. Register binaries you have read or trust.
- **Secrets you hand over** — give a server the narrowest token it
  needs; deleting the row deletes the sealed copies.
