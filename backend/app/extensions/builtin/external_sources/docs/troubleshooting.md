# Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Scan fails with `provider error, feed returned 5xx` | The feed's server is erroring | Wait and scan again; the source keeps its cursor, nothing is lost. |
| Scan fails with a `protocol` error and a 4xx code | The feed URL is wrong, gone, or blocking the fetch (401/403/404) | Open the URL in a browser; if it moved, edit the source URL, if it is gone, delete the source. |
| Site-search scan fails with "no search provider configured" | No web-search provider is set up | Connect a provider in **Settings → Tools → Web search**, then scan again. |
| Site-search scan fails with "search provider failed" | The provider (or its network path) is unreachable | Check the provider's status/key in **Settings → Tools → Web search**; the scan is retried on the next tick. |
| YouTube source yields nothing | The channel/playlist URL is a full watch URL or the channel has no public videos | Use the channel or playlist URL (must be `youtube.com` / `youtu.be`); verify videos exist. |
| The same items reappear after re-adding | The seen-cursor lives on the source row; re-adding starts fresh | Expected. Dismiss the repeats or import what you need; they will not return again. |
| A busy feed stops surfacing new items | `max_items` caps how many new suggestions a scan records (default 20) | Raise `max_items` (up to 100) or shorten the scan interval. |
| Snippets look mangled | Feed HTML is stripped to plain text by design | Cosmetic only; titles/links are what the funnel uses. |
| Scan interval seems ignored (too slow) | Intervals below 15 minutes are clamped to 900 s | Use **Scan now** for an immediate pull. |

## Still stuck?

The source row keeps the last scan error verbatim — read it first.
Extension-wide failure modes (registration, MCP servers, discovery) are
covered in the study SDK guide under **Troubleshooting & FAQ**
(`docs/dev/sdk/troubleshooting-and-faq.md` in the repository).
