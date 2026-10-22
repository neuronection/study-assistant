# Manage web & connected sources

Standing sources surface new study material on their own: feeds, YouTube
channels and playlists, site searches, WebDAV/Nextcloud folders, Google
Drive, Dropbox and OneDrive folders, a local Zotero library, and local Anki
decks. Open **Settings → Tools → Web sources**.

## What a source does

A source is scanned on its schedule (every 15 minutes at fastest, every
6 hours by default). Every new item appears as a **suggestion** in the
Discover dialog — with a keep / import / dismiss choice. Nothing is ever
imported automatically, and no AI is involved in scanning: it is a
deterministic check of the provider.

Suggestions are only suggestions. Accepting one imports that item through
the normal ingestion pipeline; a changed remote file updates its suggestion,
and a file that disappears from the remote folder is marked missing.

## Providers

The provider list is catalog data — every provider below uses the same
connect/scan/suggest flow:

| Provider | Auth | What it reads |
|---|---|---|
| **RSS / Atom feed** | none | feed entries; media enclosures become audio/video suggestions |
| **YouTube channel / playlist** | none | new videos (metadata only — nothing is downloaded until you accept) |
| **Site search** | none | your web-search provider, restricted to one domain |
| **WebDAV / Nextcloud** | app password | a remote folder over PROPFIND/ETag; also usable as a backup destination |
| **Google Drive** | OAuth (browser) | a Drive folder, including Google Docs/Slides/Sheets exports |
| **Dropbox** | OAuth (browser) | a Dropbox folder |
| **OneDrive** | OAuth (browser) | a OneDrive folder |
| **Zotero (local)** | none | a collection from the Zotero desktop app; items arrive citation-complete |
| **AnkiConnect (local)** | none | reviewed cards from selected decks; reviews merge into the due queue |

## Add a source

Press **Add source**, pick a **Provider**, and fill the fields that provider
declares. Common fields: an optional **Label**, an optional **Course** to
file suggestions under, the **Scan interval**, and a **Max items per scan**
cap. Save, then press **Scan now** to see items immediately
(**Scan finished — N new.**).

- **Feed/YouTube/site search** — the feed, channel, or query + domain.
- **WebDAV / Nextcloud** — the folder URL, your username, and an **app
  password**. Use a Nextcloud app password rather than your account
  password. WebDAV folders also get **Back up now** and a remote-backup
  restore button.
- **Google Drive / Dropbox / OneDrive** — optional folder id/path, then
  **Connect**. Your browser opens the provider's consent page; the app
  listens once on `127.0.0.1` for the callback and stores the tokens sealed
  in your OS keyring. **Disconnect** wipes them. Reconnect after the
  provider reports the token expired.
- **Zotero (local)** — the collection key from your Zotero library. Zotero
  must be running; items arrive as citation-bearing link suggestions (DOI,
  authors, year, container) and their PDFs can be imported when attached.
- **AnkiConnect (local)** — one or more deck names, comma-separated. Anki
  must be running with AnkiConnect installed. Reviewing a deck elsewhere
  merges those reviews into the local due queue on the next scan.

## Working with the list

- Each row shows its **Provider**, state (**On** / **Off**), and the last
  scan result. A source that fails once shows **Degraded**; two consecutive
  failures show **Failing**. **Needs setup** means credentials are missing;
  **Reconnect needed** means an OAuth token expired.
- **Scan now** re-checks immediately; the politeness floor still applies
  per source.
- **Edit** changes the label, options and interval; **Delete** removes the
  source. Previously saved or dismissed items stay in their state — a URL
  you already decided on is never re-suggested.
- OAuth sources show **Connect** / **Disconnect**; WebDAV sources show
  **Back up now** and the remote-backup list.
- Suggestions themselves live in the Discover dialog: **Save for later**,
  **Import & parse**, or **Dismiss** — dismissed items can be restored.

## Backup destinations

A WebDAV, Drive, Dropbox or OneDrive source can hold app backups:

- **Back up now** builds a normal `sa-backup/v1` archive and uploads it to
  the configured remote folder.
- The restore button lists remote archives; restoring replaces this app's
  database and files, so restart the app afterwards.

## Good to know

- Overlap protection means slow scans never stack: one scan per source at a
  time.
- Titles from remote providers are cleaned (HTML stripped) and links are
  validated before anything is stored.
- Remote media enclosures respect a MIME allowlist and a size cap; an
  oversized recording still appears as a suggestion but cannot be imported.
- Sources are part of your profile: exporting a course bundle carries its
  sources' settings (provider and options, never credentials or tokens).
- Credentials and OAuth tokens live only in your OS keyring — see
  [Privacy and security](privacy-and-security.md).

Related: [Add a search provider](add-a-search-provider.md) (site searches
need one), [Add an MCP connector](add-an-mcp-connector.md) for code-based
connectors, [Backups, trash & restore](backup.md),
[Extension troubleshooting](extension-troubleshooting.md).
