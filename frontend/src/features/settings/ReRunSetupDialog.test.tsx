import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { ApiError } from '@/lib/api'
import type { Provider } from '@/lib/api'

import { ReRunSetupDialog } from './ReRunSetupDialog'

const listPresets = vi.fn()
const listTaskDefaults = vi.fn()
const setupMutation = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listPresets: () => listPresets(),
    listTaskDefaults: () => listTaskDefaults(),
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
    key_url: null,
    preferred_model: { id: 'gpt-5.6-terra', name: 'GPT-5.6 Terra', caps: ['text', 'tools', 'vision'] },
    curated_models: ['gpt-5.6-terra', 'gpt-5.6-luna', 'whisper-1'],
    stt_model: 'whisper-1',
    steps: null,
    free_tier_note: null,
  },
  gemini: {
    name: 'Google Gemini',
    type: 'google',
    base_url: 'https://generativelanguage.googleapis.com',
    fixed_base: true,
    local: false,
    key_url: null,
    preferred_model: { id: 'gemini-3.8-flash', name: 'Gemini 3.8 Flash', caps: ['text', 'tools', 'vision'] },
    curated_models: ['gemini-3.8-flash'],
    stt_model: null,
    steps: null,
    free_tier_note: null,
  },
}

const PROVIDER: Provider = {
  id: 3,
  name: 'Google Gemini',
  type: 'google',
  base_url: 'https://generativelanguage.googleapis.com',
  preset_key: 'gemini',
  enabled: true,
  is_local: false,
  country: null,
  masked_key: '••••xv4s',
  status: null,
  created_at: '',
}

const TASK_DEFAULTS = [
  { requires: 'text', model_id: null, fallback_model_id: null, model_label: null, fallback_model_label: null },
  { requires: 'vision', model_id: 42, fallback_model_id: null, model_label: 'gemini-2.5-flash', fallback_model_label: null },
  { requires: 'stt', model_id: null, fallback_model_id: null, model_label: null, fallback_model_label: null },
  { requires: 'embeddings', model_id: null, fallback_model_id: null, model_label: null, fallback_model_label: null },
]

function renderDialog(provider: Provider = PROVIDER) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ReRunSetupDialog provider={provider} onClose={() => {}} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  listPresets.mockReset()
  listTaskDefaults.mockReset()
  setupMutation.mockReset()
  listPresets.mockResolvedValue(PRESETS)
  listTaskDefaults.mockResolvedValue(TASK_DEFAULTS)
})

describe('ReRunSetupDialog', () => {
  test('uses the stored key and pre-selects the curated models', async () => {
    setupMutation.mockResolvedValue({ ok: true })
    renderDialog()
    expect(await screen.findByText(/uses the stored key for/i)).toBeInTheDocument()
    const card = await screen.findByRole('button', { pressed: true, name: /gemini-3\.8-flash/i })
    expect(card).toBeInTheDocument()
    expect(screen.getByText(/existing assignments and models are never removed/i)).toBeInTheDocument()
  })

  test('shows fill rows with the current values; stt row hidden without a preset stt model', async () => {
    renderDialog()
    expect(await screen.findByText(/fill the empty default chat model/i)).toBeInTheDocument()
    expect(await screen.findByText('now: unset')).toBeInTheDocument()
    expect(screen.getByText(/fill the empty default vision model/i)).toBeInTheDocument()
    expect(screen.getByText('now: gemini-2.5-flash')).toBeInTheDocument()
    expect(screen.queryByText(/fill the empty default transcription model/i)).not.toBeInTheDocument()
  })

  test('apply posts setup with the stored key, curated ids and bind toggles', async () => {
    setupMutation.mockResolvedValue({ ok: true })
    renderDialog()
    await screen.findByText(/uses the stored key for/i)
    await screen.findByRole('button', { pressed: true, name: /gemini-3\.8-flash/i })
    fireEvent.click(screen.getByRole('button', { name: /^apply$/i }))

    await waitFor(() =>
      expect(setupMutation).toHaveBeenCalledWith('gemini', {
        api_key: null,
        options: { curated_ids: ['gemini-3.8-flash'], bind_chat: true, bind_vision: true, bind_stt: true },
      })
    )
  })

  test('deselecting a curated card drops it from curated_ids', async () => {
    setupMutation.mockResolvedValue({ ok: true })
    const first = renderDialog()
    await screen.findByText(/uses the stored key for/i)
    fireEvent.click(await screen.findByRole('button', { name: /gemini-3\.8-flash/i }))
    expect(screen.getByRole('button', { name: /gemini-3\.8-flash/i })).toHaveAttribute('aria-pressed', 'false')
    first.unmount()

    const openai: Provider = { ...PROVIDER, id: 4, name: 'OpenAI', type: 'openai_compatible', preset_key: 'openai' }
    const second = renderDialog(openai)
    await screen.findByText(/uses the stored key for/i)
    expect(await screen.findByRole('button', { pressed: true, name: /whisper-1/i })).toBeInTheDocument()
    expect(screen.getByText(/fill the empty default transcription model/i)).toBeInTheDocument()
    second.unmount()
    expect(setupMutation).not.toHaveBeenCalled()
  })

  test('classified error routes through i18n with the vendor hint', async () => {
    setupMutation.mockRejectedValue(
      new ApiError('setup failed: 422', 422, {
        code: 'invalid_key',
        suspected_vendor: 'openrouter',
        detail: 'Incorrect API key provided',
      })
    )
    renderDialog()
    await screen.findByText(/uses the stored key for/i)
    await screen.findByRole('button', { pressed: true, name: /gemini-3\.8-flash/i })
    fireEvent.click(screen.getByRole('button', { name: /^apply$/i }))

    expect(
      await screen.findByText('The API key was rejected — check it and try again.')
    ).toBeInTheDocument()
    expect(
      screen.getByText('This looks like a openrouter key pasted into the wrong field.')
    ).toBeInTheDocument()
  })
})
