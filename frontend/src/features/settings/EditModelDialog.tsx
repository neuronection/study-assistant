import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Loader2, Save } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { updateModel, type AiModel } from '@/lib/api'
import { useCloseFloatings } from '@/lib/ui-overlays'

export const MODEL_CAPS = ['text', 'vision', 'tools', 'embeddings', 'audio'] as const

export const REASONING_EFFORT_OPTIONS = [
  'none',
  'low',
  'medium',
  'high',
  'max',
  'xhigh',
] as const

export function EditModelDialog({ model, onClose }: { model: AiModel; onClose: () => void }) {
  useCloseFloatings()
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [label, setLabel] = useState(model.label)
  const [caps, setCaps] = useState<string[]>(model.caps)
  const [enabled, setEnabled] = useState(model.enabled)
  const [reasoningEffort, setReasoningEffort] = useState(model.reasoning_effort ?? '')
  const [error, setError] = useState<string | null>(null)

  const save = useMutation({
    mutationFn: () =>
      updateModel(model.id, {
        label: label.trim(),
        caps,
        enabled,
        reasoning_effort: reasoningEffort.trim(),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['models'] })
      onClose()
    },
    onError: (err: Error) => setError(err.message),
  })

  const toggleCap = (cap: string) => {
    setCaps((current) =>
      current.includes(cap) ? current.filter((entry) => entry !== cap) : [...current, cap]
    )
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <Card className="max-h-[90vh] w-full max-w-md overflow-y-auto">
        <CardHeader>
          <CardTitle className="text-base font-mono text-sm">{model.external_id}</CardTitle>
          <CardDescription>{t('settings.editModelHint')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <label className="block space-y-1 text-sm">
            <span className="text-muted-foreground">{t('settings.modelLabel')}</span>
            <input
              className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
              value={label}
              onChange={(event) => setLabel(event.target.value)}
            />
          </label>
          <div className="space-y-1 text-sm">
            <span className="text-muted-foreground">{t('settings.modelCaps')}</span>
            <div className="flex flex-wrap gap-2">
              {MODEL_CAPS.map((cap) => (
                <button
                  key={cap}
                  type="button"
                  aria-pressed={caps.includes(cap)}
                  onClick={() => toggleCap(cap)}
                  className={
                    caps.includes(cap)
                      ? 'border-primary bg-primary/10 text-primary rounded-full border px-2.5 py-0.5 text-[11px]'
                      : 'border-border text-muted-foreground rounded-full border px-2.5 py-0.5 text-[11px]'
                  }
                >
                  {t(`settings.caps.${cap}`)}
                </button>
              ))}
            </div>
            <p className="text-muted-foreground text-[11px]">{t('settings.modelCapsHint')}</p>
          </div>
          <label className="block space-y-1 text-sm">
            <span className="text-muted-foreground">{t('settings.modelReasoningEffort')}</span>
            <input
              className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
              value={reasoningEffort}
              placeholder={t('settings.modelReasoningEffortPlaceholder')}
              list="reasoning-effort-options"
              onChange={(event) => setReasoningEffort(event.target.value)}
            />
            <datalist id="reasoning-effort-options">
              {REASONING_EFFORT_OPTIONS.map((option) => (
                <option key={option} value={option} />
              ))}
            </datalist>
            <p className="text-muted-foreground text-[11px]">
              {t('settings.modelReasoningEffortHint')}
            </p>
          </label>
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(event) => setEnabled(event.target.checked)}
            />
            {t('settings.modelEnabled')}
          </label>
          <p className="text-muted-foreground text-[11px]">{t('settings.modelEnabledHint')}</p>
          {error ? <p className="text-danger text-xs">{error}</p> : null}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={onClose}>
              {t('settings.cancel')}
            </Button>
            <Button size="sm" disabled={save.isPending} onClick={() => save.mutate()}>
              {save.isPending ? (
                <Loader2 className="animate-spin" aria-hidden />
              ) : (
                <Save aria-hidden />
              )}
              {t('settings.save')}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
