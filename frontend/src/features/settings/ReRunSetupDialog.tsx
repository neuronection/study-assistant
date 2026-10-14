import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Database, Eye, Loader2, Mic, Type, Volume2, Wrench, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { SetupReview, type SetupReviewOptions } from '@/components/ui/setup-review'
import {
  listPresets,
  listTaskDefaults,
  setupErrorDetail,
  setupProviderPreset,
  type Provider,
  type ProviderSetupErrorDetail,
} from '@/lib/api'
import { useCloseFloatings } from '@/lib/ui-overlays'

import { SetupErrorPanel } from './setupErrors'

/** Shared with the setup modal's review step (capability icons + the
 * curated-card capability guess). */
export const CAP_ICONS = {
  text: Type,
  vision: Eye,
  tools: Wrench,
  embeddings: Database,
  stt: Mic,
  tts: Volume2,
} as const

export function guessCaps(externalId: string): string[] {
  const id = externalId.toLowerCase()
  if (id.includes('embedding') || id.includes('bge')) return ['embeddings']
  if (/(whisper|transcribe|stt)/.test(id)) return ['stt']
  if (/(tts|speech|voice)/.test(id)) return ['tts']
  const caps = ['text']
  if (/(4o|gpt-5|vision|vl|claude|gemini|llava|pixtral|gemma3)/.test(id)) caps.push('vision')
  if (/(gpt-4|gpt-5|o3|o4|claude|gemini|deepseek|qwen|llama-3|mistral)/.test(id)) caps.push('tools')
  return caps
}

export function ReRunSetupDialog({ provider, onClose }: { provider: Provider; onClose: () => void }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  useCloseFloatings()

  const presets = useQuery({ queryKey: ['presets'], queryFn: listPresets })
  const defaults = useQuery({ queryKey: ['task-defaults'], queryFn: listTaskDefaults })
  const presetKey = provider.preset_key ?? ''
  const preset = presets.data?.[presetKey] ?? null

  const [options, setOptions] = useState<SetupReviewOptions>({
    curatedIds: [],
    bindChat: true,
    bindVision: true,
    bindStt: true,
    bindDecision: true,
  })
  const initialized = useRef(false)
  useEffect(() => {
    if (!initialized.current && preset?.curated_models) {
      initialized.current = true
      setOptions((current) => ({ ...current, curatedIds: preset.curated_models ?? [] }))
    }
  }, [preset])

  const [error, setError] = useState<ProviderSetupErrorDetail | null>(null)
  const [plainError, setPlainError] = useState<string | null>(null)

  const defaultByCap = new Map((defaults.data ?? []).map((entry) => [entry.requires, entry]))
  const decisionDeclared = (preset?.decision_models?.length ?? 0) > 0
  const bindDecision = decisionDeclared && options.bindDecision
  const nowLabel = (requires: string) => {
    const label = defaultByCap.get(requires)?.model_label
    return t('settings.setup.review.now', { model: label ?? t('settings.setup.review.unset') })
  }

  const reviewSlots = [
    {
      id: 'chat',
      label: t('settings.setup.review.fillText'),
      bind: options.bindChat,
      currentValue: nowLabel('text'),
      optionsKey: 'bindChat' as const,
    },
    {
      id: 'vision',
      label: t('settings.setup.review.fillVision'),
      bind: options.bindVision,
      currentValue: nowLabel('vision'),
      optionsKey: 'bindVision' as const,
    },
    ...(preset?.stt_model
      ? [
          {
            id: 'stt',
            label: t('settings.setup.review.fillStt'),
            bind: options.bindStt,
            currentValue: nowLabel('stt'),
            optionsKey: 'bindStt' as const,
          },
        ]
      : []),
    ...(decisionDeclared
      ? [
          {
            id: 'decision',
            label: t('settings.setup.review.fillDecision'),
            bind: bindDecision,
            // ADR-0036 §3: setup binds the `decision` default slot only —
            // one slot, so its "now" value reads like the capability rows.
            currentValue: nowLabel('decision'),
            optionsKey: 'bindDecision' as const,
          },
        ]
      : []),
  ]

  const apply = useMutation({
    mutationFn: () =>
      setupProviderPreset(presetKey, {
        api_key: null,
        options: {
          curated_ids: preset?.curated_models ? options.curatedIds : undefined,
          bind_chat: options.bindChat,
          bind_vision: options.bindVision,
          bind_stt: options.bindStt,
          bind_decision: bindDecision,
        },
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['providers'] })
      await queryClient.invalidateQueries({ queryKey: ['models'] })
      await queryClient.invalidateQueries({ queryKey: ['tasks'] })
      await queryClient.invalidateQueries({ queryKey: ['task-defaults'] })
      onClose()
    },
    onError: (err: { detail?: unknown; message?: string }) => {
      setError(setupErrorDetail(err.detail))
      setPlainError(setupErrorDetail(err.detail) ? null : (err.message ?? String(err)))
    },
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <Card className="max-h-[90vh] w-full max-w-lg overflow-y-auto">
        <CardContent className="space-y-3 p-4">
          <div className="flex items-start justify-between gap-2">
            <h2 className="text-base font-semibold">{t('settings.setup.automatically')}</h2>
            <Button variant="ghost" size="icon" aria-label={t('common.close')} onClick={onClose}>
              <X className="size-4" aria-hidden />
            </Button>
          </div>
          <p className="text-muted-foreground text-sm">
            {t('settings.setup.review.keyNote', { name: provider.name })}
          </p>
          <SetupReview
            models={(preset?.curated_models ?? []).map((modelId) => ({
              id: modelId,
              name: modelId,
              caps: guessCaps(modelId),
              selected: options.curatedIds.includes(modelId),
            }))}
            slots={reviewSlots}
            capIcons={CAP_ICONS}
            modelsLabel={t('settings.setup.review.modelsLabel')}
            footnote={t('settings.setup.review.footnote')}
            onOptionsChange={setOptions}
          />
          <SetupErrorPanel error={error} plainError={plainError} />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={onClose}>
              {t('settings.cancel')}
            </Button>
            <Button
              size="sm"
              disabled={apply.isPending || presets.isPending}
              onClick={() => apply.mutate()}
            >
              {apply.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Check aria-hidden />}
              {t('settings.setup.review.apply')}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
