# Add a search provider

The web search behind the tutor's research tools and the Discover
dialog. Open **Settings → Tools → Web search** (the **Web search
providers** section). It works like the AI provider screens: configured
providers render as cards, and every management action (enable,
reorder, test, edit, delete) lives in the card's **⋯** menu.

## Add a provider

1. Press **Add provider** — a two-step wizard opens.
2. **Choose provider**: pick a tile —
   - **Tavily**, **Brave**, **Exa**, **Serper (Google)**, **Google
     Programmable Search** — hosted services; the form links to the
     console where you get the **API key**. Google Programmable Search
     also needs the **Engine id (cx)**.
   - **SearXNG** — self-hosted metasearch; no key, but the **Base URL**
     of your instance is required (the hosted types work without one).
3. **Configure**: paste the key (it goes straight into your operating
   system's keyring and is only ever shown masked, `••••1234`). The
   main form stays minimal — everything optional (display **Name**, a
   custom **Base URL** for a compatible endpoint, result-count and
   timeout tuning) lives under **Advanced**. The name is pre-filled
   from the provider's label and numbered when that name is taken.
4. Save — deleting a provider removes its key from the keyring too,
   after a confirmation.

## Edit or remove a provider

Open the **⋯** menu on a provider card and pick **Edit provider** —
the same form opens pre-filled, with the stored key kept unless you
type a new one (**Clear stored key** removes it). **Enable** /
**Disable**, **Move up** / **Move down**, **Test** and **Delete** live
in the same menu.

## Test it

Each card shows the connection state at a glance (**Not tested**,
**Reachable** with latency, or **Failed** with the error detail). Pick
**Test** in the **⋯** menu to run one small search against the
provider.

## Order is fallback order

Providers work as an ordered list — the priority badge on each card is
its position: **the first enabled provider that answers wins**. Put
the fastest one first and keep a second as a backup — if the first
fails, the next one is tried, and a provider you disable is skipped
entirely.

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
