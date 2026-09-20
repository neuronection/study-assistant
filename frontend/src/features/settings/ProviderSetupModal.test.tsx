import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { ApiError } from '@/lib/api'

import { ProviderSetupModal } from './ProviderSetupModal'

const listPresets = vi.fn()
const setupMutation = vi.fn()
const createProvider = vi.fn()
const clipboardWrite = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listPresets: () => listPresets(),
    setupProviderPreset: (presetKey: string, body: unknown) => setupMutation(presetKey, body),
    createProvider: (body: unknown) => createProvider(body),
  }
})

const PRESETS: Record<string, unknown> = {
  openai: {
    name: 'OpenAI',
    type: 'openai_compatible',
    base_url: 'https://api.openai.com/v1',
    fixed_base: false,
    local: false,
    key_url: 'https://platform.openai.com/api-keys',
    preferred_model: { id: 'gpt-5.6-terra', name: 'GPT-5.6 Terra', caps: ['text', 'tools', 'vision'] },
    curated_models: ['gpt-5.6-terra', 'whisper-1'],
    stt_model: 'whisper-1',
    steps: ['Open {url} and sign in.', 'Paste it below and connect.'],
    free_tier_note: null,
  },
  gemini: {
    name: 'Google Gemini',
    type: 'google',
    base_url: 'https://generativelanguage.googleapis.com',
    fixed_base: true,
    local: false,
    key_url: 'https://aistudio.google.com/app/apikey',
    preferred_model: { id: 'gemini-3.8-flash', name: 'Gemini 3.8 Flash', caps: ['text', 'tools', 'vision'] },
    curated_models: ['gemini-3.8-flash'],
    stt_model: null,
    steps: null,
    free_tier_note: 'Google offers a free AI Studio tier — no credit card required.',
  },
  ollama: {
    name: 'Ollama (local)',
    type: 'openai_compatible',
    base_url: 'http://localhost:11434/v1',
    fixed_base: false,
    local: true,
    key_url: null,
    preferred_model: null,
    curated_models: null,
    stt_model: null,
    steps: null,
    free_tier_note: null,
  },
}

const SETUP_OK = {
  ok: true,
  provider: {
    id: 1, name: 'OpenAI', type: 'openai_compatible', base_url: '', preset_key: 'openai',
    enabled: true, is_local: false, country: null, masked_key: null, status: null, created_at: '',
  },
  catalog_count: 2,
  curated_missed: false,
  assigned_chat_model: 'gpt-5.6-terra',
  assigned_vision_model: 'gpt-5.6-terra',
  assigned_stt_model: 'whisper-1',
}

function renderModal() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ProviderSetupModal onClose={() => {}} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  listPresets.mockReset()
  setupMutation.mockReset()
  createProvider.mockReset()
  listPresets.mockResolvedValue(PRESETS)
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText: clipboardWrite },
    configurable: true,
  })
})

describe('ProviderSetupModal', () => {
  test('opens on the tile grid in the canonical family order with a manual tile', async () => {
    renderModal()
    const openai = await screen.findByText('OpenAI')
    const gemini = screen.getByText('Google Gemini')
    const ollama = screen.getByText('Ollama (local)')
    expect(openai.compareDocumentPosition(gemini) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(gemini.compareDocumentPosition(ollama) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.getByText(/custom/i)).toBeInTheDocument()
  })

  test('preset form shows steps, key link, and advanced base URL; copies steps', async () => {
    renderModal()
    fireEvent.click(await screen.findByText('OpenAI'))
    expect(await screen.findByText(/open https:\/\/platform\.openai\.com\/api-keys and sign in\./i)).toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('button', { name: /copy/i })[0])
    expect(clipboardWrite).toHaveBeenCalledWith('Open {url} and sign in.')
    expect(screen.getByRole('link', { name: /get an api key/i })).toHaveAttribute(
      'href',
      'https://platform.openai.com/api-keys'
    )
    fireEvent.click(screen.getByText(/advanced/i))
    expect(screen.getByDisplayValue('https://api.openai.com/v1')).not.toHaveAttribute('readonly')
  })

  test('fixed-base preset locks the base URL field', async () => {
    renderModal()
    fireEvent.click(await screen.findByText('Google Gemini'))
    fireEvent.click(await screen.findByText(/advanced/i))
    expect(screen.getByDisplayValue('https://generativelanguage.googleapis.com')).toHaveAttribute('readonly')
  })

  test('set up automatically posts the setup mutation with the trimmed key', async () => {
    setupMutation.mockResolvedValue(SETUP_OK)
    renderModal()
    fireEvent.click(await screen.findByText('OpenAI'))
    fireEvent.change(await screen.findByLabelText(/api key/i), { target: { value: '  sk-test  ' } })
    fireEvent.click(screen.getByRole('button', { name: /set up automatically/i }))

    await waitFor(() =>
      expect(setupMutation).toHaveBeenCalledWith('openai', { api_key: 'sk-test', name: null })
    )
    expect(await screen.findByText(/connected/i)).toBeInTheDocument()
    expect(screen.getByText('whisper-1')).toBeInTheDocument()
  })

  test('edited base URL routes through the manual form', async () => {
    createProvider.mockResolvedValue({
      id: 7, name: 'OpenAI relay', type: 'openai_compatible',
      base_url: 'https://relay.test/v1', preset_key: null, enabled: true,
      is_local: false, country: null, masked_key: null, status: { model_count: 3 },
      created_at: '',
    })
    renderModal()
    fireEvent.click(await screen.findByText('OpenAI'))
    fireEvent.change(await screen.findByLabelText(/connection name/i), { target: { value: 'OpenAI relay' } })
    fireEvent.change(await screen.findByLabelText(/api key$/i), { target: { value: 'sk-test' } })
    fireEvent.click(screen.getByText(/advanced/i))
    fireEvent.change(screen.getByLabelText(/base url/i), { target: { value: 'https://relay.test/v1' } })
    fireEvent.click(screen.getByRole('button', { name: /set up automatically/i }))

    await waitFor(() =>
      expect(createProvider).toHaveBeenCalledWith({
        name: 'OpenAI relay',
        type: 'openai_compatible',
        base_url: 'https://relay.test/v1',
        api_key: 'sk-test',
        is_local: false,
        country: null,
      })
    )
    expect(setupMutation).not.toHaveBeenCalled()
  })

  test('classified error shows the i18n route and suspected vendor hint', async () => {
    setupMutation.mockRejectedValue(
      new ApiError('setup failed: 422', 422, {
        code: 'invalid_key',
        suspected_vendor: 'openrouter',
        detail: 'Incorrect API key provided',
      })
    )
    renderModal()
    fireEvent.click(await screen.findByText('OpenAI'))
    fireEvent.change(await screen.findByLabelText(/api key$/i), { target: { value: 'sk-or-v1-abc' } })
    fireEvent.click(screen.getByRole('button', { name: /set up automatically/i }))

    expect(
      await screen.findByText('The API key was rejected — check it and try again.')
    ).toBeInTheDocument()
    expect(
      screen.getByText('This looks like a openrouter key pasted into the wrong field.')
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /choose another provider/i })).toBeInTheDocument()
  })

  test('local preset hides the key field and footer can go back to tiles', async () => {
    renderModal()
    fireEvent.click(await screen.findByText('Ollama (local)'))
    expect(screen.queryByLabelText(/api key$/i)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /choose another provider/i }))
    expect(await screen.findByText('Google Gemini')).toBeInTheDocument()
  })

  test('custom tile opens the manual form with full fields', async () => {
    createProvider.mockResolvedValue({
      id: 9, name: 'LM Studio', type: 'openai_compatible', base_url: 'http://localhost:1234/v1',
      preset_key: null, enabled: true, is_local: true, country: null, masked_key: null, status: null,
      created_at: '',
    })
    renderModal()
    fireEvent.click(await screen.findByText(/custom/i))
    expect(await screen.findByLabelText(/^name$/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/base url/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /local \/ on-premise/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cloud' })).toBeInTheDocument()
    expect(screen.getByLabelText(/country$/i)).toBeInTheDocument()

    fireEvent.change(await screen.findByLabelText(/^name$/i), { target: { value: 'LM Studio' } })
    fireEvent.change(screen.getByLabelText(/base url/i), { target: { value: 'http://localhost:1234/v1' } })
    fireEvent.click(screen.getByRole('button', { name: /^add$/i }))

    await waitFor(() =>
      expect(createProvider).toHaveBeenCalledWith({
        name: 'LM Studio',
        type: 'openai_compatible',
        base_url: 'http://localhost:1234/v1',
        api_key: null,
        is_local: false,
        country: null,
      })
    )
    expect(setupMutation).not.toHaveBeenCalled()
  })
})
