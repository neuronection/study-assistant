import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from '@tanstack/react-router'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, test, vi } from 'vitest'

import { SettingsPage } from './SettingsPage'

vi.mock('@/features/spike/SpikePage', () => ({
  SpikeContent: () => <div>spike-content</div>,
}))

const listProviders = vi.fn()
const listPresets = vi.fn()
const setupProviderPreset = vi.fn()
const listModels = vi.fn()
const listTasks = vi.fn()
const listTaskDefaults = vi.fn()
const createProvider = vi.fn()
const updateProvider = vi.fn()
const testProvider = vi.fn()
const listRemoteModels = vi.fn()
const createModel = vi.fn()
const updateModel = vi.fn()
const deleteModel = vi.fn()
const assignTask = vi.fn()
const assignTaskDefault = vi.fn()
const deleteProvider = vi.fn()
const listMySessions = vi.fn().mockResolvedValue([])
const listAdminUsers = vi.fn().mockResolvedValue([])
const getCurrentUser = vi.fn().mockReturnValue(null)

vi.mock('@/lib/auth-session', () => ({
  getCurrentUser: () => getCurrentUser(),
  setCurrentUser: vi.fn(),
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listMySessions: () => listMySessions(),
    listAdminUsers: () => listAdminUsers(),
    listProviders: () => listProviders(),
    listPresets: () => listPresets(),
    listModels: () => listModels(),
    listTasks: () => listTasks(),
    listTaskDefaults: () => listTaskDefaults(),
    createProvider: (...args: unknown[]) => createProvider(...(args as [object])),
    setupProviderPreset: (...args: unknown[]) =>
      setupProviderPreset(...(args as [string, object])),
    updateProvider: (...args: unknown[]) =>
      updateProvider(...(args as [number, object])),
    testProvider: (...args: unknown[]) => testProvider(...(args as [number])),
    listRemoteModels: (...args: unknown[]) =>
      listRemoteModels(...(args as [number])),
    createModel: (...args: unknown[]) => createModel(...(args as [object])),
    updateModel: (...args: unknown[]) => updateModel(...(args as [number, object])),
    deleteModel: (...args: unknown[]) => deleteModel(...(args as [number])),
    assignTask: (...args: unknown[]) => assignTask(...(args as [string, number | null])),
    assignTaskDefault: (...args: unknown[]) =>
      assignTaskDefault(...(args as [string, number | null, number | null])),
    deleteProvider: (...args: unknown[]) => deleteProvider(...(args as [number])),
  }
})

const PRESETS = {
  openai: { name: 'OpenAI', type: 'openai_compatible', base_url: 'https://api.openai.com/v1', fixed_base: false, local: false, key_url: null, preferred_model: null, curated_models: null, stt_model: null, steps: null, free_tier_note: null },
  gemini: { name: 'Google Gemini', type: 'google', base_url: 'https://generativelanguage.googleapis.com', fixed_base: true, local: false, key_url: null, preferred_model: null, curated_models: null, stt_model: null, steps: null, free_tier_note: null },
  anthropic: { name: 'Anthropic', type: 'anthropic', base_url: 'https://api.anthropic.com', fixed_base: true, local: false, key_url: null, preferred_model: null, curated_models: null, stt_model: null, steps: null, free_tier_note: null },
  ollama: { name: 'Ollama (local)', type: 'openai_compatible', base_url: 'http://localhost:11434/v1', fixed_base: false, local: true, key_url: null, preferred_model: null, curated_models: null, stt_model: null, steps: null, free_tier_note: null },
}

async function renderSettings(initial = '/settings') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const rootRoute = createRootRoute({ component: () => <Outlet /> })
  const settingsRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/settings',
    validateSearch: (search: Record<string, unknown>) => ({
      tab: typeof search.tab === 'string' ? search.tab : undefined,
      section: typeof search.section === 'string' ? search.section : undefined,
    }),
    component: () => <SettingsPage />,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([settingsRoute]),
    history: createMemoryHistory({ initialEntries: [initial] }),
  })
  const result = render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
  await screen.findByRole('navigation', { name: 'Settings sections' })
  return result
}

async function openAiSection(label: string) {
  fireEvent.click(screen.getByRole('button', { name: /^AI/ }))
  fireEvent.click(await screen.findByRole('tab', { name: label }))
}

const PROVIDER = {
  id: 1,
  name: 'Google Gemini',
  type: 'google',
  base_url: 'https://generativelanguage.googleapis.com',
  enabled: true,
  masked_key: '••••1234',
  status: { last_tested_at: '2026-08-18T00:00:00Z', ok: true, error: null, model_count: 43 },
  created_at: '2026-08-18T00:00:00Z',
}

describe('SettingsPage', () => {
  test('providers tab lists providers with no raw key — keyless ones flag it', async () => {
    listProviders.mockResolvedValue([PROVIDER])
    await await renderSettings('/settings?tab=ai&section=providers')
    expect(await screen.findByText('Google Gemini')).toBeInTheDocument()
    // the base URL rides as a discrete subtitle; a keyed provider shows no
    // key chip (implied) and the raw key never leaks
    expect(screen.getByText('https://generativelanguage.googleapis.com')).toBeInTheDocument()
    expect(screen.queryByTestId('provider-key-1')).not.toBeInTheDocument()
    expect(screen.queryByText(/••••1234/)).not.toBeInTheDocument()
    expect(screen.queryByText(/supersecret/i)).not.toBeInTheDocument()
  })

  test('providers tab shows hosting, country and disabled badges', async () => {
    listProviders.mockResolvedValue([
      {
        ...PROVIDER,
        id: 2,
        name: 'Local Ollama',
        is_local: true,
        country: 'DE',
        enabled: false,
        masked_key: null,
      },
      { ...PROVIDER, id: 3, name: 'Cloud Gemini', is_local: false, country: 'US' },
    ])
    await await renderSettings('/settings?tab=ai&section=providers')
    expect(await screen.findByText('Local Ollama')).toBeInTheDocument()
    expect(screen.getByTestId('provider-hosting-2')).toHaveTextContent('Local / on-premise')
    expect(screen.getByTestId('provider-country-2')).toHaveTextContent('🇩🇪 DE')
    expect(screen.getByTestId('provider-hosting-3')).toHaveTextContent('Cloud')
    expect(screen.getByTestId('provider-country-3')).toHaveTextContent('🇺🇸 US')
    // keyed provider → no key chip (implied); keyless provider → danger "no key" chip;
    // disabled provider → danger badge
    expect(screen.queryByTestId('provider-key-3')).not.toBeInTheDocument()
    expect(screen.getByTestId('provider-key-2')).toBeInTheDocument()
    expect(screen.getByTestId('provider-key-2')).toHaveTextContent('no key')
    expect(screen.getByText('Disabled')).toBeInTheDocument()
  })

  test('providers tab tests a provider from the actions menu', async () => {
    const user = userEvent.setup()
    listProviders.mockResolvedValue([PROVIDER])
    listModels.mockResolvedValue([
      {
        id: 11,
        provider_id: 1,
        external_id: 'gemini-2.5-flash',
        label: 'gemini-2.5-flash',
        caps: ['text'],
        decision_transport: null,
        enabled: true,
        missing: false,
        reasoning_effort: null,
      },
    ])
    testProvider.mockResolvedValue({
      ...PROVIDER,
      status: { last_tested_at: '2026-08-18T00:00:00Z', ok: true, error: null, model_count: 43 },
    })
    await await renderSettings('/settings?tab=ai&section=providers')
    expect(await screen.findByText('Google Gemini')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Actions for Google Gemini' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Test' }))
    await waitFor(() => expect(testProvider).toHaveBeenCalledWith(1))
    expect(await screen.findByText('Connected')).toBeInTheDocument()
  })

  test('providers tab omits the Test action without a registered model', async () => {
    listProviders.mockResolvedValue([PROVIDER])
    listModels.mockResolvedValue([])
    await await renderSettings('/settings?tab=ai&section=providers')
    expect(await screen.findByText('Google Gemini')).toBeInTheDocument()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Actions for Google Gemini' }))
    expect(await screen.findByRole('menuitem', { name: 'Edit' })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Test' })).toBeNull()
  })

  test('providers tab deletes a provider through the actions menu and confirm', async () => {
    listProviders.mockResolvedValue([PROVIDER])
    await await renderSettings('/settings?tab=ai&section=providers')
    expect(await screen.findByText('Google Gemini')).toBeInTheDocument()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Actions for Google Gemini' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Delete provider' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/delete this provider/i)).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete provider' }))
    await waitFor(() => expect(deleteProvider).toHaveBeenCalledWith(1))
  })

  test('models tab lists selected (enabled) models with a catalog trigger', async () => {
    listProviders.mockResolvedValue([PROVIDER])
    listModels.mockResolvedValue([
      {
        id: 11,
        provider_id: 1,
        external_id: 'gemini-2.5-flash',
        label: 'gemini-2.5-flash',
        caps: ['text', 'vision', 'tools'],
        enabled: true,
        missing: false,
      },
      {
        id: 12,
        provider_id: 1,
        external_id: 'gemini-2.5-pro',
        label: 'gemini-2.5-pro',
        caps: ['text'],
        enabled: false,
        missing: false,
      },
    ])
    await await renderSettings()
    await openAiSection('Models')
    expect(await screen.findByText('gemini-2.5-flash')).toBeInTheDocument()
    expect(screen.getAllByText('Vision').length).toBeGreaterThan(0)
    expect(screen.queryByText('gemini-2.5-pro')).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    const browse = screen.getByRole('button', { name: 'Add model' })
    expect(browse).toHaveAttribute('aria-expanded', 'false')
  })

  test('tasks tab lists tasks with requirement badges', async () => {
    listProviders.mockResolvedValue([PROVIDER])
    listTaskDefaults.mockResolvedValue([])
    listTasks.mockResolvedValue([
      {
        task: 'ocr',
        description: 'Page & handwriting OCR',
        requires: 'vision',
        model_id: null,
        fallback_model_id: null,
        model_label: null,
        fallback_model_label: null,
        inherits_default: false,
        default_model_label: null,
      },
    ])
    listModels.mockResolvedValue([])
    await await renderSettings()
    await openAiSection('Tasks')
    expect(await screen.findByText('OCR')).toBeInTheDocument()
    expect(screen.getByText('Vision')).toBeInTheDocument()
    expect(
      screen.getAllByRole('combobox', { name: 'OCR' })[0],
    ).toHaveTextContent(/select a model/i)
  })

  test('tasks tab nudges on unassigned embeddings and concepts', async () => {
    listProviders.mockResolvedValue([PROVIDER])
    listTaskDefaults.mockResolvedValue([])
    listTasks.mockResolvedValue([
      {
        task: 'embeddings',
        description: 'Chunk embeddings',
        requires: 'embeddings',
        model_id: null,
        fallback_model_id: null,
        model_label: null,
        fallback_model_label: null,
        inherits_default: false,
        default_model_label: null,
      },
      {
        task: 'concepts',
        description: 'Concept extraction',
        requires: 'text',
        model_id: null,
        fallback_model_id: null,
        model_label: null,
        fallback_model_label: null,
        inherits_default: false,
        default_model_label: null,
      },
    ])
    listModels.mockResolvedValue([])
    await await renderSettings()
    await openAiSection('Tasks')
    expect(
      await screen.findByText(/semantic search is off/i),
    ).toBeInTheDocument()
    expect(screen.getByText(/concept extraction is unavailable/i)).toBeInTheDocument()
  })

  test('tasks tab shows default models section and inherited task model', async () => {
    listProviders.mockResolvedValue([PROVIDER])
    listTaskDefaults.mockResolvedValue([
      {
        requires: 'text',
        model_id: 11,
        fallback_model_id: null,
        model_label: 'gemini-2.5-flash',
        fallback_model_label: null,
      },
      { requires: 'vision', model_id: null, fallback_model_id: null, model_label: null, fallback_model_label: null },
      { requires: 'embeddings', model_id: null, fallback_model_id: null, model_label: null, fallback_model_label: null },
    ])
    listTasks.mockResolvedValue([
      {
        task: 'quizgen',
        description: 'Quiz question generation',
        requires: 'text',
        model_id: null,
        fallback_model_id: null,
        model_label: null,
        fallback_model_label: null,
        inherits_default: true,
        default_model_label: 'gemini-2.5-flash',
      },
    ])
    listModels.mockResolvedValue([
      {
        id: 11,
        provider_id: 1,
        external_id: 'gemini-2.5-flash',
        label: 'gemini-2.5-flash',
        caps: ['text', 'vision', 'tools'],
        enabled: true,
        missing: false,
      },
    ])
    await await renderSettings()
    await openAiSection('Tasks')
    expect(await screen.findByText(/default models/i)).toBeInTheDocument()
    expect(screen.getByText(/one default per capability/i)).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'LLM' })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Vision' })).toBeInTheDocument()
    expect((await screen.findAllByRole('combobox')).length).toBeGreaterThanOrEqual(5)
    expect(await screen.findByText(/Inherited — using gemini-2.5-flash/)).toBeInTheDocument()
  })

  test('tasks tab sends a task override when a custom model is picked', async () => {
    listProviders.mockResolvedValue([PROVIDER])
    listTaskDefaults.mockResolvedValue([])
    listTasks.mockResolvedValue([
      {
        task: 'quizgen',
        description: 'Quiz question generation',
        requires: 'text',
        model_id: null,
        fallback_model_id: null,
        model_label: null,
        fallback_model_label: null,
        inherits_default: false,
        default_model_label: null,
      },
    ])
    listModels.mockResolvedValue([
      {
        id: 11,
        provider_id: 1,
        external_id: 'gemini-2.5-flash',
        label: 'gemini-2.5-flash',
        caps: ['text', 'tools'],
        enabled: true,
        missing: false,
      },
    ])
    await await renderSettings()
    await openAiSection('Tasks')
    await screen.findByText('Quizgen')
    const trigger = screen.getAllByRole('combobox').at(-1)!
    fireEvent.click(trigger)
    const option = await screen.findByRole('option', { name: 'gemini-2.5-flash' })
    fireEvent.click(option)
    await waitFor(() => expect(assignTask).toHaveBeenCalledWith('quizgen', 11))
  })

  test('tasks tab sets a default model per capability', async () => {
    listProviders.mockResolvedValue([PROVIDER])
    listTaskDefaults.mockResolvedValue([
      { requires: 'text', model_id: null, fallback_model_id: null, model_label: null, fallback_model_label: null },
      { requires: 'vision', model_id: null, fallback_model_id: null, model_label: null, fallback_model_label: null },
      { requires: 'embeddings', model_id: null, fallback_model_id: null, model_label: null, fallback_model_label: null },
    ])
    listTasks.mockResolvedValue([])
    listModels.mockResolvedValue([
      {
        id: 11,
        provider_id: 1,
        external_id: 'gemini-2.5-flash',
        label: 'gemini-2.5-flash',
        caps: ['text', 'vision', 'tools'],
        enabled: true,
        missing: false,
      },
    ])
    await await renderSettings()
    await openAiSection('Tasks')
    await screen.findByText(/default models/i)
    const textPrimary = screen.getByRole('combobox', { name: 'LLM' })
    fireEvent.click(textPrimary)
    const option = await screen.findByRole('option', { name: 'gemini-2.5-flash' })
    fireEvent.click(option)
    await waitFor(() => expect(assignTaskDefault).toHaveBeenCalledWith('text', 11, null))
  })

  test('add provider opens the setup modal with the preset grid', async () => {
    listProviders.mockResolvedValue([])
    listPresets.mockResolvedValue(PRESETS)
    await renderSettings('/settings?tab=ai&section=providers')
    fireEvent.click(await screen.findByRole('button', { name: /add provider/i }))
    expect(await screen.findByText('Google Gemini')).toBeInTheDocument()
    expect(screen.getByText('OpenAI')).toBeInTheDocument()
    expect(screen.getByText(/custom/i)).toBeInTheDocument()
  })

  test('add provider: preset tile leads to the guided form with set-up-automatically', async () => {
    listProviders.mockResolvedValue([])
    listPresets.mockResolvedValue(PRESETS)
    listTaskDefaults.mockResolvedValue([])
    setupProviderPreset.mockResolvedValue({
      ok: true,
      provider: { ...PROVIDER, preset_key: 'openai' },
      catalog_count: 2,
      curated_missed: false,
      assigned_chat_model: 'gpt-5.6-terra',
      assigned_vision_model: null,
      assigned_stt_model: 'whisper-1',
    })
    await renderSettings('/settings?tab=ai&section=providers')
    fireEvent.click(await screen.findByRole('button', { name: /add provider/i }))
    fireEvent.click(await screen.findByText('OpenAI'))
    await screen.findByLabelText(/connection name/i)
    fireEvent.change(await screen.findByLabelText(/api key$/i), {
      target: { value: 'sk-test' },
    })
    fireEvent.click(screen.getByRole('button', { name: /set up automatically/i }))
    // connect registers only — binds stay off, the review step decides
    await waitFor(() =>
      expect(setupProviderPreset).toHaveBeenCalledWith('openai', {
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
    expect(await screen.findByText('Default assignments')).toBeInTheDocument()
  })

  test('add provider: custom tile keeps a typed name and requires a base URL', async () => {
    listProviders.mockResolvedValue([])
    listPresets.mockResolvedValue(PRESETS)
    createProvider.mockResolvedValue({ ...PROVIDER, name: 'LM Studio' })
    await renderSettings('/settings?tab=ai&section=providers')
    fireEvent.click(await screen.findByRole('button', { name: /add provider/i }))
    fireEvent.click(await screen.findByText(/custom/i))

    fireEvent.change(await screen.findByLabelText(/^name$/i), { target: { value: 'LM Studio' } })
    const submit = screen.getByRole('button', { name: /^add$/i })
    expect(submit).toBeDisabled()

    fireEvent.change(screen.getByLabelText(/base url/i), {
      target: { value: 'http://localhost:1234/v1' },
    })
    await waitFor(() => expect(submit).toBeEnabled())
    fireEvent.click(submit)
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
  })

  test('settings tabs are routable via the ?tab= and ?section= search params', async () => {
    listProviders.mockResolvedValue([PROVIDER])
    listModels.mockResolvedValue([])
    listTasks.mockResolvedValue([])
    listTaskDefaults.mockResolvedValue([])
    await renderSettings('/settings?tab=ai&section=models')
    expect(await screen.findByRole('button', { name: 'Add model' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: 'Tasks' }))
    await waitFor(() =>
      expect(screen.getByText(/default models/i)).toBeInTheDocument()
    )
  })

  test('web search and discovery live under the tools tab, not under AI providers', async () => {
    listProviders.mockResolvedValue([PROVIDER])
    await renderSettings('/settings?tab=ai&section=providers')
    expect(await screen.findByText('Google Gemini')).toBeInTheDocument()
    // tools.* domains never render under the ai tab (ADR-0033 INV-2)
    expect(screen.queryByText('Web search providers')).not.toBeInTheDocument()
    expect(screen.queryByTestId('discovery-card')).not.toBeInTheDocument()
  })

  test('the tools tab hosts web search by default and discovery via ?section=', async () => {
    await renderSettings('/settings?tab=tools')
    expect(await screen.findByText('Web search providers')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Web search' })).toHaveAttribute(
      'aria-selected',
      'true',
    )

    fireEvent.click(screen.getByRole('tab', { name: 'Discovery' }))
    expect(await screen.findByTestId('discovery-card')).toBeInTheDocument()
    expect(screen.queryByText('Web search providers')).not.toBeInTheDocument()
  })

  test('legacy ?tab=search deep links land on tools → Search & OCR', async () => {
    await renderSettings('/settings?tab=search')
    expect(await screen.findByText(/semantic search/i)).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Search & OCR' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
  })

  test('rail navigation switches top-level sections', async () => {
    await renderSettings()
    fireEvent.click(screen.getByRole('button', { name: /^data/i }))
    expect(await screen.findByText(/backup & restore/i)).toBeInTheDocument()
    expect(screen.queryByText('spike-content')).not.toBeInTheDocument()
  })

  test('the tools connectors section deep-links via ?section=', async () => {
    await renderSettings('/settings?tab=tools&section=connectors')
    expect((await screen.findAllByText(/mcp resource server/i)).length).toBeGreaterThan(0)
    expect(screen.getByRole('tab', { name: 'Integrations' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
  })

  test('legacy AI-section deep links for skills and mcp land in the tools tab', async () => {
    await renderSettings('/settings?tab=ai&section=skills')
    expect(await screen.findByText(/named behaviors per task/i)).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Skills' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
  })

  test('legacy ?tab=ai&section=mcp deep link lands on tools → Integrations', async () => {
    await renderSettings('/settings?tab=ai&section=mcp')
    expect((await screen.findAllByText(/mcp resource server/i)).length).toBeGreaterThan(0)
    expect(screen.getByRole('tab', { name: 'Integrations' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
  })

  test('the default tab is general with the language picker', async () => {
    await renderSettings()
    expect(await screen.findByRole('combobox', { name: 'Language' })).toBeInTheDocument()
    expect(screen.queryByText('Google Gemini')).not.toBeInTheDocument()
  })

  test('developer tab shows the rendering spike content only when selected', async () => {
    await renderSettings()
    expect(screen.queryByText('spike-content')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /^developer/i }))
    expect(await screen.findByText('spike-content')).toBeInTheDocument()
  })

  test('edit provider dialog patches without touching the key when blank', async () => {
    listProviders.mockResolvedValue([PROVIDER])
    await await renderSettings('/settings?tab=ai&section=providers')
    const user = userEvent.setup()
    await user.click(
      await screen.findByRole('button', { name: 'Actions for Google Gemini' }),
    )
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Edit' }))
    const nameInput = await screen.findByLabelText(/name/i)
    expect(nameInput).toHaveValue('Google Gemini')
    expect(
      screen.getByText(/a key is stored — leave blank to keep it/i)
    ).toBeInTheDocument()
    fireEvent.change(nameInput, { target: { value: 'Gemini main' } })
    screen.getByRole('button', { name: /^save$/i }).click()
    await waitFor(() =>
      expect(updateProvider).toHaveBeenCalledWith(
        1,
        expect.not.objectContaining({ api_key: expect.anything() })
      )
    )
    await waitFor(() =>
      expect(updateProvider).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ name: 'Gemini main', enabled: true })
      )
    )
  })

  test('models tab adds a model through the catalog modal', async () => {
    listProviders.mockResolvedValue([PROVIDER])
    listModels.mockResolvedValue([
      {
        id: 11,
        provider_id: 1,
        external_id: 'gemini-2.5-flash',
        label: 'gemini-2.5-flash',
        caps: ['text', 'vision', 'tools'],
        enabled: true,
        missing: false,
        temperature: null,
        max_tokens: null,
      },
    ])
    listRemoteModels.mockResolvedValue([
      { external_id: 'gemini-2.5-flash', caps: ['text', 'vision', 'tools'] },
      { external_id: 'gemini-2.5-pro', caps: ['text', 'vision', 'tools'] },
      { external_id: 'text-embedding-004', caps: ['embeddings'] },
    ])
    createModel.mockResolvedValue({
      id: 12,
      provider_id: 1,
      external_id: 'gemini-2.5-pro',
      label: 'gemini-2.5-pro',
      caps: ['text', 'vision', 'tools'],
      enabled: true,
      missing: false,
      temperature: null,
      max_tokens: null,
    })
    await await renderSettings()
    await openAiSection('Models')
    fireEvent.click(await screen.findByRole('button', { name: 'Add model' }))
    const dialog = await screen.findByRole('dialog')
    // step 1 — pick the LLM kind, then the catalog picker appears
    fireEvent.click(within(dialog).getByRole('button', { name: /^LLM/ }))

    const picker = await within(dialog).findByRole('combobox', { name: 'Model' })
    fireEvent.click(picker)
    fireEvent.click(await screen.findByRole('option', { name: 'gemini-2.5-pro' }))
    expect(
      within(dialog).getByRole('button', { name: 'Vision' }),
    ).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(within(dialog).getByRole('button', { name: 'Add model' }))
    await waitFor(() =>
      expect(createModel).toHaveBeenCalledWith(
        expect.objectContaining({
          provider_id: 1,
          external_id: 'gemini-2.5-pro',
          caps: ['text', 'vision', 'tools'],
          enabled: true,
          temperature: null,
          max_tokens: null,
        })
      )
    )
  })

  test('models tab adds decision models as a standalone kind with the transport seam', async () => {
    listProviders.mockResolvedValue([PROVIDER])
    listModels.mockResolvedValue([])
    listRemoteModels.mockRejectedValue(new Error('no key'))
    createModel.mockResolvedValue({
      id: 21,
      provider_id: 1,
      external_id: 'nimble',
      label: 'nimble',
      caps: ['decision'],
      decision_transport: 'systemone',
      enabled: true,
      missing: false,
    })
    await renderSettings()
    await openAiSection('Models')
    fireEvent.click(await screen.findByRole('button', { name: 'Add model' }))
    const dialog = await screen.findByRole('dialog')

    // step 1 — the decision kind card seeds caps and stamps the transport
    fireEvent.click(within(dialog).getByRole('button', { name: /^Decision/ }))
    expect(await within(dialog).findByText(/no key/i)).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: /manual/i }))
    await waitFor(() =>
      expect(within(dialog).getByLabelText('Model')).toBeInTheDocument(),
    )
    fireEvent.change(within(dialog).getByLabelText('Model'), {
      target: { value: 'nimble' },
    })
    // standalone kind: decision replaces the chat caps, hides the
    // generation options, and stamps the transport
    expect(within(dialog).getByText('Transport:')).toBeInTheDocument()
    expect(within(dialog).queryByLabelText('Temperature')).not.toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add model' }))
    await waitFor(() =>
      expect(createModel).toHaveBeenCalledWith(
        expect.objectContaining({
          external_id: 'nimble',
          caps: ['decision'],
          decision_transport: 'systemone',
        }),
      ),
    )
  })

  test('models tab offers manual add with cap correction when listing fails', async () => {    listProviders.mockResolvedValue([PROVIDER])
    listModels.mockResolvedValue([])
    listRemoteModels.mockRejectedValue(
      new Error(
        "401 — no API key is stored for this provider. Fix the key with the provider's Edit button, or add the model manually."
      )
    )
    createModel.mockResolvedValue({
      id: 13,
      provider_id: 1,
      external_id: 'gpt-9-turbo',
      label: 'gpt-9-turbo',
      caps: ['text'],
      enabled: true,
      missing: false,
    })
    await await renderSettings()
    await openAiSection('Models')
    fireEvent.click(await screen.findByRole('button', { name: 'Add model' }))
    const dialog = await screen.findByRole('dialog')
    // step 1 — the LLM kind (chat family pre-selected in step 2)
    fireEvent.click(within(dialog).getByRole('button', { name: /^LLM/ }))

    expect(await within(dialog).findByText(/no API key is stored/i)).toBeInTheDocument()

    fireEvent.click(within(dialog).getByRole('button', { name: /manual/i }))
    fireEvent.change(within(dialog).getByLabelText('Model'), {
      target: { value: 'gpt-9-turbo' },
    })
    // the chat family comes pre-selected (text+vision+tools); the correction
    // drops tools for this vision-only model
    fireEvent.click(within(dialog).getByRole('button', { name: 'Tools' }))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add model' }))

    await waitFor(() =>
      expect(createModel).toHaveBeenCalledWith(
        expect.objectContaining({
          provider_id: 1,
          external_id: 'gpt-9-turbo',
          caps: ['text', 'vision'],
          enabled: true,
        })
      )
    )
  })

  test('models tab deletes a model after confirmation', async () => {
    listProviders.mockResolvedValue([PROVIDER])
    listModels.mockResolvedValue([
      {
        id: 11,
        provider_id: 1,
        external_id: 'gemini-2.5-flash',
        label: 'gemini-2.5-flash',
        caps: ['text', 'vision', 'tools'],
        enabled: true,
        missing: false,
      },
    ])
    await await renderSettings()
    await openAiSection('Models')
    fireEvent.click(await screen.findByRole('button', { name: /delete model gemini-2\.5-flash/i }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete model' }))
    await waitFor(() => expect(deleteModel).toHaveBeenCalledWith(11))
  })

  test('models tab bulk-adds pending entries from the modal footer', async () => {
    listProviders.mockResolvedValue([PROVIDER])
    listModels.mockResolvedValue([])
    listRemoteModels.mockResolvedValue([
      { external_id: 'gemini-2.5-flash', caps: ['text', 'vision'] },
      { external_id: 'gemini-2.5-pro', caps: ['text'] },
      { external_id: 'text-embedding-004', caps: ['embeddings'] },
    ])
    createModel.mockResolvedValue({ id: 1 })
    createModel.mockClear()
    await await renderSettings()
    await openAiSection('Models')
    fireEvent.click(await screen.findByRole('button', { name: 'Add model' }))
    const dialog = await screen.findByRole('dialog')
    // step 1 — pick the LLM kind so the add-all footer action appears
    fireEvent.click(within(dialog).getByRole('button', { name: /^LLM/ }))

    fireEvent.click(within(dialog).getByRole('button', { name: /add all \(3\)/i }))

    await waitFor(() => expect(createModel).toHaveBeenCalledTimes(3))
    expect(createModel).toHaveBeenCalledWith(
      expect.objectContaining({ external_id: 'gemini-2.5-flash', enabled: true })
    )
    expect(createModel).toHaveBeenCalledWith(
      expect.objectContaining({ external_id: 'text-embedding-004', caps: ['embeddings'] })
    )
  })

  test('models tab edits label and caps in the draft panel', async () => {
    listProviders.mockResolvedValue([PROVIDER])
    listModels.mockResolvedValue([
      {
        id: 11,
        provider_id: 1,
        external_id: 'gemini-2.5-flash',
        label: 'gemini-2.5-flash',
        caps: ['text', 'vision', 'tools'],
        enabled: true,
        missing: false,
      },
    ])
    updateModel.mockResolvedValue({
      id: 11,
      provider_id: 1,
      external_id: 'gemini-2.5-flash',
      label: 'Flash',
      caps: ['text'],
      enabled: true,
      missing: false,
    })
    await await renderSettings()
    await openAiSection('Models')
    fireEvent.click(await screen.findByRole('button', { name: /edit model gemini-2\.5-flash/i }))
    const dialog = await screen.findByRole('dialog')

    const labelInput = await within(dialog).findByLabelText(/display name/i)
    fireEvent.change(labelInput, { target: { value: 'Flash' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Vision' }))

    fireEvent.click(within(dialog).getByRole('button', { name: /^save$/i }))
    await waitFor(() =>
      expect(updateModel).toHaveBeenCalledWith(11, {
        label: 'Flash',
        caps: ['text', 'tools'],
        reasoning_effort: null,
        temperature: null,
        max_tokens: null,
      })
    )
  })

  test('users tab appears for admins and lists the users', async () => {
    getCurrentUser.mockReturnValue({
      id: 'u-admin',
      email: 'ada@example.com',
      full_name: 'Ada Lovelace',
      is_admin: true,
      is_active: true,
    })
    listAdminUsers.mockResolvedValue([
      {
        id: 'u-admin',
        email: 'ada@example.com',
        full_name: 'Ada Lovelace',
        is_admin: true,
        is_active: true,
        created_at: '2026-01-01T00:00:00Z',
        activity_count: 3,
      },
    ])
    await renderSettings('/settings?tab=users')
    expect(screen.getAllByText('User management & account').length).toBeGreaterThan(0)
    expect(await screen.findByText('ada@example.com')).toBeInTheDocument()
  })

  test('users tab is hidden and unreachable for non-admins', async () => {
    getCurrentUser.mockReturnValue({
      id: 'u-plain',
      email: 'grace@example.com',
      full_name: '',
      is_admin: false,
      is_active: true,
    })
    await renderSettings('/settings?tab=users')
    expect(screen.queryAllByText('User management & account')).toHaveLength(0)
    // deep-linking `?tab=users` falls back to the general tab
    expect(await screen.findByRole('combobox', { name: 'Language' })).toBeInTheDocument()
  })
})
