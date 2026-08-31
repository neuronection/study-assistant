# 41 — Chat branch-tree rail (post-1.0, plan 40 follow-up)

**Status:** complete (2026-08-27, user-approved) · **Phase:** post-1.0 backlog ·
**Suggested order:** A (single slice)

## Context

Plan 40 gave chat OpenWebUI-style branching (0044 parent/active-child pointers) with
inline `‹k/N›` switchers, but there is no way to see the whole branch structure at a
glance. The user asked for an OpenWebUI-style flow/tree view; chose the lightweight
graph-rail style over a react-flow canvas (dependency + bundle cost rejected).

**ADR:** 095 (tree rail reads a read-only snapshot endpoint; click = one-pointer
`select`, level-flip semantics identical to the inline switchers; no auto-activation
of ancestor chains).

## A — Tree endpoint + graph-rail panel (complete)

**Problem.** Users cannot see where the conversation forked or which variants exist.

**Design.** `GET /chat/sessions/{id}/tree` (read-only, no schema change) returns
`{active_root_id, nodes: [{id, role, excerpt(≤100 chars), parent_id, children,
active_child_id}]}`. Frontend `BranchTreePanel` renders a recursive, indented
commit-graph-style list (dots for on/off-path nodes, role icons, truncated excerpts,
sibling-count badges); active path highlighted via a client-side pointer walk.
Clicking any node calls `POST /chat/messages/{id}/select` and invalidates
messages + tree. Entry: `GitBranch` popover button in the chat panel header
(only when a session is open).

**Accept.** Branched chat → header button → tree shows every fork; hidden variants
visible; clicking one re-walks the panel and the bubbles.

**Tests.** Backend: endpoint exposes hidden branches, correct parents/children/
active root. Frontend: render + active-path `aria-current` markers, click selects.
