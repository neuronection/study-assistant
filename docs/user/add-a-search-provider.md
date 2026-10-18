# Add a search provider

The web search behind the tutor's research tools and the Discover
dialog. Open **Settings → Tools → Web search** (the **Web search
providers** section).

## Add a provider

1. Press **Add provider**.
2. Pick the **Provider type**:
   - **Tavily**, **Brave**, **Exa**, **Serper (Google)**, **Google
     Programmable Search** — hosted services; paste the **API key**
     from the linked console. Google Programmable Search also needs
     the **Engine id (cx)**.
   - **SearXNG** — self-hosted metasearch; no key, but the **Base URL**
     of your instance is required (the hosted types work without one).
3. Optional: a display **Name**, a custom **Base URL** (for a
   compatible endpoint), and result/timeout tuning.
4. Save — the key goes straight into your operating system's keyring
   and is only ever shown masked (`••••1234`). Deleting a provider
   removes its key from the keyring too.

## Test it

Each provider row has a test button that runs one small search and
shows the verdict: **Reachable** (with latency and result count),
**Unreachable**, **API key rejected**, **Rate limited**, **JSON format
disabled on the instance** (SearXNG — enable the JSON format in its
`settings.yml`), or **Test failed**.

## Order is fallback order

Providers work as an ordered list: **the first enabled provider that
answers wins**. Put the fastest one first and keep a second as a
backup — if the first fails, the next one is tried, and a provider you
disable is skipped entirely. Use **Move up** / **Move down** to
reorder.

## What uses it

- The tutor's **SEARCH** and **FETCH** research tools in chat.
- The **Web** provider and site presets in the Discover dialog
  (Settings → Tools → Discovery lets you choose which are active).
- **Site search** web sources (see
  [Manage web sources](manage-web-sources.md)).

If no provider is configured, these features simply skip web search —
nothing breaks, and the panel says so.

Related: [Add an MCP connector](add-an-mcp-connector.md) for
code-based sources, [Extension troubleshooting](extension-troubleshooting.md)
for error decoding.
