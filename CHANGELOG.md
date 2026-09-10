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
