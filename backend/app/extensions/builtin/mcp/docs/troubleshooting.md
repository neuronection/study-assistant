# Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Refresh fails with "spawn" or timeout errors (stdio) | The command is wrong, not executable, or the server crashes on start | Run the command by hand in a terminal; fix the path/args, then refresh again. |
| Refresh fails on `http`/`sse` | The URL is unreachable, not an MCP endpoint, or TLS-blocked | Open the URL; check scheme (`http(s)` only) and that the server speaks MCP. |
| The server row shows a red/failing status | The last refresh or call failed | Read the row's last error; it keeps the failure verbatim. |
| "a http(s) URL is required for remote servers" | An `http`/`sse` server was saved without a URL, or with a non-http scheme | Edit the row and set the URL. |
| "command is required for stdio servers" | A `stdio` server was saved without a command | Edit the row and set the command. |
| A tool disappeared after refresh | The server stopped offering it | Expected — the row mirrors the server's current tool list; re-enable if it returns. |
| A tool never gets called in discovery | The tool's contract is `none` (default after refresh), or the server is disabled | Set the contract to `discovery` and enable server + tool. |
| A parse tool never fires on import | The page URL does not match the tool's URL pattern | Fix the pattern (≤300 chars) on the tool row. |
| "unknown tool '<name>' — refresh first" | The tool was patched before the server was ever refreshed | Refresh once, then edit tools. |
| "at most 10 servers can be registered" | The per-profile server cap | Delete a server you no longer use. |
| Token/env edits seem ignored | Values are sealed to the keyring, not shown back | The key chip on the row reflects presence; re-save to replace, tick the clear box to delete. |
| Tool calls time out at ~30 s | The per-call timeout elapsed (default 30) | Raise the server's timeout (up to 120 s) or make the tool faster. |

## Still stuck?

MCP spawn-level behavior is pinned end-to-end by the repo's real-subprocess
e2e wall (`test_mcp_connectors.py`); the study SDK guide's
**Troubleshooting & FAQ** chapter (`docs/dev/sdk/troubleshooting-and-faq.md`
in the repository) covers the connector- and registry-level failures.
