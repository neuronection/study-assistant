# Cloud calendars — implementation notes

Family law: [ADR-0052] (cloud accounts) and
[`guidelines/cloud-connectors.md`]. This page is the study-host map; the
canonical catalog and engines are vendored byte-identically from the
family contract canonical.

## Where the code lives

| Piece | Path |
|---|---|
| Vendored catalog + engines | `backend/app/extensions/cloud/` (never edit) |
| Host adapter (rows, custody, OAuth, mapping, sync) | `backend/app/services/study/calendar_sync.py` |
| API | `backend/app/api/calendar.py` |
| Models | `backend/app/domain/models/study.py` (`CalendarLink`, `CalendarEventLink`) |
| Migration | `backend/alembic/versions/0009_calendar_links.py` |
| Secret custody | `app/core/secrets.py` (OS keyring + at-rest cipher) |
| OAuth primitives | `nx_auth.oauth` (kit: PKCE S256, single-use profile-bound state, sealed token vault) via `app/services/study/cloud_oauth.py` |
| Settings surface | `frontend/src/features/settings/CalendarCard.tsx` |

## Mapping law

- Project only `exam`, `deadline`, `milestone`.
- All-day event; canonical end is exclusive (`due_date + 1 day`).
- Category = upper-case kind (`EXAM`, `DEADLINE`, `MILESTONE`).
- UID = `study:<plan-item-id>` (stable across renames).
- Completed items are tombstones: the remote event is deleted, the plan item
  stays.
- Pull accepts only events whose categories intersect the link's
  `acceptCategories`, or every event when `options.acceptAll` is true. Inbound
  events become `origin='calendar'` plan items; they are never auto-completed.

## Persistence

`calendar_links` is the credential binding: provider, protocol location,
direction, scopes, secret **pointer**, status, failures, cursor, options. No
token column exists. `calendar_event_links` is the per-link identity map
(`uid`, `remoteId`, `etag`, `local_hash`, `remote_hash`), unique on
`(link_id, uid)`. The two hash pins are E3 law: providers normalize on write,
so one shared hash would read back as "changed" on every run forever; each
side compares against its own pin.

## Sync

`calendar_sync.sync_link` builds the transport from the catalog protocol, lists
a bounded window (14 days back / 400 forward), calls the engine's pure
`reconcile` (window-aware per E5: an out-of-window link is absent, not
deleted — it is skipped, never unlinked), applies the actions, and writes
health. The conflict default is `skip` (surface a `conflict` action) and the
deletion default is `keep-local` — neither is clock-based (C2/E4). One
`asyncio.Lock` per link serializes runs. Failures map to the family status
vocabulary and stop at the cap.

## Network guard

`calendar_sync._guarded_client` wraps every sync/test request: the host must
match the catalog's declared domains (or, for a self-hosted CalDAV/WebDAV/ICS
binding, the base host the user supplied), and `polite_http.assert_safe_url`
runs on every request; the checked address is pinned with the original `Host`
header + SNI. Private addresses are allowed only for self-hosted bindings —
a Google/Microsoft binding can never resolve to a LAN address. Calendar writes
skip the GET-only politeness layer (robots, conditional GET) but never the
SSRF check.

## Data-driven setup (plan 52 §12 / Rev 4)

The bind form knows no provider names. `calendar_sync.setup_fields(provider)`
derives each row's form fields from catalog data — the row's `protocol`,
`authKinds` and `baseUrlRequired` — and the API ships them as `setup_fields`
on `GET /api/v1/calendar/providers`. Field shape:

| Key | Meaning |
|---|---|
| `key` | `CalendarLinkIn` payload key the field feeds (`base_url`, `calendar_url`, `username`, `secret`, `calendar`) |
| `kind` | input kind: `url`, `text`, `secret`, `calendar` (the discovery-backed picker) |
| `required` | form-level requirement |
| `label_key` | i18n suffix under `settings.calendar.` — user copy never comes from the backend |
| `auth_kind` | render only when this auth kind is chosen (`null` = always) |
| `manual_key` | payload key for a manual paste fallback (`calendar_url` on CalDAV; OAuth providers pick from the list only) |

Derivation rules: CalDAV → base URL (required when `baseUrlRequired`),
username + secret per auth kind, picker with manual fallback; ICS → feed URL +
token secret when offered; `google-calendar`/`graph-calendar` → picker only.
When a row offers more than one auth kind the form shows a sign-in-method
selector and `CalendarLinkIn` carries the chosen `auth_kind` (validated
against the row's `authKinds` — a token bind binds as a token, with its own
keyring slot). **Adding a provider that speaks an existing protocol needs no
frontend change.** The frontend (`CalendarCard`) renders `setup_fields`
verbatim and holds no `if provider === "x"` branch; protocol adapters stay
server-side.

Where this should live long-term: the descriptor is derived, not stored — the
canonical catalog (the family cloud-providers contract) could grow an
explicit `setupFields` block per row, and this mapper would then validate
against it instead of deriving. Until that lands, this file is the study-host
derivation and any new protocol needs a case in `setup_fields` (code, not
data — protocols are code).

## Calendar discovery (plan 52 §9 M1)

`POST /api/v1/calendar/links/discover` lists an account's calendars for the
picker. Request: either `link_id` (discovery rides the stored credential of a
connected link) or bind-form fields (`provider`, `auth_kind`, `base_url`,
`calendar_url`, `username`, `secret`) held in memory for this one request —
**never persisted, never echoed back**. OAuth providers require `link_id`
(their tokens exist only under a connected link). Response:
`{"calendars": [{"id", "name", "url", "primary"}]}` where `url` (CalDAV
collection href) is sanitized to scheme+host+path, names are truncated, and
the list is capped at 50 rows. Transports: CalDAV PROPFIND via the engine's
`discover_calendars`, Google `users/me/calendarList`, Graph `me/calendars`.
Errors are typed (`needs-secret`, `provider`, `unsupported`) and carry no
credential material.

## OAuth

`oauth_start` stores `{state, verifier, profile, created, scopes}` in the
keyring under `calendar:<id>:pending` and returns the authorize URL + loopback
redirect. `oauth_complete` enforces the Rev 3 E12 law: **`state` is bound to
the profile** (a mismatch refuses the flow), **single-use** — the pending slot
is consumed on every outcome (success, expiry, profile mismatch, state
mismatch), so a replay can never complete — and expires after 10 minutes. It
then exchanges the code once, seals the token set under `calendar:<id>:oauth`,
and clears the pending slot. The frontend opens the authorize URL and pastes
the code — the documented fallback for environments where a local loopback
listener is not available; the state verifier is still enforced server-side.

**OAuth implementation.** Study uses the family kit's `nx_auth.oauth`
(`cloud_oauth.py` adapts study's keyring + at-rest cipher to the kit's
`StateStore`/`SealedStore`/`TokenTransport` seams). The state is single-use,
profile-bound and expiring; the token set is sealed under
`calendar:<id>:oauth`; the pending slot is cleared on every outcome. The
frontend opens the authorize URL and pastes the code — the documented fallback
for environments where a local loopback listener is not available; the state
verifier is still enforced server-side.

Client ids come from `SA_GOOGLE_CLIENT_ID` / `SA_MICROSOFT_CLIENT_ID`
(+ `_SECRET` where the deployment registered a confidential client). A missing
id is a typed `needs-config`, never a crash.

## Tests

- `backend/tests/test_calendar_sync.py` — mapping, custody, idempotency, and
  the host-side contract pins: the `local_hash`/`remote_hash` two-pin schema,
  the `skip` conflict default, window-aware reconcile (out-of-window links
  stay linked), private-ICS URL custody (full URL in the keyring, row keeps
  scheme+host+path), descriptor-driven setup fields, the discovery endpoint
  (bounded, credential-free) and the profile-bound single-use OAuth state.
- The vendored fixture wall (`cloud-connectors.fixtures.json`) runs in the
  backend suite via `tests/test_cloud_contract.py`; the canonical changes
  fail here before they reach a user.
- Frontend: `CalendarCard` tests pin the descriptor-driven bind form (no
  provider branches), the picker, and the auth-kind swap; typecheck and the
  settings map wall cover placement (the card lives under `tools.connectors`,
  so the settings nav contract is unchanged).

## Deployment modes: desktop vs web (plan 52 fix)

Two things differ between a desktop install and a web/server deployment, and
**both fail silently** if ignored.

| Concern | Desktop/local | Web/server |
|---|---|---|
| Credential storage | OS keyring | sealed file `<data_dir>/secrets.json` (0600, `nx_auth.atrest`) |
| OAuth redirect | loopback `http://127.0.0.1:<port>/oauth/callback` (RFC 8252) | `{SA_APP_URL}/api/v1/calendar/oauth/callback` |

**Storage.** `app/core/secrets.py` probe-selects the backend: the keyring is
used only if a write **round-trips**, else the sealed file, else it **fails
closed**. The probe matters because `keyring.backends.null` accepts writes and
discards them — without it a bind "succeeds" and the token is simply gone.
`store_backend()` reports which is live (`keyring` | `file` | `none`).

**Redirect.** Set `SA_APP_URL` (the public base URL) on any web deployment.
Without it OAuth uses the loopback redirect, which only works when the browser
and the app share a machine — the provider would otherwise send the code to
the *user's own* localhost. The server callback route's security is the state
law: single-use, expiring, bound to the profile that started it. The state is
a `<link-id>.<nonce>` composite so the callback can find the binding; the
nonce does the security work.

## Identity & the delta fast path (E9 / M4)

Two rules that only bite in production:

**The link row is the identity authority.** `CalendarEventLink.uid` is the
LOCAL uid (`study:plan-item:<id>` / `health:examination:<id>`); the provider's
handle lives in `remote_id`/`etag`. This is load-bearing: **Graph's `iCalUId`
is server-generated and read-only**, so the provider can hand back a different
uid for an event we created. Matching by uid alone split one event into
`unlink` + `create-remote` — a duplicate every sync. The remote side is
matched by write handle, falling back to uid.

**Orphan repair.** A local record with no link may already have a remote twin
(the link write was lost in a crash between the provider write and our
commit). `reconcile` matches those by content hash and emits `LINK_EXISTING`
— attach, never create. Graph has no idempotency key, so this is what closes
the crash window there.

**A delta cursor is a probe, never the remote view.** A delta listing returns
only *changed* events. Feeding it to `reconcile` as the remote set reads every
unchanged event as "vanished" and unlinks it. The cursor is used to
short-circuit the run when the provider reports no changes; any change
(including a tombstone) falls through to the full window; a dead cursor is
dropped and the run resyncs — never a failure.

## Common pitfalls

- Do not hand-write a provider or scope list — read the catalog. The bind
  form's fields come from `setup_fields`; adding a protocol case is backend
  code, adding a provider is a catalog row and nothing else.
- Do not add a token column; another secret is another keyring slot. A URL
  with a query string is a secret too — full URL to the keyring, sanitized
  address in the row and in every discovery response.
- Do not project every plan item; that is the noise the mapping law exists to
  prevent.
- Do not pull without an acceptance predicate.
- Do not store the provider's uid in the link row — it is not an identity.
- Do not feed a delta result to `reconcile` as the remote view.
