import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Database, Eye, Loader2, Mic, Type, Volume2, Wrench, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  listPresets,
  listTaskDefaults,
  setupErrorDetail,
  setupProviderPreset,
  type Provider,
  type ProviderSetupErrorDetail,
} from '@/lib/api'
import { useCloseFloatings } from '@/lib/ui-overlays'

import { ProviderLogo } from './ProviderLogo'
import { SetupErrorPanel } from './setupErrors'

const CAP_ICONS = {
  text: Type,
  vision: Eye,
  tools: Wrench,
  embeddings: Database,
  stt: Mic,
  tts: Volume2,
} as const

function guessCaps(externalId: string): string[] {
  const id = externalId.toLowerCase()
  if (id.includes('embedding') || id.includes('bge')) return ['embeddings']
  if (/(whisper|transcribe|stt)/.test(id)) return ['stt']
  if (/(tts|speech|voice)/.test(id)) return ['tts']
  const caps = ['text']
  if (/(4o|gpt-5|vision|vl|claude|gemini|llava|pixtral|gemma3)/.test(id)) caps.push('vision')
  if (/(gpt-4|gpt-5|o3|o4|claude|gemini|deepseek|qwen|llama-3|mistral)/.test(id)) caps.push('tools')
  return caps
}

function SwitchRow({
  label,
  current,
  checked,
  onToggle,
}: {
  label: string
  current: string
  checked: boolean
  onToggle: () => void
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={onToggle}
      className="border-border hover:bg-subtle flex w-full items-center justify-between gap-3 rounded-md border px-3 py-2 text-left text-sm"
    >
      <span className="flex min-w-0 flex-col">
        <span>{label}</span>
        <span className="text-muted-foreground truncate text-xs">{current}</span>
      </span>
      <span
        aria-hidden="true"
        className={`relative h-5 w-9 shrink-0 rounded-full transition-colors ${
          checked ? 'bg-primary' : 'bg-border'
        }`}
      >
        <span
          className={`bg-surface absolute top-0.5 h-4 w-4 rounded-full shadow transition-all ${
            checked ? 'left-[1.125rem]' : 'left-0.5'
          }`}
        />
      </span>
    </button>
  )
}

export function ReRunSetupDialog({ provider, onClose }: { provider: Provider; onClose: () => void }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  useCloseFloatings()

  const presets = useQuery({ queryKey: ['presets'], queryFn: listPresets })
  const defaults = useQuery({ queryKey: ['task-defaults'], queryFn: listTaskDefaults })
  const presetKey = provider.preset_key ?? ''
  const preset = presets.data?.[presetKey] ?? null

  const [selected, setSelected] = useState<string[]>([])
  const [fillText, setFillText] = useState(true)
  const [fillVision, setFillVision] = useState(true)
  const [fillStt, setFillStt] = useState(true)
  const initialized = useRef(false)
  useEffect(() => {
    if (!initialized.current && preset?.curated_models) {
      initialized.current = true
      setSelected(preset.curated_models)
    }
  }, [preset])

  const [error, setError] = useState<ProviderSetupErrorDetail | null>(null)
  const [plainError, setPlainError] = useState<string | null>(null)

  const defaultByCap = new Map((defaults.data ?? []).map((entry) => [entry.requires, entry]))
  const nowLabel = (requires: string) => {
    const label = defaultByCap.get(requires)?.model_label
    return t('settings.setup.review.now', { model: label ?? t('settings.setup.review.unset') })
  }

  const apply = useMutation({
    mutationFn: () =>
      setupProviderPreset(presetKey, {
        api_key: null,
        options: {
          curated_ids: preset?.curated_models ? selected : undefined,
          bind_chat: fillText,
          bind_vision: fillVision,
          bind_stt: fillStt,
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
          {preset && preset.curated_models && preset.curated_models.length > 0 ? (
            <div
              role="group"
              aria-label={t('settings.setup.review.modelsLabel')}
              className="grid grid-cols-1 gap-2 sm:grid-cols-2"
            >
              {preset.curated_models.map((modelId) => {
                const isSelected = selected.includes(modelId)
                return (
                  <button
                    type="button"
                    key={modelId}
                    aria-pressed={isSelected}
                    onClick={() =>
                      setSelected((current) =>
                        isSelected
                          ? current.filter((id) => id !== modelId)
                          : [...current, modelId]
                      )
                    }
                    className={`flex items-center justify-between gap-2 rounded-md border px-3 py-2 text-left text-sm ${
                      isSelected
                        ? 'border-primary bg-primary/10'
                        : 'border-border bg-surface hover:bg-subtle opacity-70'
                    }`}
                  >
                    <span className="flex min-w-0 flex-col gap-1">
                      <span className="flex items-center gap-2 truncate font-medium">
                        <ProviderLogo presetKey={presetKey} label={modelId} />
                        {modelId}
                      </span>
                      <span className="text-muted-foreground flex items-center gap-2 text-xs">
                        {guessCaps(modelId).map((cap) => {
                          const Icon = CAP_ICONS[cap as keyof typeof CAP_ICONS]
                          return Icon ? <Icon key={cap} className="size-3.5" aria-hidden /> : null
                        })}
                      </span>
                    </span>
                    {isSelected ? <Check className="text-primary size-4 shrink-0" aria-hidden /> : null}
                  </button>
                )
              })}
            </div>
          ) : null}
          <div className="space-y-2">
            <SwitchRow
              label={t('settings.setup.review.fillText')}
              current={nowLabel('text')}
              checked={fillText}
              onToggle={() => setFillText((v) => !v)}
            />
            <SwitchRow
              label={t('settings.setup.review.fillVision')}
              current={nowLabel('vision')}
              checked={fillVision}
              onToggle={() => setFillVision((v) => !v)}
            />
            {preset?.stt_model ? (
              <SwitchRow
                label={t('settings.setup.review.fillStt')}
                current={nowLabel('stt')}
                checked={fillStt}
                onToggle={() => setFillStt((v) => !v)}
              />
            ) : null}
          </div>
          <p className="text-muted-foreground text-xs">{t('settings.setup.review.footnote')}</p>
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
