import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, CircleAlert, Loader2, RotateCcw, Undo2 } from 'lucide-react'
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

export function WorkingDirEditor() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const info = useQuery({ queryKey: ['working-dir'], queryFn: getWorkingDir })
  const [path, setPath] = useState<string | null>(null)
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
    mutationFn: () => validateWorkingDir(trimmed),
    onSuccess: (result) => {
      setValidation(result)
      setValidatedFor(trimmed)
      setError(null)
    },
    onError: (err: Error) => setError(err.message),
  })

  const save = useMutation({
    mutationFn: () => setWorkingDir(trimmed),
    onSuccess: async () => {
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
      setPath(null)
      setValidation(null)
      setValidatedFor(null)
      setError(null)
      await invalidate()
    },
    onError: (err: Error) => setError(err.message),
  })

  if (info.isPending) {
    return <Loader2 className="text-muted-foreground animate-spin" aria-hidden />
  }

  return (
    <div className="space-y-3">
      {info.data?.restart_pending ? (
        <p className="border-warning/40 bg-warning/10 text-foreground flex items-start gap-2 rounded-md border px-3 py-2 text-xs">
          <CircleAlert className="text-warning mt-0.5 size-3.5 shrink-0" aria-hidden />
          <span className="min-w-0 flex-1">
            {t('settings.workingDir.restartPending', { path: info.data.path })}
          </span>
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
      <label className="block space-y-1 text-sm">
        <span className="text-muted-foreground">{t('settings.workingDir.inputLabel')}</span>
        <input
          type="text"
          className="bg-surface border-border w-full rounded-md border px-3 py-2 font-mono text-xs"
          value={value}
          spellCheck={false}
          onChange={(event) => {
            setPath(event.target.value)
            setValidation(null)
            setValidatedFor(null)
          }}
          onBlur={() => {
            if (changed && !validation) {
              check.mutate()
            }
          }}
        />
        {info.data ? (
          <span className="text-muted-foreground block text-[11px]">
            {t('settings.workingDir.defaultHint', { path: info.data.default_path })}
          </span>
        ) : null}
      </label>
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
        {info.data?.custom ? (
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
        {!changed && info.data ? (
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setPath(info.data.default_path)
              setValidation(null)
              setValidatedFor(null)
            }}
          >
            {t('settings.workingDir.useDefault')}
          </Button>
        ) : null}
        <Button variant="outline" size="sm" disabled={!changed || check.isPending} onClick={() => check.mutate()}>
          {check.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
          {t('settings.workingDir.check')}
        </Button>
        <Button size="sm" disabled={!canSave || save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
          {t('settings.workingDir.save')}
        </Button>
      </div>
    </div>
  )
}
