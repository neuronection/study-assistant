# Overview

The **external web sources** connector polls web sources you configure —
RSS/Atom feeds, YouTube channels and playlists, and site-filtered web
searches — on a schedule. Every new item it finds lands in the app as a
*suggestion*: a card with title, link and snippet you can turn into
material with one click. It never writes materials, notes or flashcards
on its own, and it never asks a language model anything.

- **Four source kinds** — `rss`, `youtube_channel`, `youtube_playlist`
  and `site_search`, one URL each.
- **Suggestions only** — scan output flows into the suggestion funnel;
  you decide what becomes a material.
- **No credentials** — the connector declares only the `sync`
  capability. It fetches URLs you configured; there is no fixed domain
  allowlist to grant, and no API keys to store.

## When to use it

- You follow a blog, podcast feed or course announcement feed and want
  new posts to appear as study suggestions.
- You want new videos from a YouTube channel or playlist to show up
  without opening YouTube.
- You want a periodic "what's new on this site" search (for example
  new exercises on a practice site) folded into the same stream.

## When NOT to use it

- You need one-shot search inside chat — that is the DISCOVER tool of
  the bundled discovery connector, not a scheduled source.
- You need deep page content (full text, PDFs) — sources only carry
  title, link and a capped snippet; import the material for the rest.
- The site requires login or an API key — sources are anonymous HTTP
  fetches; authenticated platforms are out of scope by design.
