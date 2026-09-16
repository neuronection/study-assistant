# Changelog

All notable changes to **Study Assistant** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Release history from before the public launch lives in the
[git tags](https://github.com/neuronection/study-assistant/tags) and
[GitHub Releases](https://github.com/neuronection/study-assistant/releases).

## [Unreleased]

### Added

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
