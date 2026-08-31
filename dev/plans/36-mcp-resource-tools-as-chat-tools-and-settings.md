# 36 — MCP resource tools become shared, chat-callable tools + a Settings page (ADR-080)

**Status:** COMPLETE (2026-08-25, user-requested) — 36A (shared registry), 36B (chat resource tools), 36C (Settings → MCP tab), 36D (chat-only tools dialog) all done ·
**Phase:** post-1.0 backlog — AI/agent interop (plan 36) ·
**Suggested order:** A → B → C → D

## Summary

The MCP resource server (`python -m courseassistant mcp`, read-only, for external agents) and
the in-app chat have two *separate* tool worlds: the MCP server exposes 8 resource tools
(`list_courses`, `get_node_*`), the chat exposes `CALC`/`SYMPY`/`READ`/`STATE`/`PLOT`. The
chat's "Tools the AI can use" dialog lists *both* groups, which makes the MCP tools look
chat-callable (they aren't — the LLM correctly said so). This round unifies them: the resource
tools become a **single shared registry** whose execution logic is called by both the MCP
server and (a curated subset) the chat; the MCP server is documented on the **Settings** page;
and the chat dialog shows **only chat-callable tools**.

## 36A — Shared resource-tool registry (backend)

**Problem.** `mcp_resources.py` nests each tool's execution inside an `@server.tool` closure, so
the chat cannot reuse the logic without duplicating it.

**Design.** Lift each tool's core query into a module-level function `(session, **params) → dict`,
and add a `RESOURCE_TOOLS` registry (name → description + the function + a `chat` keyword or
`None`). The MCP `@server.tool` wrappers become thin (call the module function), preserving the
MCP schema and `test_mcp_resources.py` behavior. Descriptions become module constants so the
MCP wrapper and the chat doc can't drift.

**Accept.** `create_resource_server` builds the same 8 tools; each tool's logic lives in one
module-level function; `RESOURCE_TOOLS` exposes name/description/`chat` keyword per tool.

**Tests.** `test_mcp_resources.py` stays green (behavior-preserving refactor) + a new assertion
that `RESOURCE_TOOLS` has the expected chat keywords for the curated set.

## 36B — Chat-callable resource tools (backend)

**Problem.** The chat can't list courses or browse a node's resources.

**Design.** A curated subset joins the chat tool catalog with a `READ`-style line grammar:

| keyword | tool | arg |
|---|---|---|
| `COURSES` | `list_courses` | — |
| `NODE_OVERVIEW` | `get_node_overview` | node handle `T#` or `here` |
| `NODE_QUIZZES` | `get_node_quizzes` | node handle `T#` or `here` |
| `NODE_EXERCISES` | `get_node_exercises` | node handle `T#` or `here` |
| `NODE_NOTES` | `get_node_notes` | node handle `T#` or `here` |

`here` resolves to `chat_session.node_id`; `T#` resolves through the mention registry (node
kind). Read-only, executed against the shared `RESOURCE_TOOLS` functions, emitted as
`tool_call` events (name/argument/result + timing, like the others), a dedicated budget
(`MAX_RESOURCE_ROUNDS = 5`/turn), and stripped from the answer. `get_node_context` /
`get_node_materials` / `get_node_concepts` stay MCP-only (redundant with the chat's own context
assembly). `CHAT_TOOL_DOC` gains a resource-tools section so the model knows the keywords.

**Accept.** "list my courses" → `COURSES`; "what quizzes are in this node" → `NODE_QUIZZES
here`; a `T#` handle from the manifest resolves; unknown/missing node → honest error fed back.

**Tests.** Backend: each keyword resolves + executes (scripted gateway emits the tool line),
budget cap, unknown-handle error, results fed back and stripped from the answer, `tool_call`
event carries timing. Frontend: none (tool cards already generic).

## 36C — Settings → MCP server section (frontend)

**Problem.** The only place the MCP server is mentioned is the chat's tool dialog.

**Design.** A new Settings tab **MCP server** (Settings → "MCP server") documenting what it is
(read-only access for external agents), the launch command (`python -m courseassistant mcp`)
with a **Copy** button, and the read-only tool list (name + description) from a small
`GET /ai/mcp` endpoint (or reuse `/ai/tools` groups). No secrets, no write config.

**Accept.** Settings → MCP server shows the command + tool list; nothing chat-related lives there.

**Tests.** Frontend: tab renders the command + tool names; copy button copies.

## 36D — Chat dialog shows only chat tools (frontend + backend)

**Problem.** `GET /ai/tools` returns a `mcp` group that the chat dialog renders as if callable.

**Design.** `GET /ai/tools` returns only the chat tools (drop the `mcp` group); the MCP tool
list lives behind the Settings endpoint (36C). The `ToolsDialog` renders a single chat-tools
list (the `chatGroup`/`mcpGroup` split is removed).

**Accept.** The chat "Tools the AI can use" popup lists exactly the tools the chat can call
(CALC/SYMPY/READ/STATE/PLOT + the 5 resource keywords), nothing else.

**Tests.** Backend: `/ai/tools` has one group, no `mcp`. Frontend: dialog renders chat tools only.

## Non-goals

- No MCP server *configuration* (no transport/port settings) — stdio only, documented.
- No write tools for external agents or chat (read-only per ADR-039/9E and the MCP design).
- No `get_node_context`/`get_node_materials`/`get_node_concepts` in chat this round.

## Verification per slice

Standard suite (AGENTS.md) + `ca-docs-sync`. ADR-080 row appended as the slice starts.
