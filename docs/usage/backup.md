# Backups, trash & restore

Your data lives in the app data folder (`~/.local/share/StudyAssistant/` unless
`SA_DATA_DIR` says otherwise): a SQLite database plus the originals in a
content-addressed blob store. Everything below protects exactly that folder.

## Trash (7-day undo for deletes)

Deleting a **note, quiz, exercise or chat** moves a full snapshot of it (with
its children — questions, attempts, drawings, messages, review history) into
the **Trash** instead of destroying it:

- Every delete shows a short **Deleted — Undo** strip; clicking Undo restores
  the item immediately, exactly as it was (same placements).
- Settings → Data → **Trash** lists everything with a Restore and a
  Delete-forever action.
- Items are kept for **7 days**, then purged automatically.

**Deleting a course** is too big for the Trash — instead the app **creates a
full backup first** (visible in Settings → Data → backups list) and then purges
the course. If you ever need it back, restore that backup.

## Automatic backups (default: on)

The app backs itself up — you don't have to remember anything:

- A **full backup** (consistent database snapshot + all originals + manifest)
  is written to the `backups/` subfolder of the data directory, **once shortly
  after startup** and then every **interval hours** (default 24) while the app
  runs.
- **Retention:** the newest 14 daily backups are always kept (default), plus
  one per week for the last 8 weeks. Older ones rotate out automatically.
- **Validation:** every archive is re-opened and its database
  integrity-checked after writing — a corrupt backup is discarded immediately.
- **Boot check:** if the database is ever found corrupt at startup, the corrupt
  file is preserved as `corrupt-<timestamp>.db`, the newest *valid* backup is
  restored automatically, and Settings → Data shows what happened.

### Off-machine copies (sync folder)

In **Settings → Data → Automatic backups** you can set a **sync folder**
(e.g. a Nextcloud/Dropbox directory). Every backup is copied there atomically
(after the same retention rules), so a synced peer gives you an off-machine
copy with zero extra tooling. Leave it empty to disable.

The same card lets you: turn automatic backups off, change the interval and
retention, run **Back up now**, and **restore or delete** any listed backup.
Restoring replaces the current database and originals entirely — it asks for
confirmation first.

## Manual export / import

Still in Settings → Data:

- **Download backup** exports the same full archive as a `.zip` download
  (useful before big changes or to migrate machines).
- **Restore from file** uploads a backup archive. It's validated (format,
  integrity, migration history) before anything is touched; then the database
  and originals are replaced and migrations re-run.

## Environment variables

Defaults can be pinned via `SA_*` variables (UI changes in Settings → Data
override them and are stored in `backup-settings.json` in the data dir):

| Variable | Default | Meaning |
|---|---|---|
| `SA_AUTO_BACKUP` | `true` | automatic backups on/off |
| `SA_BACKUP_INTERVAL_HOURS` | `24` | hours between automatic backups |
| `SA_BACKUP_KEEP_DAILY` | `14` | newest backups always kept |
| `SA_BACKUP_KEEP_WEEKLY` | `8` | weekly representatives kept |
| `SA_BACKUP_SYNC_DIR` | — | extra copy target (existing folder) |

## Notes

- Backups never include API keys (those live only in the OS keyring).
- The restore path replays migrations, so restoring an older backup into a
  newer app is safe.
- The archive format is `ca-backup/v1`: `manifest.json`, `database.sqlite`
  (portable, no WAL sidecars) and `blobs/…` originals.
