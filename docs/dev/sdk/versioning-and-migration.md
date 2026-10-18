# Versioning & migration

What changes how, and what that does to a configured instance.

## The envelope policy

Every manifest — the three bundled ones and any future artifact —
declares `apiVersion: "extension/v1"` and a per-kind `kindVersion`.
`extension/v1` is frozen: fields are added, never repurposed; unknown
envelope fields are validation errors (closed objects), so a future
reader either understands a manifest completely or rejects it loudly.

## Append-only vocabularies

The vocabularies this set documents are wire law, and they only grow:

- **charter codes and capabilities** — closed sets in the vendored
  charter; a new code or capability lands family-wide via the dev
  canonical, and a bundled manifest declaring something the study host
  profile does not honor self-disables at registration (fails closed).
- **tool contracts** (`none | discovery | parse`), **transports**
  (`stdio | http | sse`), **instance statuses** (`ok | degraded |
  failing | stale`), **discovery kinds**, **search provider types and
  error kinds** — adding a value is a family wave (the vendored trio
  changes in lockstep with desktop's TS adapters and the fixture
  wall); removing or renaming one is a breaking change (below).

## The ADR-0035 sync law

The web-search trio, the charter set, and the docs-tree contract are
**byte-identical vendored copies** — never edited in-repo. The law, in
one line each:

- change the **dev canonical** (`dev/contracts/search_providers.py`,
  `dev/contracts/…`), then run the sync script
  (`dev/scripts/sync-search-providers.sh` /
  `sync-extension-contract.sh`) and commit both sides together;
- drift is a gate failure (`--check`, wired into `verify-wiring.sh`),
  not a merge conflict to resolve by hand;
- the vendored `SearchError` taxonomy maps onto the charter codes
  app-side (the D4 projection) precisely so the canonical enum can keep
  its wire contract — converging the enum itself is a charter-owner
  decision, recorded in the charter's `legacyMappingNote`, never taken
  in a product commit.

The same discipline covers this doc set's own tree:
`docs/dev/sdk/docs-tree.json` validates against the vendored
`contracts/docs-tree.schema.json` (the tree gate
`backend/tests/test_extension_docs_tree.py` runs the contract's fixture
suite through the vendored validator).

## Breaking changes and your instances

- **A major bump of a bundled connector** (say `discovery` v2) does not
  migrate instances in place: the registry validates at registration,
  so an incompatible manifest simply fails boot loudly — bundled
  manifests ship in the same commit as the code they describe.
- **Your MCP server changing its tool signature** is *your* breaking
  change: study pins nothing about your tools except the two contract
  shapes. A tool that stops matching its declared contract surfaces as
  dropped rows (discovery) or failed imports (parse) — refresh to
  re-list tools, re-declare, and re-test with one search or one import
  before trusting it again.
- **Removing a provider type or contract value from the catalog** would
  strand configured rows — which is why the vocabulary is append-only.
  A removed *provider row* (you deleted it) cleans its keyring slot in
  the same call; nothing else leaks.

## The no-shims doctrine

Old shapes are deleted in the adopting commit, not shimmed: the lazy
migration from the pre-plan-28 single-provider preference rewrote rows
once and dropped the old key; the legacy keyring slot moved with it.
There is no compatibility layer to target — write against the shapes
in [Reference](reference.md) as they are today.
