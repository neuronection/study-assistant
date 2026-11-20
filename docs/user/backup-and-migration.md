# Backup, restore & migration — Study Assistant (self-host)

Conforms to the family template (`dev/templates/docs/backup-migration.md`).
Cross-VM mechanics live in the canonical runbook:
[`neuronection/self-host` → docs/migration.md](https://github.com/neuronection/self-host/blob/main/docs/migration.md).
(The desktop app's data-folder backup is a different story — see
`docs/user/backup.md`.)

## What one backup contains

`bash scripts/backup.sh [output-dir]` produces
`study-assistant-<timestamp>.tar.gz`:

- `database.dump` — `pg_dump` custom format of `neuronection_study`
- `data.tar.gz` — the `data` volume (`SA_DATA_DIR=/data`: blobs, cache,
  thumbnails, import-inbox, in-app backups)
- `manifest.json` — contents + versions (ledger row in `backup_runs.jsonl`)

Archives never contain secrets; `docker/.env` is excluded on purpose.

## Off-host targets (set in `docker/.env` or the shell)

Every configured target receives the archive:

| Key | Target |
|---|---|
| `SA_BACKUP_RCLONE_REMOTE` | any `remote:path` rclone target |
| `SA_BACKUP_S3_URI` | `s3://bucket/prefix` |
| `SA_BACKUP_AZURE_URL` | `https://acct.blob…/ctr` (azcopy) |
| `SA_BACKUP_AGE_RECIPIENT` | age public key — encrypt before upload |

Schedule with cron — nightly is a sane default. A local-only backup is
non-DR: label it as such and add an off-host target.

## Restore

```bash
bash scripts/restore.sh <archive.tar.gz> [--yes]
FORCE=1 bash scripts/restore.sh <archive.tar.gz>
```

Replaces the database and the `data` volume. Encrypted archives
(`.tar.gz.age`) decrypt first with the local age identity
(`AGE_IDENTITY`, default `~/.config/age/keys.txt`).

## The data-key rule

`SA_DATA_KEY` in `docker/.env` encrypts columns at rest. It is **not**
in the archive — when moving to another VM, copy `docker/.env` (0600)
to the new install **before** restoring, then fix host-specific values
(`SA_PUBLIC_URL`, ports). Full runbook:
[self-host migration guide](https://github.com/neuronection/self-host/blob/main/docs/migration.md).

## Restore drill

Once a month (and after any version change): restore the latest archive
into a scratch install (`--env-only` + old `.env` + `restore.sh`), log
in, open one real entity, then delete the scratch. If the drill fails,
the backup is not a backup.
