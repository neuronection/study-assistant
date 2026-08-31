# 40 — Chat turn branches + composer & message actions (post-1.0, tutor UX)

**Status:** complete (as-built 2026-08-27; was planned 2026-08-27, user-approved) ·
**Phase:** post-1.0 backlog · **Suggested order:** A → B → C → D

## Context

The tutor chat (sidepanel + full page) rendered a strictly linear message list:
`POST /chat/sessions/{id}/messages` appends the user message and enqueues a
`chat_turn` job whose handler asserted `messages[-1].role == "user"`, and history
was built as the last N rows. Consequences: a sent message could never be corrected
without polluting the context, and a bad answer could never be regenerated. The
composer had no equation/drawing/screenshot entry points; no stop control; no
code-copy; no export.

**ADRs:** 093 (branch tree) · 094 (screenshot via getDisplayMedia) — recorded in
06-decisions-and-risks.md.

## A — Branch tree core (done, commit a6b4d31)

Migration **0044**: `chat_messages.parent_id` + `active_child_id` (plain Integer —
SQLite can't ALTER-add FKs; service-enforced) and `chat_sessions.active_root_id`;
data migration chains legacy messages so old chats look unchanged. Active-path
walk in `ChatService.messages()`; history cut from the path up to the target turn;
assistant rows parented under the target user message. Endpoints
`edit` / `regenerate` / `select`; `MessageOut` + `parent_id`/`variant_index`/
`variant_count`. Per-session FIFO turn lock shared by handler + tip-scans.

## B — Message actions UI (done, 38cdf5b)

Hover **Copy**; user bubbles gain inline **Edit** (Save & resend → `edit`);
assistant bubbles gain **Regenerate** (`…/regenerate`); `‹index/count›` switcher
drives `select`; `sibling_ids` added to `MessageOut`.

## C — Composer "+" items (done, c265440)

**Equation…** (MathLive `MathInput`, inline `$…$` vs `$$…$$`, insert at cursor),
**Draw…** (`DrawCanvas` → PNG → `useMaterialUpload` → **Chat uploads** material
chip), **Screenshot…** (`getDisplayMedia` frame → draggable crop overlay → cropped
PNG upload; graceful unsupported alert; hidden without a course).

## D — QoL extras (done, 466676f)

**Stop** (`POST /chat/sessions/{id}/stop`, per-session event checked per chunk;
prefix persisted with `trace.stream_interrupted`; ■ button while pending; WS
`stream_interrupted` finalizes panel state). Sticky **scroll-to-latest** pill
(>120 px from bottom). **Copy** on code blocks (`CodeSurface` in BlockRenderer).
**Export as Markdown** from session ⋯ menus (`exportSessionMarkdown.ts`).

## As-built deviations from the original design

- Added `sibling_ids` to `MessageOut` (switcher needs both neighbors).
- `chat_sessions.active_root_id` added for root-level variants (a pointer column
  alone cannot order multiple parentless roots).
- A FIFO per-session turn lock (handler + send/edit/regenerate tip-scans) replaced
  the "UI single-flight means no races" assumption — back-to-back requests now
  parent correctly even while a previous generation is still streaming.
- Empty-prefix interruptions still persist an (invisible) empty assistant row —
  acceptable; polish item.

## Non-goals kept

Native/portal screenshot tools; branch graph canvas (→ plan 41 rail instead);
per-message model badges; server-side chat search.
