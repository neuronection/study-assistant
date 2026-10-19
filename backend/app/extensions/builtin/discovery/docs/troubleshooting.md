# Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Web results never appear | No search provider configured, or all are disabled | Configure one in **Settings → Tools → Web search**; the web leg skips silently when none is present. |
| YouTube results never appear | The `youtube` provider is disabled | Re-enable it in **Settings → Tools → Discovery**. |
| An MCP leg never fires | Server disabled, or no tool enabled with the `discovery` contract | Enable the server, refresh, then set the tool's contract to `discovery` (see the mcp connector's docs). |
| An MCP leg errors every call | The tool returns non-JSON text or the server is down | Check the server row's last error; the tool must return JSON (a list or `{"results": [...]}`). |
| MCP rows are missing from an otherwise successful call | Rows without a title or with a non-`http(s)` URL are dropped by design | Fix the server's row shape; valid rows carry `title` + `url` at minimum. |
| Site preset returns generic web results | The preset runs `site:` through the web-search legs | That is expected — presets are query filters, not site-specific APIs. |
| Results differ between runs | Providers race and caps trim; order is not a ranking promise | Expected; run again or narrow the query. |

## Still stuck?

The DISCOVER tool's tool-level failure modes (timeouts, per-call caps)
surface in chat as tool errors. The study SDK guide's
**Troubleshooting & FAQ** chapter (`docs/dev/sdk/troubleshooting-and-faq.md`
in the repository) covers the registry- and connector-level failures.
