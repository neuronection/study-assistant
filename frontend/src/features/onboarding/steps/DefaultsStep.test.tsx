import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { DefaultsStep } from './DefaultsStep'

const assignTaskDefault = vi.fn()
const listModels = vi.fn()
const listProviders = vi.fn()
const listTaskDefaults = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    assignTaskDefault: (requires: string, modelId: string | null, fallback: string | null) =>
      assignTaskDefault(requires, modelId, fallback),
    listModels: () => listModels(),
    listProviders: () => listProviders(),
    listTaskDefaults: () => listTaskDefaults(),
  }
})

const PROVIDER = {
  id: '1',
  name: 'OpenAI',
  is_local: false,
}

const MODELS = [
  {
    id: '11',
    provider_id: '1',
    external_id: 'gpt-4o',
    label: 'GPT-4o',
    caps: ['text', 'vision'],
    enabled: true,
    missing: false,
  },
  {
    id: '12',
    provider_id: '1',
    external_id: 'text-embedding-3-small',
    label: 'Embedding',
    caps: ['embeddings'],
    enabled: true,
    missing: false,
  },
  {
    id: '13',
    provider_id: '1',
    external_id: 'whisper-1',
    label: 'Whisper',
    caps: ['stt'],
    enabled: true,
    missing: false,
  },
  {
    id: '14',
    provider_id: '1',
    external_id: 'tts-1',
    label: 'TTS',
    caps: ['tts'],
    enabled: true,
    missing: false,
  },
]

function renderStep() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <DefaultsStep />
    </QueryClientProvider>
  )
}

describe('DefaultsStep', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listProviders.mockResolvedValue([PROVIDER])
    listModels.mockResolvedValue(MODELS)
    listTaskDefaults.mockResolvedValue([])
    assignTaskDefault.mockResolvedValue({})
  })

  test('auto-assigns every capability with an enabled model', async () => {
    renderStep()

    await waitFor(() => expect(assignTaskDefault).toHaveBeenCalledTimes(5))
    expect(assignTaskDefault).toHaveBeenCalledWith('text', '11', null)
    expect(assignTaskDefault).toHaveBeenCalledWith('vision', '11', null)
    expect(assignTaskDefault).toHaveBeenCalledWith('embeddings', '12', null)
    expect(assignTaskDefault).toHaveBeenCalledWith('stt', '13', null)
    expect(assignTaskDefault).toHaveBeenCalledWith('tts', '14', null)
  })

  test('does not overwrite an existing default', async () => {
    listTaskDefaults.mockResolvedValue([
      { requires: 'text', model_id: '11', fallback_model_id: null },
    ])
    renderStep()

    await waitFor(() => expect(assignTaskDefault).toHaveBeenCalledTimes(4))
    expect(assignTaskDefault).not.toHaveBeenCalledWith('text', '11', null)
  })
})
