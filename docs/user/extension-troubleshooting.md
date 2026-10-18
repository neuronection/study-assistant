# Extension troubleshooting

Fixes for the Tools tab surfaces — search providers, web sources, MCP
connectors, and the Discover suggestions they feed. For AI-provider
problems, see [Troubleshooting](troubleshooting.md) instead.

## A search provider's test fails

| Message on the row | What it means | Fix |
|---|---|---|
| **Unreachable** | the endpoint did not answer | check the base URL; the service may be down |
| **API key rejected** | wrong, expired, or wrong-vendor key | re-paste the key from the provider's console |
| **Rate limited** | quota window exhausted | wait and retry; lower results per search |
| **JSON format disabled on the instance** | SearXNG without its JSON format | on the SearXNG instance: `settings.yml` → `search.formats: [json]` |
| **Test failed** | anything else | the row's detail shows the raw reason |

Searches quietly use the **first enabled provider that answers** — if
results stop, test the first enabled row, not the last one added.

## A web source shows an error badge

- **Dead or moved feed** — the badge shows the last error; fix the URL
  via **Edit** or delete the source. Other sources keep scanning.
- **Site search finds nothing** — it needs a working
  [search provider](add-a-search-provider.md); test the provider first.
- **Nothing new appears** — that can simply be true (nothing new was
  published). **Scan now** shows the count; items you already saved or
  dismissed are never re-suggested.

## An MCP connector misbehaves

Open **Settings → Tools → Integrations** and read the server's health
line:

- **Degraded** — the last refresh failed; the row shows the error.
  Common causes: the command path is wrong, the interpreter is missing
  dependencies, or the server crashed at start. Run the same command
  in a terminal to see its real error, then **Refresh** again — your
  settings survive the failure.
- **Stale** — not refreshed in over 24 hours; press **Refresh**.
- **Incomplete configuration** — a required field is missing for the
  transport (a stdio server needs a command; a remote one needs a
  URL). **Edit** and complete it.
- Tools listed but greyed out — they are switched off or have **No
  contract**; enable the ones you want and give each a **Discovery**
  or **Parser** contract ([how](add-an-mcp-connector.md)).

## A discovery tool returns fewer results than expected

That is usually the safety rail, not a bug: rows without a title or
with a broken link are dropped before they reach you. If a source you
trust returns too little, the tool's author needs to fix its rows —
the app never fills gaps or guesses.

## An import used the wrong parser

If importing a page from a site with a **Parser**-contract tool landed
as a plain web page, the tool's **URL pattern** did not match that
address (patterns match the site and path, not query parameters).
Check the pattern in the server's tool list. If *every* page of a site
should go through the tool, widen the pattern — but not so wide that
it captures addresses you wanted the built-in parser to handle.

## Suggestions

- **Where did my suggestion go?** Saved and dismissed items stay in
  the Discover dialog under its saved/dismissed section — restore
  from there.
- **Nothing appears from a connector** — is the server **On** and at
  least one tool enabled with the **Discovery** contract? Refresh
  lists tools but never enables them.

Still stuck? [Add an MCP connector](add-an-mcp-connector.md) and
[Manage web sources](manage-web-sources.md) walk the full setup, and
the [settings reference](settings.md) maps every Tools tab section.
