"""A real stdio MCP server speaking study's discovery contract.

Test scaffold (plan 34 wave 5): the runnable core of the SDK quickstart
and the recipes — spawned as a REAL local subprocess by
``test_mcp_connectors.py`` (no network, no fastmcp dependency; rides the
``mcp`` SDK already in the dev environment, the same server API
``app/ai/mcp_resources.py`` uses). Kept in the quickstart's shape so the
documented path and the walled path cannot drift.
"""

from __future__ import annotations

import json
import sys

from mcp.server.mcpserver import MCPServer

server = MCPServer(name="coursehub")


def _rows(query: str) -> list[dict[str, object]]:
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


@server.tool(
    name="search_courses",
    description="Return the hub's rows for a study query (the discovery contract).",
)
def search_courses(query: str) -> str:
    return json.dumps({"results": _rows(query)})


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        print(json.dumps({"results": _rows("chain rule")}))
        return
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
