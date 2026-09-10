import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { createProvider, listPresets, type Provider } from '@/lib/api'

export const CUSTOM_PRESET = 'custom'
export const PROVIDER_PRESET_ORDER = [
  'google',
  'openai',
  'anthropic',
  'ollama',
  'llama_cpp',
  'lm_studio',
] as const
const LOCAL_PRESETS = new Set(['ollama', 'llama_cpp', 'lm_studio'])
const PRESET_TYPES: Record<string, string> = {
  google: 'google',
  anthropic: 'anthropic',
  openai: 'openai_compatible',
  ollama: 'openai_compatible',
  llama_cpp: 'openai_compatible',
  lm_studio: 'openai_compatible',
  [CUSTOM_PRESET]: 'openai_compatible',
}

export function useProviderCreate({ onCreated }: { onCreated: (provider: Provider) => void }) {
  const queryClient = useQueryClient()
  const presets = useQuery({ queryKey: ['presets'], queryFn: listPresets })
  const [presetKey, setPresetKey] = useState<string>('google')
  const [name, setName] = useState('')
  const [nameDirty, setNameDirty] = useState(false)
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [isLocal, setIsLocal] = useState(false)
  const [country, setCountry] = useState('')
  const [error, setError] = useState<string | null>(null)

  const presetNames = Object.values(presets.data ?? {}).map((preset) => preset.name)
  const selectedType = PRESET_TYPES[presetKey] ?? 'openai_compatible'

  const applyPreset = (key: string) => {
    setPresetKey(key)
    const preset = presets.data?.[key]
    if (preset && (!nameDirty || presetNames.includes(name))) {
      setName(preset.name)
    }
    setBaseUrl(key === CUSTOM_PRESET ? '' : (preset?.base_url ?? ''))
    setIsLocal(LOCAL_PRESETS.has(key))
  }

  const save = useMutation({
    mutationFn: () =>
      createProvider({
        name,
        type: selectedType,
        base_url: selectedType === 'openai_compatible' ? baseUrl.trim() || null : null,
        api_key: apiKey || null,
        is_local: isLocal,
        country: country.trim() || null,
      }),
    onSuccess: async (provider) => {
      await queryClient.invalidateQueries({ queryKey: ['providers'] })
      await queryClient.invalidateQueries({ queryKey: ['models'] })
      onCreated(provider)
    },
    onError: (err: Error) => setError(err.message),
  })

  const canSave = name.trim().length > 0 && !(presetKey === CUSTOM_PRESET && !baseUrl.trim())

  return {
    presets,
    presetKey,
    applyPreset,
    selectedType,
    name,
    setName: (value: string) => {
      setName(value)
      setNameDirty(true)
    },
    baseUrl,
    setBaseUrl,
    apiKey,
    setApiKey,
    isLocal,
    setIsLocal,
    country,
    setCountry,
    error,
    canSave,
    submitting: save.isPending,
    submit: () => save.mutate(),
  }
}

export type ProviderCreateState = ReturnType<typeof useProviderCreate>
