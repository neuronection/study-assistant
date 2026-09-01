import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  importSkillPackCommit,
  importSkillPackPreview,
  type SkillPackCommit,
  type SkillPackPreview,
} from '@/lib/api'

type Resolution = 'replace' | 'rename' | 'skip'

export function SkillPackImportDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [pack, setPack] = useState<unknown>(null)
  const [preview, setPreview] = useState<SkillPackPreview | null>(null)
  const [resolutions, setResolutions] = useState<Record<string, Resolution>>({})
  const [result, setResult] = useState<SkillPackCommit | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadFile = async (file: File) => {
    setError(null)
    setResult(null)
    setPreview(null)
    try {
      const parsed: unknown = JSON.parse(await file.text())
      const data = await importSkillPackPreview(parsed)
      setPack(parsed)
      setPreview(data)
      const initial: Record<string, Resolution> = {}
      for (const skill of data.skills) {
        initial[skill.key] = skill.collision ? 'skip' : 'replace'
      }
      setResolutions(initial)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  const commit = useMutation({
    mutationFn: () => importSkillPackCommit(pack, resolutions),
    onSuccess: async (data) => {
      setResult(data)
      await queryClient.invalidateQueries({ queryKey: ['skills'] })
      await queryClient.invalidateQueries({ queryKey: ['tasks'] })
    },
    onError: (err: Error) => setError(err.message),
  })

  const totalNew = result
    ? result.created.length +
      result.replaced.length +
      result.renamed.length
    : 0

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <Card className="max-h-[90vh] w-full max-w-lg overflow-y-auto">
        <CardHeader>
          <CardTitle className="text-base">{t('settings.packImportTitle')}</CardTitle>
          <p className="text-muted-foreground text-xs">{t('settings.packImportHint')}</p>
        </CardHeader>
        <CardContent className="space-y-3">
          {result ? (
            <div className="space-y-1 text-sm">
              <p className="text-success">
                {t('settings.packImportDone', { count: totalNew })}
              </p>
              {result.created.length > 0 ? (
                <p className="text-muted-foreground text-xs">
                  {t('settings.packCreated', { keys: result.created.join(', ') })}
                </p>
              ) : null}
              {result.replaced.length > 0 ? (
                <p className="text-muted-foreground text-xs">
                  {t('settings.packReplaced', { keys: result.replaced.join(', ') })}
                </p>
              ) : null}
              {result.renamed.map((entry) => (
                <p key={entry.new_key} className="text-muted-foreground text-xs">
                  {t('settings.packRenamed', { from: entry.key, to: entry.new_key })}
                </p>
              ))}
              {result.skipped.map((entry) => (
                <p key={entry.key} className="text-warning text-xs">
                  {t('settings.packSkipped', { key: entry.key, reason: entry.reason })}
                </p>
              ))}
              <div className="flex justify-end pt-2">
                <Button size="sm" onClick={onClose}>
                  {t('common.close')}
                </Button>
              </div>
            </div>
          ) : preview ? (
            <>
              <div className="space-y-2">
                {preview.skills.map((skill) => (
                  <div
                    key={skill.key}
                    className="border-border bg-surface space-y-1 rounded-md border px-3 py-2"
                  >
                    <p className="text-sm font-medium">
                      {skill.name}
                      <span className="text-muted-foreground ml-2 font-mono text-[11px]">
                        {skill.key}
                      </span>
                    </p>
                    <p className="text-muted-foreground text-xs">
                      {t('settings.packVersions', { count: skill.version_count })}
                      {skill.collision ? ` · ${t('settings.packCollision')}` : ''}
                    </p>
                    {skill.errors.length > 0 ? (
                      <p className="text-danger text-xs">{skill.errors.join('; ')}</p>
                    ) : null}
                    {skill.collision && skill.errors.length === 0 ? (
                      <select
                        className="bg-surface border-border rounded-md border px-2 py-1 text-xs"
                        value={resolutions[skill.key] ?? 'skip'}
                        onChange={(event) =>
                          setResolutions({
                            ...resolutions,
                            [skill.key]: event.target.value as Resolution,
                          })
                        }
                        aria-label={t('settings.packResolutionFor', { key: skill.key })}
                      >
                        <option value="replace">{t('settings.packResolutionReplace')}</option>
                        <option value="rename">{t('settings.packResolutionRename')}</option>
                        <option value="skip">{t('settings.packResolutionSkip')}</option>
                      </select>
                    ) : null}
                  </div>
                ))}
              </div>
              {error ? <p className="text-danger text-xs">{error}</p> : null}
              <div className="flex justify-end gap-2">
                <Button variant="ghost" size="sm" onClick={onClose}>
                  {t('common.cancel')}
                </Button>
                <Button
                  size="sm"
                  disabled={commit.isPending}
                  onClick={() => commit.mutate()}
                >
                  {t('settings.packImportCommit')}
                </Button>
              </div>
            </>
          ) : (
            <>
              <label className="text-muted-foreground block text-xs">
                {t('settings.packPickFile')}
                <input
                  type="file"
                  accept="application/json,.json"
                  className="mt-2 block w-full text-xs"
                  onChange={(event) => {
                    const file = event.target.files?.[0]
                    if (file) void loadFile(file)
                  }}
                />
              </label>
              {error ? <p className="text-danger text-xs">{error}</p> : null}
              <div className="flex justify-end">
                <Button variant="ghost" size="sm" onClick={onClose}>
                  {t('common.cancel')}
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
