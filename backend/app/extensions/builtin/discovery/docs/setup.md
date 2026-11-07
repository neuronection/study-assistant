# Setup

## Built-in providers

Provider on/off switches and the site presets live in
**Settings → Tools → Discovery**:

- **Web** — runs the query through your configured web-search
  providers (managed in **Settings → Tools → Web search**). With no
  provider configured, the web leg is skipped silently.
- **YouTube** — yt-dlp flat video search, no API key. On by default.
- **Site presets** — a list of `(site, label)` pairs queried as
  `"<query> site:<host>"`. The default preset is Khan Academy; presets
  are data, not scrapers — they go through the same web-search legs.

Web and YouTube are enabled out of the box; a fresh profile starts
with `web`, `youtube` and the Khan Academy preset.

## MCP legs

An external MCP server contributes a discovery leg when three things
line up:

1. The server is registered in **Settings → Tools → Connectors**
   (transport, command/URL, optional sealed token — see the mcp
   connector's docs).
2. The server is **enabled**.
3. At least one of its tools is enabled with the **`discovery`**
   contract (set per tool after a refresh).

The tool then appears to the registry as the provider
`mcp.<server-name>.<tool-name>`. Tools with the `parse` contract feed
URL import instead and never join the discovery fan-out.
