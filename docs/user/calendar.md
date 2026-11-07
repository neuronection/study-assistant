# Cloud calendars (exams, deadlines and study events)

Study Assistant can bind a course to your own calendar so exam, deadline and
milestone dates appear where you already plan your week — and, if you want,
pull study events back into the course plan.

## What gets projected

Only three plan kinds are published by default:

| Plan kind | Calendar event |
|---|---|
| `exam` | all-day event on the due date |
| `deadline` | all-day event on the due date |
| `milestone` | all-day event on the due date |

Ordinary study, practice and review tasks stay private. An all-day event's end
is the day *after* the due date (the iCalendar convention), so it renders as a
single day.

Two-way sync is **opt-in**. A pull only accepts events whose categories mark
them as study events (`EXAM`, `EXAMINATION`, `DEADLINE`, `MIDTERM`, `FINAL`) or
a link you explicitly marked "accept all". Your whole personal calendar is
never imported.

## Providers

Providers, their scopes and their setup fields come from the family catalog,
not from this app: Google Calendar, Microsoft 365, Nextcloud, iCloud, Fastmail,
generic CalDAV, and read-only ICS feeds. The bind form renders whatever fields
your provider needs — if a provider is added to the catalog, it appears in the
form with no app update.

- **CalDAV providers** (Nextcloud, iCloud, Fastmail, self-hosted) use your
  username and an **app password** (or, on generic CalDAV, an access token).
  Fill the form and press **Find calendars**: the app lists the account's
  calendars and you pick one instead of pasting a collection URL. Pasting a
  URL by hand still works. Create a dedicated app password at the provider;
  revoke it there to disconnect.
- **ICS feeds** are read-only subscriptions. Paste the feed URL. A private
  feed URL carries a token in its query string; the app stores that full URL
  only in the OS keyring and keeps the sanitized address (host + path) in the
  database, so the token never appears in the link row or the UI.
- **Google / Microsoft** use OAuth. A deployment administrator registers an
  OAuth client for this app and sets `SA_GOOGLE_CLIENT_ID` /
  `SA_MICROSOFT_CLIENT_ID` (plus `_SECRET` for a confidential client) — the
  redirect URI is `http://127.0.0.1:<port>/oauth/callback` on desktop, or
  `{SA_APP_URL}/api/v1/calendar/oauth/callback` in web mode. Without a client
  id the bind form reports `needs-config` instead of opening a consent screen.
  Saving the link then opens the consent screen; after approving, paste the
  authorization code back into the card. Google binds your primary calendar;
  use **Choose calendar** on the link to pick a specific one (Microsoft links
  need this — they have no "primary"). The app requests only the scopes needed
  for the direction you chose (read for pull, read + write for push/two-way).

## Where credentials live

Only in your OS keyring, under `calendar:<link-id>:…`. The database stores a
pointer and metadata, never a token. Logs, exports and backups exclude them.
Disconnecting deletes the keyring entries and the link — your plan items and
courses stay. Revoke the app password or the provider grant at the provider if
you want the remote access cancelled immediately too.

## Using it

1. Settings → Tools → Connectors → **Cloud calendars**.
2. **Bind a calendar**, pick the course, provider and direction; fill the
   fields the catalog asks for and pick a calendar from the **Find calendars**
   list (or paste a URL where a picker is not available); save.
3. For OAuth, click **Connect account**, approve in the browser, paste the code
   and press **Finish connection**. Use **Choose calendar** on the bound link
   to point it at a specific calendar.
4. Use **Test** for a read-only check and **Sync now** to run the sync.
5. Disconnect with the trash button. Nothing else is deleted.

Status follows the family vocabulary: `ok`, `degraded`, `failing`, `stale`,
plus `needs-auth` and `needs-secret` when the credential needs attention. A
failed sync shows its last error and stops rather than retrying forever.

## Privacy

The projected event contains the plan title, date and the category (the plan
kind). It contains no notes, no course description and no material. If a title
is sensitive, rename the plan item — the calendar sees what you name it.
