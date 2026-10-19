# Setup

Servers are managed in **Settings → Tools → Connectors**. At most
**10 servers** can be registered per profile.

## Register a server

1. Press **Add server**.
2. Choose the transport:

   | Transport | Required field | Notes |
   |---|---|---|
   | `stdio` | **command** (+ optional args) | The app spawns the process, e.g. `/usr/bin/python -m their_server`. |
   | `http` | **URL** | A streamable-HTTP endpoint, `http(s)` only. |
   | `sse` | **URL** | A Server-Sent-Events endpoint, `http(s)` only. |

3. Name the server (≤80 chars). The name is the tool prefix you will
   recognize later (`mcp.<name>.<tool>`).
4. Optional credentials (both are secret slots — see below):
   - **Bearer token** — sent as the Authorization header on remote calls.
   - **Environment** — a JSON object of env vars for a `stdio` process.
5. Save. The server is added **disabled**.

## The knobs

- **Timeout** — per tool call, 5–120 seconds (default 30).
- **Max concurrent calls** — 1–8 (default 4).

## Sealed credentials

The token and the env map never live in the server's stored config
row: both are declared `x-secret` slots in the connector manifest and
are stored in the OS keyring (sealed at rest). The config row only
records *that* a token/env exists, shown as a key chip on the server
row. Clearing the fields on edit deletes the sealed values.
