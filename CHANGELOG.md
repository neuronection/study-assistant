# Changelog

All notable changes to **Study Assistant** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Release history from before the public launch lives in the
[git tags](https://github.com/neuronection/study-assistant/tags) and
[GitHub Releases](https://github.com/neuronection/study-assistant/releases).

## [Unreleased]

### Added

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
