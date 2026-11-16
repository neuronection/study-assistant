# Off-host backup timer (T1)

The compose `backup` sidecar is a **same-host** dump loop (non-DR). For a T1
deployment, schedule `scripts/backup.sh` on the host with an off-host target:

```ini
# /etc/systemd/system/study-backup.service
[Unit]
Description=Study Assistant off-host backup
[Service]
Type=oneshot
WorkingDirectory=/srv/study-assistant
EnvironmentFile=/srv/study-assistant/docker/.env
ExecStart=/srv/study-assistant/scripts/backup.sh
```

```ini
# /etc/systemd/system/study-backup.timer
[Unit]
Description=Daily Study Assistant backup
[Timer]
OnCalendar=*-*-* 03:15:00
Persistent=true
[Install]
WantedBy=timers.target
```

Install `awscli`, `rclone` or `azcopy`, set one of
`SA_BACKUP_RCLONE_REMOTE` / `SA_BACKUP_S3_URI` / `SA_BACKUP_AZURE_URL`, then
`systemctl enable --now study-backup.timer`. Alert when the newest
`backup_runs.jsonl` row is older than 2× the interval.
