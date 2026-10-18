# Quickstart — register an MCP server and watch DISCOVER use it

One path, about ten minutes: write a discovery-contract MCP server
modeled on the family template, point a scratch Study Assistant profile
at it, register it, refresh to list its real tools, declare the
discovery contract — and DISCOVER returns your rows. The transcript
below is the actual output of exactly this flow (executed 2026-10-18
against a scratch SQLite profile; responses trimmed to the fields that
matter, the spawned server's startup banner omitted). The same pipeline
runs in CI as the real-subprocess wall
`backend/tests/test_mcp_connectors.py::test_real_stdio_spawn_feeds_discovery_end_to_end`
against `backend/tests/fixtures/mcp_discovery_server.py` — the same
server written against the `mcp` SDK the app itself ships (no fastmcp
dependency), so CI walls the documented path without a scratch venv.

**Prerequisites**

- A `backend/` checkout with its environment (`uv sync` — everything
  runs through `uv run`).
- A scratch directory for this walkthrough (here `$QS`):
  `export QS=/tmp/study-sdk-quickstart && mkdir -p "$QS"` (nothing
  below writes into your working tree).
- Python with the `fastmcp` package for the server (one scratch venv,
  reused for every connector you write):
  `uv venv "$QS/.venv" && uv pip install --python "$QS/.venv/bin/python" fastmcp`.

**Success criterion:** `POST /api/v1/discovery/search` returns two rows
with `"provider": "mcp.coursehub.search_courses"` — and exactly two,
because the server deliberately returns a third, invalid row that the
app drops. One audit row (`mcp_tool_call`) lands in `ai_interactions`.

## 1. The server (the family template, tool swapped)

The reference vehicle is the family template
[`career-connector-template`](https://github.com/neuronection/career-connector-template)
— its `server.py` is an external MCP server (the T3 script tier). Study
consumes the same shape; the one edit is the tool, which must speak
study's **discovery contract**: it receives `{"query": str}` and its
text output is JSON — a list of rows (or `{"results": [...]}`), every
valid row carrying a non-empty `title` and an http(s) `url`. Save this
as `$QS/server.py`:

```python
"""A study-assistant discovery connector (T3 script tier).

Modeled on the family template (career-connector-template's server.py):
an external MCP server whose tool feeds study's DISCOVER. The tool
receives {"query": str} and returns JSON rows with a non-empty title and
an http(s) url — study validates and caps every row app-side before it
reaches a chat, so keep rows honest and small.
"""

from __future__ import annotations

import json

from fastmcp import FastMCP

mcp = FastMCP("coursehub")


def _rows(query: str) -> list[dict]:
    """Your real source is queried here — the script's own network calls
    are its own business (T3 runs outside the app's perimeter)."""
    slug = "".join(c if c.isalnum() else "-" for c in query.lower()).strip("-") or "calculus"
    return [
        {
            "title": f"{query} — interactive course",
            "url": f"https://coursehub.example/learn/{slug}",
            "kind": "course",
            "description": "A worked example row from your connector.",
        },
        {
            "title": f"{query} — problem set",
            "url": f"https://coursehub.example/learn/{slug}/problems",
            "kind": "exercise",
            "description": "Practice rows ride the same contract.",
        },
        {"title": "", "url": "https://coursehub.example/broken"},
    ]


@mcp.tool
def search_courses(query: str) -> str:
    """Return the hub's rows for a study query (the discovery contract)."""
    return json.dumps({"results": _rows(query)})


if __name__ == "__main__":
    mcp.run()
```

The third row (`title: ""`) is deliberate — it demonstrates the app-side
validation this contract promises: invalid rows are dropped with a
logged warning, never trusted, never faked.

Sanity-check the server standalone (optional but recommended):

```bash
"$QS/.venv/bin/python" -c "import sys; sys.path.insert(0, '$QS'); import server; print(server._rows('chain rule')[0]['title'])"
```

```text
chain rule — interactive course
```

## 2. A scratch profile

The API needs a bootstrapped database. The fastest throwaway is the app
stack itself — create the app against `$QS` and drive it through the
same client the test suite uses (the MCP spawn below is a real
subprocess either way). Any script with this shape works; the essential
calls are shown as HTTP because that is what the settings Tools tab
sends:

```python
import os
os.environ["SA_APP_ENV"] = "test"
os.environ["SA_CONFIG_DIR"] = os.path.expandvars("$QS/config")

import keyring
from keyring.backend import KeyringBackend

class TestKeyring(KeyringBackend):  # never touch the real OS keyring
    priority = 99
    def __init__(self): self._store = {}
    def set_password(self, s, u, p): self._store[(s, u)] = p
    def get_password(self, s, u): return self._store.get((s, u))
    def delete_password(self, s, u): self._store.pop((s, u), None)

keyring.set_keyring(TestKeyring())

from alembic import command
from alembic.config import Config

cfg = Config("alembic.ini")
cfg.set_main_option("sqlalchemy.url", f"sqlite:///$QS/study.sqlite3")
command.upgrade(cfg, "head")

from app.core.config import Settings
from app.main import create_app

app = create_app(Settings(
    data_dir=..., config_dir=..., spa_dist=..., log_level="WARNING", app_env="test",
))
```

(from `backend/`; run migrations and app exactly once per scratch dir —
see `backend/tests/conftest.py` for the battle-tested version of this
bootstrap.)

## 3. Register, refresh, declare, discover

With a client bound to that app (any authorized session — the Tools tab
does the same four calls):

**Register** — `POST /api/v1/mcp/servers`. Rows are created **disabled**
with an empty tool list; nothing runs yet:

```json
{
  "name": "coursehub",
  "command": "/tmp/study-sdk-quickstart/.venv/bin/python",
  "args": ["/tmp/study-sdk-quickstart/server.py"]
}
```

Real response (`201`):

```json
{
  "id": "51eaba9f18e6",
  "name": "coursehub",
  "enabled": false,
  "tools": [],
  "transport": "stdio",
  "status": "ok",
  "conditions": [],
  "declared_contracts": []
}
```

**Refresh** — `POST /api/v1/mcp/servers/{id}/refresh`. This is the real
spawn: the app launches your command over stdio, performs the MCP
handshake and lists tools. Each tool lands **disabled** with contract
`none` — refresh never auto-enables:

```json
{
  "tools": [
    {
      "name": "search_courses",
      "description": "Return the hub's rows for a study query (the discovery contract).",
      "enabled": false,
      "contract": "none",
      "url_pattern": null
    }
  ],
  "refreshed_at": "2026-10-18T02:25:48.302344+00:00",
  "last_error": null
}
```

**Declare** — `PATCH /api/v1/mcp/servers/{id}`: enable the server and
the tool, and set the tool's contract to `discovery`:

```json
{
  "enabled": true,
  "tools": [{"name": "search_courses", "enabled": true, "contract": "discovery"}]
}
```

Real response carries the surfaced contract (`"declared_contracts":
["discovery"]`, `"status": "ok"`).

**Discover** — `POST /api/v1/discovery/search`:

```json
{"query": "chain rule", "providers": ["mcp.coursehub.search_courses"]}
```

Real response (`200`) — two rows, the invalid third dropped (the server
log shows `mcp_discovery_invalid_row provider=mcp.coursehub.search_courses`):

```json
{
  "results": [
    {
      "provider": "mcp.coursehub.search_courses",
      "title": "chain rule — interactive course",
      "url": "https://coursehub.example/learn/chain-rule",
      "kind": "course",
      "meta": {"mcp": true}
    },
    {
      "provider": "mcp.coursehub.search_courses",
      "title": "chain rule — problem set",
      "url": "https://coursehub.example/learn/chain-rule/problems",
      "kind": "exercise",
      "meta": {"mcp": true}
    }
  ],
  "errors": []
}
```

The provider id is `mcp.<server name>.<tool name>` — the same rows the
chat DISCOVER tool surfaces (it rides the same provider registry), and
the same funnel the Discover dialog annotates with keep/import actions.

One audit row per tool call lands in `ai_interactions` (checked
directly after the call above):

```text
audit rows (task=mcp_tool_call): 1
  model=mcp.coursehub.search_courses latency_ms=748
```

## Where next

- [Core Concepts](core-concepts.md) for the nouns you just used, then
  [Authoring & Configuration](authoring-and-configuration.md) for every
  field the registration accepts (transports, tokens, url_patterns).
- The [parse-contract recipe](examples-and-use-cases.md#recipe-2--a-parse-contract-parser-for-one-site)
  makes a tool import whole pages instead of suggesting them.
- The consent side of what you just enabled:
  [Security & Gotchas](security-and-gotchas.md) — the T3 perimeter
  disclosure runs verbatim in the connector card, and so should your
  understanding of it.
- To clean up: delete the scratch directory. The scratch DB and
  keyring never touched your real profile.
