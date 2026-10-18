# Manage web sources

Standing web sources that surface new study material on their own:
feeds, YouTube channels and playlists, and site searches. Open
**Settings → Tools → Web sources**.

## What a source does

A source is scanned on its schedule (every 15 minutes at fastest,
every 6 hours by default). Every new item appears as a **suggestion**
in the Discover dialog — with a keep / import / dismiss choice.
Nothing is ever imported automatically, and no AI is involved in
scanning: it is a deterministic check of the feed or channel.

## Add a source

Press **Add source** and pick the **Kind**:

| Kind | What to fill | Notes |
|---|---|---|
| **RSS / Atom feed** | the feed URL | lecture podcasts, course blogs, journal feeds |
| **YouTube channel** / **YouTube playlist** | the channel or playlist URL | new videos appear as suggestions; nothing is downloaded |
| **Site search** | a **Search query** and the **Site filter (domain)** | runs your web search restricted to one site — needs a configured [search provider](add-a-search-provider.md) |

Common fields: an optional **Label**, an optional **Course** to file
suggestions under, the **Scan interval**, and a **Max items per scan**
cap. Save, and the first scan runs on schedule — or press **Scan now**
to see items immediately (**Scan finished — N new.**).

## Working with the list

- Each row shows its state (**On** / **Off**), the last scan result,
  and an honest error badge if a scan failed (a dead feed shows its
  last error — one broken source never blocks the others).
- **Scan now** re-checks immediately; the politeness floor still
  applies per source.
- **Edit** changes any field; **Delete** removes the source. Previously
  saved or dismissed items stay in their state — a URL you already
  decided on is never re-suggested.
- Suggestions themselves live in the Discover dialog: **Save for
  later**, **Import & parse**, or **Dismiss** — dismissed items can be
  restored from there.

## Good to know

- Overlap protection means slow scans never stack: one scan per source
  at a time.
- Titles from feeds are cleaned (HTML stripped) and links are
  validated before anything is stored.
- Sources are part of your profile: exporting a course bundle carries
  its sources' settings (not their saved items' content).

Related: [Add a search provider](add-a-search-provider.md) (site
searches need one), [Add an MCP connector](add-an-mcp-connector.md)
for code-based connectors,
[Extension troubleshooting](extension-troubleshooting.md).
