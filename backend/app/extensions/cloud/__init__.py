"""Family cloud-connector contract (ADR-0052).

The modules in this package are vendored byte-identical from
``the family contract canonical/cloud_*.py`` +
``the family contract canonical/cloud-providers.json`` via
``the family sync tooling`` (ADR-0031). Never edit them here —
change the canonical copy in the the family standards repo and re-run the sync.

Study's host-side adapter lives in
:mod:`app.services.study.calendar_sync`; this package is only the shared
engine (event model, ICS/CalDAV/Google/Graph transports, reconcile).
"""
