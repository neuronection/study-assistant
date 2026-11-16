import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CheckCircle2,
  CircleAlert,
  FolderOpen,
  Loader2,
  RotateCcw,
  Undo2,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import {
  getWorkingDir,
  resetWorkingDir,
  setWorkingDir,
  validateWorkingDir,
  type WorkingDirValidation,
} from '@/lib/api'
import { hasDataDirPicker, pickDataDir } from '@/lib/desktop-bridge'

const INPUT_ID = 'working-dir-path'

export function WorkingDirEditor() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const info = useQuery({ queryKey: ['working-dir'], queryFn: getWorkingDir })
  const [path, setPath] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [validation, setValidation] = useState<WorkingDirValidation | null>(null)
  const [validatedFor, setValidatedFor] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (info.data && path === null) {
      setPath(info.data.path)
    }
  }, [info.data, path])

  const value = path ?? ''
  const trimmed = value.trim()
  const changed =
    info.data !== undefined && trimmed.length > 0 && trimmed !== info.data.path
  const canSave = changed && validation?.valid === true && validatedFor === trimmed

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['working-dir'] })

  const check = useMutation({
    mutationFn: (target: string) => validateWorkingDir(target),
    onSuccess: (result, target) => {
      setValidation(result)
      setValidatedFor(target)
      setError(null)
    },
    onError: (err: Error) => setError(err.message),
  })

  const save = useMutation({
    mutationFn: () => setWorkingDir(trimmed),
    onSuccess: async () => {
      setEditing(false)
      setPath(null)
      setValidation(null)
      setValidatedFor(null)
      setError(null)
      await invalidate()
    },
    onError: (err: Error) => setError(err.message),
  })

  const reset = useMutation({
    mutationFn: resetWorkingDir,
    onSuccess: async () => {
      setEditing(false)
      setPath(null)
      setValidation(null)
      setValidatedFor(null)
      setError(null)
      await invalidate()
    },
    onError: (err: Error) => setError(err.message),
  })

  const applyPath = (next: string) => {
    setPath(next)
    setValidation(null)
    setValidatedFor(null)
    setError(null)
  }

  const beginEdit = () => {
    setEditing(true)
    setValidation(null)
    setValidatedFor(null)
    setError(null)
  }

  const cancelEdit = () => {
    setEditing(false)
    setPath(null)
    setValidation(null)
    setValidatedFor(null)
    setError(null)
  }

  const chooseFolder = async () => {
    const selected = await pickDataDir()
    if (selected === null) {
      return
    }
    applyPath(selected)
    check.mutate(selected)
  }

  if (info.isPending) {
    return <Loader2 className="text-muted-foreground animate-spin" aria-hidden />
  }

  return (
    <div className="space-y-3">
      {info.data?.restart_pending ? (
        <p className="border-warning/40 bg-warning/10 text-foreground flex items-start gap-2 rounded-md border px-3 py-2 text-xs">
          <CircleAlert className="text-warning mt-0.5 size-3.5 shrink-0" aria-hidden />
          <span className="min-w-0 flex-1">{t('settings.workingDir.restartPending')}</span>
          <Button
            variant="ghost"
            size="sm"
            className="h-auto shrink-0 px-1.5 py-0.5 text-[11px]"
            disabled={reset.isPending}
            onClick={() => reset.mutate()}
          >
            <Undo2 className="size-3" aria-hidden />
            {t('settings.workingDir.undo')}
          </Button>
        </p>
      ) : null}

      <div className="space-y-1 text-sm">
        <label htmlFor={INPUT_ID} className="text-muted-foreground">
          {t('settings.workingDir.inputLabel')}
        </label>
        {editing ? (
          <input
            id={INPUT_ID}
            type="text"
            className="bg-surface border-border w-full rounded-md border px-3 py-2 font-mono text-xs"
            value={value}
            spellCheck={false}
            autoFocus
            onChange={(event) => applyPath(event.target.value)}
            onBlur={() => {
              if (changed && validatedFor !== trimmed) {
                check.mutate(trimmed)
              }
            }}
          />
        ) : (
          <div className="flex items-center gap-2">
            <input
              id={INPUT_ID}
              type="text"
              className="bg-subtle border-border text-muted-foreground w-full min-w-0 rounded-md border px-3 py-2 font-mono text-xs"
              value={info.data?.path ?? ''}
              readOnly
            />
            <Button variant="outline" size="sm" className="shrink-0" onClick={beginEdit}>
              <FolderOpen className="size-3.5" aria-hidden />
              {t('settings.workingDir.change')}
            </Button>
          </div>
        )}
        {info.data ? (
          <span className="text-muted-foreground block text-[11px]">
            {t('settings.workingDir.defaultHint', { path: info.data.default_path })}
          </span>
        ) : null}
      </div>

      <p className="text-muted-foreground text-[11px]">
        {editing
          ? t('settings.workingDir.manualHint')
          : t('settings.workingDir.readOnlyHint')}
      </p>

      {validation ? (
        validation.valid ? (
          <p className="text-success flex items-center gap-1.5 text-xs">
            <CheckCircle2 className="size-3.5 shrink-0" aria-hidden />
            {t(
              validation.empty
                ? 'settings.workingDir.validEmpty'
                : 'settings.workingDir.validExisting'
            )}
          </p>
        ) : (
          <p className="text-warning flex items-center gap-1.5 text-xs">
            <CircleAlert className="size-3.5 shrink-0" aria-hidden />
            {validation.reason
              ? t(`settings.workingDir.reason.${validation.reason}`)
              : t('settings.workingDir.invalid')}
          </p>
        )
      ) : null}
      {error ? <p className="text-danger text-xs">{error}</p> : null}

      <div className="flex flex-wrap items-center justify-end gap-2">
        {editing ? (
          <>
            {hasDataDirPicker() ? (
              <Button variant="outline" size="sm" onClick={() => void chooseFolder()}>
                <FolderOpen className="size-3.5" aria-hidden />
                {t('settings.workingDir.browse')}
              </Button>
            ) : null}
            <Button variant="ghost" size="sm" onClick={cancelEdit}>
              {t('settings.workingDir.cancel')}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => applyPath(info.data?.default_path ?? '')}
            >
              {t('settings.workingDir.useDefault')}
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={!changed || check.isPending}
              onClick={() => check.mutate(trimmed)}
            >
              {check.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
              {t('settings.workingDir.check')}
            </Button>
            <Button
              size="sm"
              disabled={!canSave || save.isPending}
              onClick={() => save.mutate()}
            >
              {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
              {t('settings.workingDir.save')}
            </Button>
          </>
        ) : info.data?.custom ? (
          <Button
            variant="ghost"
            size="sm"
            disabled={reset.isPending}
            onClick={() => reset.mutate()}
          >
            <RotateCcw className="size-3.5" aria-hidden />
            {t('settings.workingDir.resetDefault')}
          </Button>
        ) : null}
      </div>
    </div>
  )
}
