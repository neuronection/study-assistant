import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { DatabaseBackup, Download, Loader2, ShieldCheck, Trash2, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorBanner } from '@/components/ui/error-banner'
import { TrashCard } from './TrashCard'
import {
  backupExportUrl,
  createBackupNow,
  deleteBackup,
  getBackupStatus,
  restoreBackup,
  restoreBackupByName,
  updateBackupSettings,
  type BackupSettingsInfo,
} from '@/lib/api'

function formatSize(size: number): string {
  if (size >= 1024 * 1024 * 1024) {
    return `${(size / (1024 * 1024 * 1024)).toFixed(1)} GB`
  }
  if (size >= 1024 * 1024) {
    return `${(size / (1024 * 1024)).toFixed(1)} MB`
  }
  return `${Math.max(1, Math.round(size / 1024))} kB`
}

export function DataTab() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const fileInput = useRef<HTMLInputElement>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [settingsDraft, setSettingsDraft] = useState<BackupSettingsInfo | null>(null)

  const status = useQuery({
    queryKey: ['backup-status'],
    queryFn: getBackupStatus,
  })

  useEffect(() => {
    if (status.data && settingsDraft === null) {
      setSettingsDraft(status.data.settings)
    }
  }, [status.data, settingsDraft])

  const invalidate = async () => {
    await queryClient.invalidateQueries()
  }

  const restore = useMutation({
    mutationFn: (file: File) => restoreBackup(file),
    onSuccess: async (result) => {
      setMessage(t('settings.restoreDone', { count: result.materials }))
      await invalidate()
    },
    onError: (err: Error) => setMessage(err.message),
  })

  const restoreStored = useMutation({
    mutationFn: (name: string) => restoreBackupByName(name),
    onSuccess: async (result) => {
      setMessage(t('settings.restoreDone', { count: result.materials }))
      await invalidate()
    },
    onError: (err: Error) => setError(err.message),
  })

  const createNow = useMutation({
    mutationFn: createBackupNow,
    onSuccess: async () => {
      setError(null)
      setMessage(t('settings.backupCreated'))
      await queryClient.invalidateQueries({ queryKey: ['backup-status'] })
    },
    onError: (err: Error) => setError(err.message),
  })

  const saveSettings = useMutation({
    mutationFn: (body: Partial<BackupSettingsInfo>) => updateBackupSettings(body),
    onSuccess: async (result) => {
      setSettingsDraft(result.settings)
      setError(null)
      setMessage(t('settings.backupSettingsSaved'))
      await queryClient.invalidateQueries({ queryKey: ['backup-status'] })
    },
    onError: (err: Error) => setError(err.message),
  })

  const removeBackup = useMutation({
    mutationFn: (name: string) => deleteBackup(name),
    onSuccess: async () => {
      setError(null)
      await queryClient.invalidateQueries({ queryKey: ['backup-status'] })
    },
    onError: (err: Error) => setError(err.message),
  })

  const dirtySettings =
    settingsDraft !== null &&
    status.data !== undefined &&
    (settingsDraft.interval_hours !== status.data.settings.interval_hours ||
      settingsDraft.keep_daily !== status.data.settings.keep_daily ||
      settingsDraft.keep_weekly !== status.data.settings.keep_weekly ||
      (settingsDraft.sync_dir ?? '') !== (status.data.settings.sync_dir ?? ''))

  return (
    <div className="space-y-4">
      <TrashCard />
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm">
            <ShieldCheck className="size-4" aria-hidden />
            {t('settings.autoBackupTitle')}
          </CardTitle>
          <CardDescription>{t('settings.autoBackupHint')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {!status.data || settingsDraft === null ? (
            <Loader2
              className="text-muted-foreground animate-spin"
              aria-label={t('library.loading')}
            />
          ) : (
            <>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={status.data.settings.auto}
                  onChange={(event) =>
                    saveSettings.mutate({ auto: event.target.checked })
                  }
                />
                {t('settings.autoBackupEnabled')}
              </label>

              <div className="grid gap-3 sm:grid-cols-3">
                <label className="space-y-1 text-xs">
                  <span className="text-muted-foreground">
                    {t('settings.backupInterval')}
                  </span>
                  <input
                    type="number"
                    min={1}
                    max={168}
                    className="bg-surface border-border w-full rounded-md border px-2 py-1"
                    value={settingsDraft.interval_hours}
                    onChange={(event) =>
                      setSettingsDraft({
                        ...settingsDraft,
                        interval_hours: Number(event.target.value) || 1,
                      })
                    }
                  />
                </label>
                <label className="space-y-1 text-xs">
                  <span className="text-muted-foreground">
                    {t('settings.backupKeepDaily')}
                  </span>
                  <input
                    type="number"
                    min={1}
                    max={365}
                    className="bg-surface border-border w-full rounded-md border px-2 py-1"
                    value={settingsDraft.keep_daily}
                    onChange={(event) =>
                      setSettingsDraft({
                        ...settingsDraft,
                        keep_daily: Number(event.target.value) || 1,
                      })
                    }
                  />
                </label>
                <label className="space-y-1 text-xs">
                  <span className="text-muted-foreground">
                    {t('settings.backupKeepWeekly')}
                  </span>
                  <input
                    type="number"
                    min={0}
                    max={104}
                    className="bg-surface border-border w-full rounded-md border px-2 py-1"
                    value={settingsDraft.keep_weekly}
                    onChange={(event) =>
                      setSettingsDraft({
                        ...settingsDraft,
                        keep_weekly: Number(event.target.value) || 0,
                      })
                    }
                  />
                </label>
              </div>

              <label className="space-y-1 block text-xs">
                <span className="text-muted-foreground">{t('settings.backupSyncDir')}</span>
                <input
                  type="text"
                  className="bg-surface border-border w-full rounded-md border px-2 py-1"
                  placeholder={t('settings.backupSyncDirPlaceholder')}
                  value={settingsDraft.sync_dir ?? ''}
                  onChange={(event) =>
                    setSettingsDraft({ ...settingsDraft, sync_dir: event.target.value })
                  }
                />
                <span className="text-muted-foreground text-[11px]">
                  {t('settings.backupSyncDirHint')}
                </span>
              </label>

              <div className="flex items-center justify-between">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!dirtySettings || saveSettings.isPending}
                  onClick={() =>
                    saveSettings.mutate({
                      interval_hours: settingsDraft.interval_hours,
                      keep_daily: settingsDraft.keep_daily,
                      keep_weekly: settingsDraft.keep_weekly,
                      sync_dir: (settingsDraft.sync_dir ?? '').trim() || null,
                    })
                  }
                >
                  {saveSettings.isPending ? (
                    <Loader2 className="animate-spin" aria-hidden />
                  ) : null}
                  {t('settings.backupSaveSettings')}
                </Button>
                <Button size="sm" disabled={createNow.isPending} onClick={() => createNow.mutate()}>
                  {createNow.isPending ? (
                    <Loader2 className="animate-spin" aria-hidden />
                  ) : (
                    <DatabaseBackup aria-hidden />
                  )}
                  {t('settings.backupNow')}
                </Button>
              </div>

              {status.data.last_recovery !== null ? (
                <p className="text-warning text-xs">
                  {t('settings.backupRecovered', {
                    date: new Date(status.data.last_recovery.at).toLocaleString(),
                    name: status.data.last_recovery.from_backup ?? t('settings.backupRecoveredNone'),
                  })}
                </p>
              ) : null}

              {status.data.backups.length > 0 ? (
                <ul className="divide-border divide-y rounded-md border">
                  {status.data.backups.map((entry) => (
                    <li key={entry.name} className="flex items-center gap-2 px-2 py-1.5 text-xs">
                      <span className="min-w-0 flex-1 truncate font-medium">{entry.name}</span>
                      <span className="text-muted-foreground shrink-0">
                        {formatSize(entry.size)}
                      </span>
                      <span className="text-muted-foreground shrink-0">
                        {new Date(entry.created_at).toLocaleString()}
                      </span>
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={restoreStored.isPending}
                        title={t('settings.backupRestoreThis')}
                        onClick={() => {
                          if (window.confirm(t('settings.backupRestoreConfirm', { name: entry.name }))) {
                            restoreStored.mutate(entry.name)
                          }
                        }}
                      >
                        {restoreStored.isPending && restoreStored.variables === entry.name ? (
                          <Loader2 className="animate-spin" aria-hidden />
                        ) : (
                          <Upload className="size-3.5" aria-hidden />
                        )}
                        {t('settings.backupRestoreThis')}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={removeBackup.isPending}
                        title={t('settings.backupDeleteThis')}
                        onClick={() => removeBackup.mutate(entry.name)}
                      >
                        {removeBackup.isPending && removeBackup.variables === entry.name ? (
                          <Loader2 className="animate-spin" aria-hidden />
                        ) : (
                          <Trash2 className="size-3.5" aria-hidden />
                        )}
                      </Button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-muted-foreground text-xs">{t('settings.backupNoneYet')}</p>
              )}
            </>
          )}
          <ErrorBanner message={error} />
          {message ? <p className="text-muted-foreground text-xs">{message}</p> : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t('settings.dataTitle')}</CardTitle>
          <CardDescription>{t('settings.dataHint')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <a
            href={backupExportUrl()}
            download
            className="border-border text-muted-foreground hover:bg-subtle hover:text-foreground inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs"
          >
            <Download className="size-3.5" aria-hidden />
            {t('settings.backupDownload')}
          </a>
          <div>
            <input
              ref={fileInput}
              type="file"
              accept=".zip"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (file) {
                  restore.mutate(file)
                }
                event.target.value = ''
              }}
            />
            <Button
              variant="outline"
              size="sm"
              disabled={restore.isPending}
              onClick={() => fileInput.current?.click()}
            >
              {restore.isPending ? (
                <Loader2 className="animate-spin" aria-hidden />
              ) : (
                <Upload aria-hidden />
              )}
              {t('settings.backupRestore')}
            </Button>
          </div>
          <p className="text-muted-foreground text-[11px]">{t('settings.restoreWarning')}</p>
        </CardContent>
      </Card>
    </div>
  )
}
