# Changelog

All notable changes to **Study Assistant** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Release history from before the public launch lives in the
[git tags](https://github.com/neuronection/study-assistant/tags) and
[GitHub Releases](https://github.com/neuronection/study-assistant/releases).

## [Unreleased]

### Added

- Tutor chat: the tools catalog now lists the assistant's proposal abilities
  as first-class HITL capabilities ("propose edits", "propose generations")
  with a warning-tone badge, and turns whose suggested actions fail
  validation say so honestly — a warning line plus per-fence reason codes
  (`trace.proposals_dropped`) instead of silently vanishing proposals
  (plan 78-A, ADR-192; family ADR-0015 conformance).
- Tutor chat: proposals are now grounded — every target id is checked
  against the offered manifest at contract time, and edit-in-place proposals
  (note/material edits and appends) require the target's full content to
  have been read in the same turn; ungrounded proposals trigger a repair
  round that names the exact `READ` call to make, and are dropped with an
  honest reason instead of becoming cards that can never apply (plan 78-B,
  ADR-192).
- Tutor chat: note and material edit proposals can now carry anchored
  `text_edits` (replace-with-exact-anchor / append / prepend) that resolve
  server-side against the current content — surgical diffs for targeted
  changes instead of whole-document regeneration, with
  mismatch/ambiguity/conflict dropped by stable reason codes (plan 78-C,
  ADR-192).
- Tutor chat: approving a proposal whose target changed in the meantime no
  longer dead-ends as stale — the card flips to "Changed" with the diff
  refreshed against the current content for explicit re-approval (anchored
  edits preserve interim manual edits), and the tutor now learns the outcome
  of its earlier cards on the next turn so it stops re-proposing resolved
  changes (plan 78-D, ADR-192).
- Tutor chat: suggested actions are now visible and resolvable outside the
  conversation — a cross-session proposals list (`GET /chat/proposals`), a
  pending count in the notification bell with a link to chat, and a badge on
  the chat rail entry (plan 78-E, ADR-192).

### Changed

- Adopt `@neuronection/assistant-ui` 0.42.0 (chat-tools-catalog badge chip,
  chat-hitl module enhancements, ModalBody compound, token refresh).

## [v0.9.1] - 2026-09-16

### Changed

- Adopt `@neuronection/assistant-ui` 0.37.0 (session-list title wrapping,
  softer chat-bubble radius, standalone `InfoTooltip`, settings-shell
  container-query layout modes) and refresh the minor/patch dependency
  drift (React 19.3, TanStack router/query/virtual, i18next, lucide-react,
  framer-motion, vite, eslint, and friends). Rendering majors (plotly 4,
  mermaid 12, katex 0.18) and toolchain majors (TypeScript 7, vitest 5)
  are deliberately held for dedicated passes.

### Fixed

- Tutor page (`/chat`): the chat history panel now scrolls on its own while
  the conversation and composer stay fixed (previously the whole page
  scrolled as one), and the input is the standard multiline composer that
  grows with the message like in Career Assistant.
- Startup: a stray `.env` in the working directory no longer crashes the
  app at boot — unrelated keys in it are now ignored (only `SA_*` settings
  are read).

## [v0.9.0] - 2026-09-16

### Added

- Custom MCP connectors: register your own external MCP servers in
  Settings → Integrations, refresh to list their tools, and assign each tool
  as a discovery source (appears in Discover and chat DISCOVER) or a parser
  (keyed by a URL pattern, runs inside Import & parse). Servers are disabled
  by default, invocations are audited and time-boxed, and all external
  output is validated before use. (plan 73-G, ADR-170)
- Chat discovery with approval-only attach: the chatbot gained a DISCOVER
  tool (web, YouTube and site presets; `DISCOVER here` searches for the
  current topic without typing a query) and an attach_link proposal that
  turns a found URL into a placed link reference after you approve it.
  (plan 73-F, ADR-167/170)
- External web sources: add RSS/Atom feeds, YouTube channels or playlists and
  site-filtered searches as standing sources — a deterministic scheduler scans
  them on a schedule (manual "Scan now" included) and new items land as
  suggestions in the Discover dialog, never auto-imported and never LLM-called.
  Settings → Integrations gains the Web sources card; sources travel inside
  course bundles with fresh cursors. (plan 73-E, ADR-167/170)
- Discovery suggestions & Discover dialog: search results can now be kept —
  save for later, dismiss, or attach/import them as link materials, with one
  tracked row per normalized URL per profile and a "Saved & dismissed" list in
  the new Discover dialog (course Materials tab and Library create menus).
  Settings → Providers gains a Discovery card for provider toggles and
  site presets. (plan 73-D)
- Discovery provider registry: search across web, YouTube, and site-filtered
  presets (Khan Academy built in) through one normalized, never-persisted
  search endpoint with honest per-provider errors. (plan 73-C, ADR-166)
- Parser registry & YouTube transcripts: the "Import & parse" verb on link
  references now works — YouTube videos gain searchable, timestamped
  transcripts, direct file URLs (PDF, Markdown, Office, audio…) download into
  the standard library pipeline, and plain pages convert like the URL
  importer. Links without captions say so and offer one-click audio
  transcription; re-parsing keeps version history. (plan 73-B, ADR-165)
- Link materials: paste a URL to keep it as a real, first-class reference —
  placeable at any topic, taggable, starable and searchable, with
  database-enforced dedupe on normalized URLs (YouTube short links and
  tracking parameters count as the same link). The URL import dialog now
  defaults to attaching references, with full import remaining one click
  away. (plan 73-A, ADR-164/171)
- Async compose with progress and cancel: composing study material no longer
  blocks the app for the whole generation — documents are generated as a
  cancellable background job with live progress, single-job status polling
  and a cancel button; the chat approval path stays synchronous.
  (plan 70-D, ADR-156)
- Validated practice sets: AI-composed practice sets are now authored as
  structured items whose answers are verified server-side (SymPy-checked
  equations, distractors can't equal the answer, parseable numeric values)
  before the document is saved — a broken generation is repaired or refused,
  never persisted with a provably wrong key. (plan 70-C, ADR-158)
- Compose orphan-material awareness: when composing at a topic, materials
  that were uploaded but never placed anywhere are no longer silently
  ignored — the dialog offers an opt-in checkbox to also draw on them, with a
  shortcut to the course materials tab for placing them properly. (plan 70-B)
- Compose coverage honesty: AI-composed documents now measure how much of the
  scope's material retrieval actually surfaced (deterministic accounting, a
  diversified second retrieval round when a large scope is thinly covered)
  and report it — the GenerateDialog result names the shortfall ("Built from
  8 of 14 materials — 6 weren't retrieved.") and flags the document for
  review when coverage stays thin. The same review flag is now surfaced for
  formula sheets, whose "needs review" marker previously had no visible
  consumer. (plan 70-A, ADR-157)

### Changed

### Fixed

- Viewer drawer: no longer clipped off the left edge of the window while the
  chat side panel is docked — the overlay panel was double-inset by the chat
  width (once in the backdrop, once in the panel). It now sits flush against
  the chat dock and clamps to the available width on narrow windows.
- Viewer drawer: the material body is now the single scroll owner — the overlay
  panel no longer keeps a second, competing scrollbar (the inner one previously
  had only a few pixels of travel while the panel did the real scrolling).
- Viewer: display math indented inside list items no longer leaks raw LaTeX as
  red KaTeX errors — the `$$…$$` fence canonicalization now preserves the
  line's indentation instead of emitting a mixed-indent closing fence that
  remark-math rejects (`normalizeMathFences`).

## [v0.8.1] - 2026-09-10

### Added

- GitHub Sponsors funding (Buy Me a Coffee only) via `FUNDING.yml`.

### Changed

- README: direct stable download links for release assets, quick-start reorder,
  family wordmark colophon, new community and security sections, and a Website
  link in the header.
- Release workflow uploads stable-name download aliases next to the versioned
  assets so README links survive future releases.

### Fixed

- Graph chat engine: round-close straggler dropping now applies only to tool
  rounds, so a final answer's trailing token chunks are no longer dropped when
  the round-end flush races the merged token queue (regression from the
  2026-09-09 tool-call leak fix; could truncate streamed answers under load).
