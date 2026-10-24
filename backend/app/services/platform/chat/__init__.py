"""Chat domain services (family plan 40 W1 — structure-only split).

`service` hosts `ChatService` (session/message/branch CRUD + turn
orchestration + thin proposal glue over `platform/proposal_actions.py`),
`turn_context` the per-turn context assembly (guards, notes, structure,
registry), `tools` the chat tool seam, `errors` the shared `ChatError`.
"""
