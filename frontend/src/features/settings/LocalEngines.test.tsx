import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { LocalEngines } from './LocalEngines'

const detectLocalEngines = vi.fn()
const createProvider = vi.fn()
const listPresets = vi.fn()
const setupProviderPreset = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    detectLocalEngines: () => detectLocalEngines(),
    createProvider: (...args: unknown[]) => createProvider(...(args as [object])),
    listPresets: () => listPresets(),
    setupProviderPreset: (key: string, body: unknown) => setupProviderPreset(key, body),
  }
})

const HIT = {
  preset_id: 'ollama',
  name: 'Ollama (local)',
  base_url: 'http://localhost:11434/v1',
  models: ['qwen3:8b', 'nomic-embed-text'],
}

function renderDetector(props: Parameters<typeof LocalEngines>[0] = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <LocalEngines {...props} />
    </QueryClientProvider>
  )
}

describe('LocalEngines', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listPresets.mockResolvedValue({})
  })

  test('probes on demand and offers one-click add', async () => {
    detectLocalEngines.mockResolvedValue([HIT])
    const onCreated = vi.fn()
    createProvider.mockResolvedValue({ id: '7', name: HIT.name })
    renderDetector({ onCreated })
    expect(screen.queryByText('Ollama (local)')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /detect local engines/i }))
    expect(await screen.findByText('Ollama (local)')).toBeInTheDocument()
    expect(screen.getByText('http://localhost:11434/v1 · 2 models')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /add ollama \(local\)/i }))
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(expect.objectContaining({ id: '7' })))
    expect(createProvider).toHaveBeenCalledWith({
      name: 'Ollama (local)',
      type: 'openai_compatible',
      base_url: 'http://localhost:11434/v1',
      api_key: null,
      is_local: true,
    })
  })

  test('routes a known local preset through the shared preset setup', async () => {
    listPresets.mockResolvedValue({ ollama: { name: 'Ollama' } })
    detectLocalEngines.mockResolvedValue([HIT])
    const onCreated = vi.fn()
    setupProviderPreset.mockResolvedValue({
      provider: { id: '8', name: HIT.name, base_url: HIT.base_url },
    })
    renderDetector({ auto: true, onCreated })
    fireEvent.click(await screen.findByRole('button', { name: /add ollama \(local\)/i }))
    await waitFor(() =>
      expect(setupProviderPreset).toHaveBeenCalledWith('ollama', {
        api_key: null,
        name: HIT.name,
        options: {
          bind_chat: false,
          bind_vision: false,
          bind_stt: false,
          bind_embeddings: false,
          bind_decision: false,
        },
      })
    )
    await waitFor(() =>
      expect(onCreated).toHaveBeenCalledWith(expect.objectContaining({ id: '8' }))
    )
    expect(createProvider).not.toHaveBeenCalled()
  })

  test('auto mode probes on mount without a click', async () => {
    detectLocalEngines.mockResolvedValue([HIT])
    renderDetector({ auto: true })
    expect(await screen.findByText('Ollama (local)')).toBeInTheDocument()
    expect(detectLocalEngines).toHaveBeenCalled()
  })

  test('reports an empty scan honestly', async () => {
    detectLocalEngines.mockResolvedValue([])
    renderDetector({ auto: true })
    expect(await screen.findByText(/no local engines detected/i)).toBeInTheDocument()
  })

  test('surfaces add failures', async () => {
    detectLocalEngines.mockResolvedValue([HIT])
    createProvider.mockRejectedValue(new Error('boom'))
    renderDetector({ auto: true })
    fireEvent.click(await screen.findByRole('button', { name: /add ollama \(local\)/i }))
    expect(await screen.findByText('boom')).toBeInTheDocument()
  })
})
