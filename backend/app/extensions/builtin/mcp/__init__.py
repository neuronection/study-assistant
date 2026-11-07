"""Bundled ``mcp`` connector (T3 in the tier ladder).

The machinery is core subsystem code — :mod:`app.extensions.mcp_servers`
(the D19 instance lifecycle over the ``mcp.servers`` preference rows) and
:mod:`app.ai.mcp_client` (the AI-layer client, fastmcp/mcp imports stay
where ADR-0012 law puts them). Each connected server is one INSTANCE of
this connector: own config, sealed keyring token/env slots (x-secret
declared in ``manifest.json``), per-tool allowlist, enable state, status
and audit rows. The T3 perimeter disclosure renders verbatim from the
vendored charter (``consent.t3PerimeterDisclosure``) on the instance
surface.
"""
