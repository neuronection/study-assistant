"""Family cloud-connector contract (ADR-0052).

The modules in this package are vendored byte-identical from
``dev/contracts/cloud_*.py`` + ``dev/contracts/cloud-providers.json`` via
``dev/scripts/sync-cloud-connectors.sh`` (ADR-0031). Never edit them here —
change the canonical copy in the dev repo and re-run the sync.

Study's host-side adapter lives in
:mod:`app.services.study.calendar_sync`; this package is only the shared
engine (event model, ICS/CalDAV/Google/Graph transports, reconcile).
"""
