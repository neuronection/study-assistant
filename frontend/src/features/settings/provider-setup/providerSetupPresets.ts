import type { ProviderSetupFormPreset } from '@/components/ui/provider-setup-form'
import type { ProviderSetupTileChip } from '@neuronection/assistant-ui/provider-setup-tiles'

import type { ProviderPreset } from '@/lib/api'

export const TILE_ORDER = [
  'openai',
  'gemini',
  'openrouter',
  'typesafe',
  'anthropic',
  'groq',
  'mistral',
  'deepseek',
  'ollama',
] as const

export function orderedPresetKeys(
  presets: Record<string, ProviderPreset> | undefined
): string[] {
  return TILE_ORDER.filter((key) => key in (presets ?? {}))
}

export function chipsForPreset(
  preset: Pick<
    ProviderPreset,
    'type' | 'local' | 'preferred_model' | 'stt_model' | 'decision_models'
  >,
  t: (key: string) => string
): ProviderSetupTileChip[] {
  const chips: ProviderSetupTileChip[] = []
  if (preset.type !== 'decision') {
    chips.push({ key: 'chat', label: t('settings.setup.chipChat') })
    if (preset.preferred_model?.caps?.includes('vision')) {
      chips.push({ key: 'vision', label: t('settings.setup.chipVision') })
    }
    if (preset.stt_model) {
      chips.push({ key: 'stt', label: t('settings.setup.chipStt') })
    }
  }
  if (preset.decision_models && preset.decision_models.length > 0) {
    chips.push({ key: 'decision', label: t('settings.setup.chipDecision') })
  }
  if (preset.local) {
    chips.push({ key: 'local', label: t('settings.setup.chipLocal') })
  }
  return chips
}

export function presetToFormPreset(
  key: string,
  preset: ProviderPreset
): ProviderSetupFormPreset {
  return {
    key,
    name: preset.name,
    keyUrl: preset.key_url ?? undefined,
    steps: preset.steps ?? undefined,
    freeTierNote: preset.free_tier_note ?? undefined,
    fixedBase: preset.fixed_base,
    baseUrl: preset.base_url,
    local: preset.local,
  }
}
