# Add an MCP connector

Bring an external MCP server's tools into Study Assistant — as
discovery providers (they feed the Discover dialog and the tutor's
research) or as site parsers (they import pages from one site). Open
**Settings → Tools → Integrations** (the **MCP connectors** section).

## Add a server

1. Press **Add server**.
2. Give it a **Name** — it becomes part of the tool label you'll see in
   Discover (`mcp.<name>.<tool>`).
3. Pick the **Transport**:
   - **stdio (local command)** — the app starts a program on this
     machine: fill **Command** (e.g. `/opt/my-connectors/.venv/bin/python`)
     and **Arguments** (e.g. `/opt/my-connectors/server.py`). The
     program must speak the MCP protocol over stdio.
   - **Streamable HTTP** or **SSE** — a running server elsewhere: fill
     the **Server URL** (`https://…`) and, if it needs one, an
     **Auth token**.
4. Optional: an **Environment variables** JSON object for a stdio
   server, a **Timeout** per call (5–120 s), and a **Max parallel
   calls** cap.
5. Save.

Tokens and environment maps are stored in your operating system's
keyring — never in the database — and never shown again (you'll see
"Token in keyring"; leave the field blank to keep the stored one).

## The disclosure box, explained

Every server card shows an **External process** box with this text:

> This extension runs as a separate process outside the app's network perimeter. It opens its own network connections, with no SSRF guard, robots.txt check or rate limiting by the app. The app governs only what it returns: outputs are validated and capped.

In plain terms: an MCP server is *your* software, and it runs with
your user's permissions — the app cannot limit what it does, which
sites it contacts, or how often. What the app does control is what the
server *returns*: every result is checked and size-capped before it
reaches you, and nothing is ever imported automatically. Only register
servers whose code you know and trust — for example, one you wrote, or
a clone of a repository you've read.

## Refresh, then enable

New servers start **off**, with no tools listed. That is deliberate —
nothing runs until you say so:

1. Press **Refresh**. The app starts the server, asks it which tools it
   offers, and lists them under **Declared tools** — each one off, with
   **No contract**.
2. For each tool you want, switch it on and choose its **Contract**:
   - **Discovery** — the tool searches a source for you. It appears as
     its own provider in the Discover dialog and the tutor's Discover
     tool.
   - **Parser** — the tool reads pages from one site. Give it a **URL
     pattern** like `coursehub.example/learn/*`; from then on, importing
     a matching page uses your tool instead of the built-in web parser.
3. Turn the server **On**.

**Refresh never enables anything by itself** — after every refresh,
re-check the tool list (a server that renamed or removed tools shows
the new list; your choices persist for tools that kept their names).

## Reading the health line

Each server row shows one of: **Healthy**, **Degraded** (the last
refresh failed — the error is shown on the row), **Failing**,
**Stale** (not refreshed in over 24 h), or **Incomplete configuration**
(a required field is missing for the chosen transport). Failures are
honest: a server that cannot start stays visible with its error until
you fix the cause and refresh again.

## Removing a server

**Delete** removes the server together with its keyring entries (token
and environment map). Nothing of it remains on disk.

## Where connectors surface

- Discovery-contract tools appear in the **Discover** dialog's provider
  list and answer the tutor's research tool.
- Parser-contract tools work inside **Import & parse** for URLs
  matching their pattern — the import looks and behaves like any other.
- Every tool call is recorded in the app's activity log with its
  duration.

For problems and fixes, see
[Extension troubleshooting](extension-troubleshooting.md). To suggest
material from feeds and channels instead of running code, see
[Manage web sources](manage-web-sources.md).
