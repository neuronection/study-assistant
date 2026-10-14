import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { ApiError } from '@/lib/api'

import { ProviderSetupModal } from './ProviderSetupModal'

const listPresets = vi.fn()
const setupMutation = vi.fn()
const createProvider = vi.fn()
const listModels = vi.fn()
const listTaskDefaults = vi.fn()
const assignTaskDefault = vi.fn()
const clipboardWrite = vi.fn().mockResolvedValue(undefined)

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listPresets: () => listPresets(),
    setupProviderPreset: (presetKey: string, body: unknown) => setupMutation(presetKey, body),
    createProvider: (body: unknown) => createProvider(body),
    listModels: () => listModels(),
    listTaskDefaults: () => listTaskDefaults(),
    assignTaskDefault: (requires: string, modelId: number | null, fallback: number | null) =>
      assignTaskDefault(requires, modelId, fallback),
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
  assigned_embeddings_model: null,
}

function renderModal() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ProviderSetupModal onClose={() => {}} />
    </QueryClientProvider>,
  )
}

const PROVIDER_MODELS = [
  { id: 11, provider_id: 1, external_id: 'gpt-5.6-terra', label: 'GPT-5.6 Terra', caps: ['text', 'vision', 'tools'], enabled: true, missing: false, reasoning_effort: null },
  { id: 12, provider_id: 1, external_id: 'whisper-1', label: 'whisper-1', caps: ['stt'], enabled: true, missing: false, reasoning_effort: null },
]
const TASK_DEFAULTS = [
  { requires: 'text', model_id: null, fallback_model_id: null, model_label: null, fallback_model_label: null },
  { requires: 'vision', model_id: null, fallback_model_id: null, model_label: null, fallback_model_label: null },
  { requires: 'stt', model_id: null, fallback_model_id: null, model_label: null, fallback_model_label: null },
  { requires: 'embeddings', model_id: null, fallback_model_id: null, model_label: null, fallback_model_label: null },
  { requires: 'decision', model_id: null, fallback_model_id: null, model_label: null, fallback_model_label: null },
]

beforeEach(() => {
  listPresets.mockReset()
  setupMutation.mockReset()
  createProvider.mockReset()
  listModels.mockReset()
  listTaskDefaults.mockReset()
  assignTaskDefault.mockReset()
  listModels.mockResolvedValue(PROVIDER_MODELS)
  listTaskDefaults.mockResolvedValue(TASK_DEFAULTS)
  assignTaskDefault.mockResolvedValue(TASK_DEFAULTS[0])
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

  test('the docs-verified decision-only preset renders a tile (exposure switch flipped, §13.3 superseded)', async () => {
    listPresets.mockResolvedValue({
      ...PRESETS,
      typesafe: {
        name: 'TypeSafe',
        type: 'decision',
        base_url: 'https://api.typesafe.ai',
        fixed_base: false,
        local: false,
        key_url: 'https://docs.typesafe.ai/api',
        preferred_model: null,
        curated_models: null,
        stt_model: null,
        decision_models: [
          {
            id: 'jev-latest',
            name: 'Jev (latest)',
            transport: 'systemone',
            caps: ['tool-dispatch', 'boolean-gate', 'choice', 'score'],
          },
        ],
        decision_default: 'jev-latest',
        provisional: null,
        steps: null,
        free_tier_note: null,
      },
    })
    renderModal()

    await screen.findByText('OpenAI')
    const typesafeTile = screen.getByRole('button', { name: /TypeSafe/ })
    expect(typesafeTile).toBeInTheDocument()
    const gemini = screen.getByRole('button', { name: /Google Gemini/ })
    const ollama = screen.getByRole('button', { name: /Ollama/ })
    expect(gemini.compareDocumentPosition(typesafeTile) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(typesafeTile.compareDocumentPosition(ollama) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
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

  test('setup walks connect (bind-less) → review → apply (binds) → done', async () => {
    setupMutation.mockResolvedValue(SETUP_OK)
    renderModal()
    fireEvent.click(await screen.findByText('OpenAI'))
    fireEvent.change(await screen.findByLabelText(/api key/i), { target: { value: '  sk-test  ' } })
    fireEvent.click(screen.getByRole('button', { name: /set up automatically/i }))

    // connect registers only — binds stay off, the review step decides
    await waitFor(() =>
      expect(setupMutation).toHaveBeenCalledWith('openai', {
        api_key: 'sk-test',
        name: null,
        options: {
          bind_chat: false,
          bind_vision: false,
          bind_stt: false,
          bind_embeddings: false,
          bind_decision: false,
        },
      })
    )
    // step 2 is explicit: the wizard header names it, and the assignment
    // rows carry now/fills context per task (terra serves chat and vision)
    expect(await screen.findByText('Choose defaults')).toBeInTheDocument()
    expect(screen.getByText('Default assignments')).toBeInTheDocument()
    expect(screen.getAllByText(/fills: gpt-5\.6-terra/)).toHaveLength(2)
    expect(screen.getByRole('switch', { name: /^Chat/ })).not.toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: /apply/i }))
    await waitFor(() =>
      expect(setupMutation).toHaveBeenLastCalledWith('openai', {
        api_key: 'sk-test',
        name: null,
        options: {
          curated_ids: ['gpt-5.6-terra', 'whisper-1'],
          bind_chat: true,
          bind_vision: true,
          bind_stt: true,
          bind_decision: false,
        },
      })
    )
    expect(await screen.findByText(/connected/i)).toBeInTheDocument()
    expect(screen.getByText('whisper-1')).toBeInTheDocument()
  })

  test('setup: review offers the decision default for decision-capable presets', async () => {
    listPresets.mockResolvedValue({
      ...PRESETS,
      openrouter: {
        name: 'OpenRouter',
        type: 'openai_compatible',
        base_url: 'https://openrouter.ai/api/v1',
        fixed_base: false,
        local: false,
        key_url: null,
        preferred_model: { id: 'openrouter/auto', name: 'Auto', caps: ['text', 'tools'] },
        curated_models: ['openrouter/auto'],
        stt_model: null,
        decision_models: [
          {
            id: 'openrouter.jev-latest',
            name: 'Jev via OpenRouter (latest)',
            transport: 'systemone',
            caps: ['tool-dispatch', 'boolean-gate', 'choice', 'score'],
            provisional: true,
          },
        ],
        decision_default: 'openrouter.jev-latest',
        provisional: null,
        steps: null,
        free_tier_note: null,
      },
    })
    listModels.mockResolvedValue([
      ...PROVIDER_MODELS,
      {
        id: 13, provider_id: 1, external_id: 'openrouter.jev-latest', label: 'Jev via OpenRouter',
        caps: ['decision'], decision_transport: 'systemone', enabled: true, missing: false,
        reasoning_effort: null,
      },
    ])
    setupMutation.mockResolvedValue({
      ...SETUP_OK,
      provider: { ...SETUP_OK.provider, name: 'OpenRouter', preset_key: 'openrouter' },
      assigned_decision_slots: { decision: 'openrouter.jev-latest' },
    })
    renderModal()
    fireEvent.click(await screen.findByText('OpenRouter'))
    fireEvent.change(await screen.findByLabelText(/api key$/i), { target: { value: 'sk-or-key' } })
    fireEvent.click(screen.getByRole('button', { name: /set up automatically/i }))

    // review: the decision default row names the model it would bind
    // (openrouter declares decision models; the Jev card never rides the
    // curated list, so the sub-line is where it must surface)
    expect(await screen.findByText('Default decision model')).toBeInTheDocument()
    expect(
      await screen.findByText(/fills: Jev via OpenRouter \(latest\)/)
    ).toBeInTheDocument()
    // auto has no vision caps and no other card carries them — the vision
    // switch honestly reports "no model selected" and stays disabled
    expect(screen.getByText(/no model selected/)).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: /^Vision/ })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: /apply/i }))
    await waitFor(() =>
      expect(setupMutation).toHaveBeenLastCalledWith(
        'openrouter',
        expect.objectContaining({
          options: expect.objectContaining({ bind_decision: true }),
        })
      )
    )
    // done: the registered decision model feeds the default-decision picker
    expect(await screen.findByText('Default decision model')).toBeInTheDocument()
    expect(screen.queryByText('Tool dispatch')).not.toBeInTheDocument()
    expect(screen.queryByText('Boolean gate')).not.toBeInTheDocument()
    expect(screen.queryByText('Choice')).not.toBeInTheDocument()
    expect(screen.queryByText('Score')).not.toBeInTheDocument()
    const decisionPicker = screen.getByRole('combobox', { name: 'Default decision model' })
    fireEvent.click(decisionPicker)
    const jevOption = await screen.findByRole('option', { name: /jev via openrouter/i })
    const decisionListbox = jevOption.closest('[role="listbox"]')
    expect(decisionListbox).not.toBeNull()
    const decisionOptions = Array.from(
      decisionListbox!.querySelectorAll('[role="option"]')
    ).map((option) => option.textContent)
    expect(decisionOptions).toHaveLength(1)
    expect(decisionOptions[0]).toMatch(/jev via openrouter/i)
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
