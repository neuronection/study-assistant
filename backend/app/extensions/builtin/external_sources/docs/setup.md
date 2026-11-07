# Setup

All sources are managed in **Settings → Tools → Web sources**. One row
is one source; every source needs a kind, a URL and (optionally) a
label and a course to attach suggestions to.

## Add a source

1. Open **Settings → Tools → Web sources** and press **Add source**.
2. Pick the kind:

   | Kind | URL shape | Extra options |
   |---|---|---|
   | `rss` | any `http(s)` feed URL | `max_items` (1–100, default 20) |
   | `youtube_channel` | a `youtube.com` / `youtu.be` channel URL | `max_items` |
   | `youtube_playlist` | a `youtube.com` playlist URL | `max_items` |
   | `site_search` | any `http(s)` site URL | `query` (required, ≤300 chars), `site` (optional host filter) |

3. Paste the URL. URLs must be `http(s)`; the YouTube kinds additionally
   require a `youtube.com` / `youtu.be` host — anything else is rejected
   at save time.
4. Optionally pick a course: suggestions from this source are then
   attached to it, so they surface where you study that subject.
5. Save. The first scan runs on the next scheduler tick, or immediately
   via **Scan now**.

## Scan interval

Every source carries its own cadence. The minimum is **15 minutes**
(900 seconds — anything lower is clamped); the default is **6 hours**.
An RSS source that publishes daily does not need a faster cadence than
an hour; a busy announcement feed is fine at 15–30 minutes.

## Site-search prerequisites

`site_search` sources ride the bundled web-search trio: they run the
query `"<query> site:<host>"` through your configured search provider.
If no provider is configured, the scan fails with a not-ready error
that tells you to connect one in **Settings → Tools → Web search**.
