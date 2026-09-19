import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { ApiError } from '@/lib/api'

import { SetupPresetsCard } from './SetupPresetsCard'

const listPresets = vi.fn()
const setupMutation = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listPresets: () => listPresets(),
    setupProviderPreset: (presetKey: string, body: unknown) => setupMutation(presetKey, body),
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

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SetupPresetsCard />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  listPresets.mockReset()
  setupMutation.mockReset()
  listPresets.mockResolvedValue(PRESETS)
})

describe('SetupPresetsCard', () => {
  test('renders neutral tiles in the canonical family order', async () => {
    renderCard()
    const openai = await screen.findByText('OpenAI')
    const gemini = screen.getByText('Google Gemini')
    const ollama = screen.getByText('Ollama (local)')
    expect(openai.compareDocumentPosition(gemini) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(gemini.compareDocumentPosition(ollama) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  test('guided connect posts the setup mutation with the key', async () => {
    setupMutation.mockResolvedValue({
      ok: true,
      provider: { id: 1, name: 'OpenAI', type: 'openai_compatible', base_url: '', preset_key: 'openai', enabled: true, is_local: false, country: null, masked_key: null, status: null, created_at: '' },
      catalog_count: 2,
      curated_missed: false,
      assigned_chat_model: 'gpt-5.6-terra',
      assigned_vision_model: 'gpt-5.6-terra',
      assigned_stt_model: 'whisper-1',
    })
    renderCard()
    fireEvent.click(await screen.findByText('OpenAI'))
    const keyInput = screen.getByLabelText(/api key/i)
    fireEvent.change(keyInput, { target: { value: '  sk-test  ' } })
    fireEvent.click(screen.getByRole('button', { name: /connect/i }))

    await waitFor(() => {
      expect(setupMutation).toHaveBeenCalledWith('openai', {
        api_key: 'sk-test',
        name: null,
      })
    })
    expect(await screen.findByText(/connected/i)).toBeInTheDocument()
    expect(screen.getByText('whisper-1')).toBeInTheDocument()
    expect(screen.queryByText(/full list was saved/i)).not.toBeInTheDocument()
  })

  test('classified error shows the i18n route and suspected vendor hint', async () => {
    setupMutation.mockRejectedValue(
      new ApiError('setup failed: 422', 422, {
        code: 'invalid_key',
        suspected_vendor: 'openrouter',
        detail: 'Incorrect API key provided',
      })
    )
    renderCard()
    fireEvent.click(await screen.findByText('OpenAI'))
    const keyInput = screen.getByLabelText(/api key/i)
    fireEvent.change(keyInput, { target: { value: 'sk-or-v1-abc' } })
    fireEvent.click(screen.getByRole('button', { name: /connect/i }))

    expect(
      await screen.findByText('The API key was rejected — check it and try again.')
    ).toBeInTheDocument()
    expect(
      screen.getByText('This looks like a openrouter key pasted into the wrong field.')
    ).toBeInTheDocument()
    expect(screen.getByText('Incorrect API key provided')).toBeInTheDocument()
  })

  test('local preset needs no key field', async () => {
    renderCard()
    fireEvent.click(await screen.findByText('Ollama (local)'))
    expect(screen.queryByLabelText(/api key/i)).not.toBeInTheDocument()
  })

  test('free tier note and key link render for gemini', async () => {
    renderCard()
    fireEvent.click(await screen.findByText('Google Gemini'))
    expect(screen.getByText(/free AI Studio tier/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /get an api key/i })).toHaveAttribute(
      'href',
      'https://aistudio.google.com/app/apikey'
    )
  })
})
