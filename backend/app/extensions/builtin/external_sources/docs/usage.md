# Usage

## What a scan does

A scan fetches the source, normalizes every new entry and hands it to
the suggestion funnel. Each suggestion carries:

- a **title** (HTML stripped to plain text) and a **link** (re-validated
  as `http(s)` before it is stored),
- a **snippet** capped at 2000 characters (RSS and site search only —
  YouTube entries carry duration and channel instead),
- a **kind** guess: `video`, `course`, `exercise`, `article` or `other`,
  derived from the entry's enclosures and categories,
- the source's **provider line** (`rss:<label>`, `youtube:<label>` or
  `site:<host>`) so you can see where a suggestion came from.

Nothing is downloaded beyond metadata: RSS entries are read from the
feed itself, YouTube listings come from a flat yt-dlp extract (no video
download), and site search returns the provider's result rows.

## Duplicate suppression

Each source keeps a cursor of seen entry ids (capped at the last 1000).
RSS scans also store the feed's `ETag` / `Last-Modified` and send them
back as conditional-GET headers — an unchanged feed answers `304 Not
Modified` and the scan ends without recording anything. Deleting and
re-adding a source starts its cursor fresh, so old entries reappear as
suggestions once.

## Disabling and manual scans

- Toggle a source off to pause its scans; the scheduler skips disabled
  rows and scans return a not-ready error if triggered by hand.
- **Scan now** runs one scan immediately, regardless of cadence.
- The last scan error is kept on the row, so a failing source explains
  itself instead of failing silently.

## Turning suggestions into study material

Suggestions are read-only cards. Use the suggestion's actions to import
it as a material (URL import) or dismiss it. The connector never
imports anything on its own — no scan, schedule or setting changes that.
