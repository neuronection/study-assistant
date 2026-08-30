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
import { describe, expect, test, vi } from 'vitest'

import { SettingsPage } from './SettingsPage'

vi.mock('@/features/spike/SpikePage', () => ({
  SpikeContent: () => <div>spike-content</div>,
}))

const listProviders = vi.fn()
const listPresets = vi.fn()
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

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listProviders: () => listProviders(),
    listPresets: () => listPresets(),
    listModels: () => listModels(),
    listTasks: () => listTasks(),
    listTaskDefaults: () => listTaskDefaults(),
    createProvider: (...args: unknown[]) => createProvider(...(args as [object])),
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
  google: { name: 'Google Gemini', type: 'google', base_url: 'https://generativelanguage.googleapis.com' },
  openai: { name: 'OpenAI', type: 'openai_compatible', base_url: 'https://api.openai.com/v1' },
  anthropic: { name: 'Anthropic', type: 'anthropic', base_url: 'https://api.anthropic.com' },
  ollama: { name: 'Ollama (local)', type: 'openai_compatible', base_url: 'http://localhost:11434/v1' },
}

async function renderSettings(initial = '/settings') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const rootRoute = createRootRoute({ component: () => <Outlet /> })
  const settingsRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/settings',
    validateSearch: (search: Record<string, unknown>) => ({
      tab: typeof search.tab === 'string' ? search.tab : undefined,
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
  await screen.findByRole('heading', { name: /settings/i })
  return result
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
  test('providers tab lists providers with masked key', async () => {
    listProviders.mockResolvedValue([PROVIDER])
    await await renderSettings()
    expect(await screen.findByText('Google Gemini')).toBeInTheDocument()
    expect(screen.getByText(/••••1234/)).toBeInTheDocument()
    expect(screen.queryByText(/supersecret/i)).not.toBeInTheDocument()
  })

  test('models tab shows only selected (enabled) models', async () => {
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
    screen.getByRole('button', { name: /models/i }).click()
    expect(await screen.findByText('gemini-2.5-flash')).toBeInTheDocument()
    expect(screen.getByText('vision')).toBeInTheDocument()
    expect(screen.queryByText('gemini-2.5-pro')).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  })

  test('tasks tab lists tasks with requirement badges', async () => {
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
        default_fallback_model_label: null,
      },
    ])
    listModels.mockResolvedValue([])
    await await renderSettings()
    screen.getByRole('button', { name: /tasks/i }).click()
    expect(await screen.findByText('ocr')).toBeInTheDocument()
    expect(screen.getByText('vision')).toBeInTheDocument()
    expect(screen.getAllByText('— unassigned —').length).toBeGreaterThan(0)
  })

  test('tasks tab nudges on unassigned embeddings and concepts', async () => {
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
        default_fallback_model_label: null,
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
        default_fallback_model_label: null,
      },
    ])
    listModels.mockResolvedValue([])
    await await renderSettings()
    screen.getByRole('button', { name: /tasks/i }).click()
    expect(
      await screen.findByText(/semantic search is off/i),
    ).toBeInTheDocument()
    expect(screen.getByText(/concept extraction is unavailable/i)).toBeInTheDocument()
  })

  test('tasks tab shows default models section and inherited task model', async () => {
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
        default_fallback_model_label: null,
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
    screen.getByRole('button', { name: /tasks/i }).click()
    expect(await screen.findByText(/default models/i)).toBeInTheDocument()
    expect(screen.getAllByText(/Default text model/).length).toBeGreaterThan(0)
    expect((await screen.findAllByRole('combobox')).length).toBeGreaterThanOrEqual(5)
    expect(await screen.findByText(/Inherited — using gemini-2.5-flash/)).toBeInTheDocument()
  })

  test('tasks tab sends a task override when a custom model is picked', async () => {
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
        default_fallback_model_label: null,
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
    screen.getByRole('button', { name: /tasks/i }).click()
    await screen.findByText('quizgen')
    const trigger = screen.getAllByRole('combobox').at(-1)!
    fireEvent.click(trigger)
    const option = await screen.findByRole('option', { name: 'gemini-2.5-flash' })
    fireEvent.click(option)
    await waitFor(() => expect(assignTask).toHaveBeenCalledWith('quizgen', 11))
  })

  test('tasks tab sets a default model per capability', async () => {
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
    screen.getByRole('button', { name: /tasks/i }).click()
    await screen.findByText(/default models/i)
    const textPrimary = screen.getByRole('combobox', { name: 'Default text model' })
    fireEvent.click(textPrimary)
    const option = await screen.findByRole('option', { name: 'gemini-2.5-flash' })
    fireEvent.click(option)
    await waitFor(() => expect(assignTaskDefault).toHaveBeenCalledWith('text', 11, null))
  })

  test('add provider dialog: dropdown preset fills name, type and base URL', async () => {
    listProviders.mockResolvedValue([])
    listPresets.mockResolvedValue(PRESETS)
    createProvider.mockResolvedValue(PROVIDER)
    await await renderSettings()
    fireEvent.click(await screen.findByRole('button', { name: /add provider/i }))
    await screen.findByText('Google Gemini')

    fireEvent.change(await screen.findByLabelText(/^provider$/i), {
      target: { value: 'ollama' },
    })
    expect(screen.getByLabelText(/name/i)).toHaveValue('Ollama (local)')
    fireEvent.change(screen.getByLabelText(/api key/i), {
      target: { value: 'sk-local' },
    })

    screen.getByRole('button', { name: /^add$/i }).click()
    await waitFor(() =>
      expect(createProvider).toHaveBeenCalledWith({
        name: 'Ollama (local)',
        type: 'openai_compatible',
        base_url: 'http://localhost:11434/v1',
        api_key: 'sk-local',
      })
    )
  })

  test('add provider dialog: custom preset keeps a typed name and requires a base URL', async () => {
    listProviders.mockResolvedValue([])
    listPresets.mockResolvedValue(PRESETS)
    createProvider.mockResolvedValue(PROVIDER)
    await await     renderSettings()
    fireEvent.click(await screen.findByRole('button', { name: /add provider/i }))
    await screen.findByText('Google Gemini')

    fireEvent.change(await screen.findByLabelText(/^provider$/i), {
      target: { value: 'custom' },
    })
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: 'LM Studio' } })

    fireEvent.change(await screen.findByLabelText(/^provider$/i), {
      target: { value: 'openai' },
    })
    fireEvent.change(screen.getByLabelText(/^provider$/i), {
      target: { value: 'custom' },
    })
    expect(screen.getByLabelText(/name/i)).toHaveValue('LM Studio')

    const submit = screen.getByRole('button', { name: /^add$/i })
    expect(submit).toBeDisabled()
    expect(screen.getByText(/custom providers need a base url/i)).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/base url/i), {
      target: { value: 'http://localhost:1234/v1' },
    })
    await waitFor(() => expect(submit).toBeEnabled())
    submit.click()
    await waitFor(() =>
      expect(createProvider).toHaveBeenCalledWith({
        name: 'LM Studio',
        type: 'openai_compatible',
        base_url: 'http://localhost:1234/v1',
        api_key: null,
      })
    )
  })

  test('settings tabs are routable via the ?tab= search param', async () => {
    listProviders.mockResolvedValue([PROVIDER])
    listModels.mockResolvedValue([])
    listTasks.mockResolvedValue([])
    listTaskDefaults.mockResolvedValue([])
    await renderSettings('/settings?tab=models')
    expect(await screen.findByRole('button', { name: /add model/i })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /^tasks$/i }))
    await waitFor(() =>
      expect(screen.getByText(/default models/i)).toBeInTheDocument()
    )
  })

  test('developer tab shows the rendering spike content only when selected', async () => {
    await renderSettings()
    expect(screen.queryByText('spike-content')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /^developer$/i }))
    expect(await screen.findByText('spike-content')).toBeInTheDocument()
  })

  test('edit provider dialog patches without touching the key when blank', async () => {
    listProviders.mockResolvedValue([PROVIDER])
    await await renderSettings()
    const edit = await screen.findByRole('button', { name: /edit provider/i })
    edit.click()
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

  test('models tab add-model dialog searches remote list and adds', async () => {
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
    })
    await await renderSettings()
    screen.getByRole('button', { name: /models/i }).click()
    fireEvent.click(await screen.findByRole('button', { name: /add model/i }))

    const search = await screen.findByLabelText(/search models/i)
    expect(await screen.findByText('gemini-2.5-pro')).toBeInTheDocument()
    expect(screen.getByText('text-embedding-004')).toBeInTheDocument()
    expect(screen.getByText('Added')).toBeInTheDocument()

    fireEvent.change(search, { target: { value: 'pro' } })
    expect(screen.queryByText('text-embedding-004')).not.toBeInTheDocument()

    fireEvent.click(screen.getAllByRole('button', { name: /^add$/i })[0])
    await waitFor(() =>
      expect(createModel).toHaveBeenCalledWith(
        expect.objectContaining({
          provider_id: 1,
          external_id: 'gemini-2.5-pro',
          caps: ['text', 'vision', 'tools'],
          enabled: true,
        })
      )
    )
  })

  test('add-model dialog offers manual add when listing fails', async () => {
    listProviders.mockResolvedValue([PROVIDER])
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
    screen.getByRole('button', { name: /models/i }).click()
    fireEvent.click(await screen.findByRole('button', { name: /add model/i }))

    expect(await screen.findByText(/no API key is stored/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /edit provider/i })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /add manually/i }))
    fireEvent.change(await screen.findByLabelText(/model id/i), {
      target: { value: 'gpt-9-turbo' },
    })
    fireEvent.click(screen.getByRole('button', { name: /image \/ vision/i }))
    fireEvent.click(screen.getByRole('button', { name: /^add$/i }))

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
    screen.getByRole('button', { name: /models/i }).click()
    fireEvent.click(await screen.findByRole('button', { name: /delete model/i }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete model' }))
    await waitFor(() => expect(deleteModel).toHaveBeenCalledWith(11))
  })

  test('add-model dialog fuzzy-searches and loads more on scroll', async () => {
    const observers: { callback: IntersectionObserverCallback }[] = []
    class StubObserver {
      callback: IntersectionObserverCallback
      constructor(callback: IntersectionObserverCallback) {
        this.callback = callback
        observers.push(this)
      }
      observe() {}
      unobserve() {}
      disconnect() {}
      takeRecords() {
        return []
      }
    }
    vi.stubGlobal('IntersectionObserver', StubObserver)

    const catalog = Array.from({ length: 75 }, (_, index) => ({
      external_id: `model-${String(index).padStart(2, '0')}`,
      caps: ['text'],
    }))
    try {
      listProviders.mockResolvedValue([PROVIDER])
      listModels.mockResolvedValue([])
      listRemoteModels.mockResolvedValue(catalog)
      await await renderSettings()
      screen.getByRole('button', { name: /models/i }).click()
      fireEvent.click(await screen.findByRole('button', { name: /add model/i }))

      expect(await screen.findByText('model-00')).toBeInTheDocument()
      expect(screen.getByText('model-29')).toBeInTheDocument()
      expect(screen.queryByText('model-30')).not.toBeInTheDocument()
      expect(screen.getByText(/showing 30 of 75/i)).toBeInTheDocument()

      observers[observers.length - 1].callback(
        [{ isIntersecting: true } as IntersectionObserverEntry],
        {} as IntersectionObserver
      )
      expect(await screen.findByText('model-30')).toBeInTheDocument()
      expect(screen.getByText('model-59')).toBeInTheDocument()
      expect(screen.queryByText('model-60')).not.toBeInTheDocument()
      expect(screen.getByText(/showing 60 of 75/i)).toBeInTheDocument()

      observers[observers.length - 1].callback(
        [{ isIntersecting: true } as IntersectionObserverEntry],
        {} as IntersectionObserver
      )
      await waitFor(() =>
        expect(screen.queryByText(/showing \d+ of 75/i)).not.toBeInTheDocument()
      )
      expect(screen.getByText('model-74')).toBeInTheDocument()

      fireEvent.change(screen.getByLabelText(/search models/i), {
        target: { value: 'm7' },
      })
      const matches = await screen.findAllByText(/^model-7\d$/)
      expect(matches.length).toBeGreaterThanOrEqual(5)
      expect(screen.queryByText('model-00')).not.toBeInTheDocument()
    } finally {
      vi.unstubAllGlobals()
    }
  })

  test('add-model dialog bulk-adds the current matches', async () => {
    listProviders.mockResolvedValue([PROVIDER])
    listModels.mockResolvedValue([])
    listRemoteModels.mockResolvedValue([
      { external_id: 'gemini-2.5-flash', caps: ['text', 'vision'] },
      { external_id: 'gemini-2.5-pro', caps: ['text'] },
      { external_id: 'text-embedding-004', caps: ['embeddings'] },
    ])
    createModel.mockResolvedValue({ id: 1 })
    await await renderSettings()
    screen.getByRole('button', { name: /models/i }).click()
    fireEvent.click(await screen.findByRole('button', { name: /add model/i }))
    await screen.findByText('gemini-2.5-flash')

    fireEvent.change(screen.getByLabelText(/search models/i), {
      target: { value: 'gemini' },
    })
    fireEvent.click(screen.getByRole('button', { name: /add all 2/i }))

    await waitFor(() => expect(createModel).toHaveBeenCalledTimes(2))
    expect(createModel).toHaveBeenCalledWith(
      expect.objectContaining({ external_id: 'gemini-2.5-flash', enabled: true })
    )
    expect(createModel).toHaveBeenCalledWith(
      expect.objectContaining({ external_id: 'gemini-2.5-pro', enabled: true })
    )
    expect(createModel).not.toHaveBeenCalledWith(
      expect.objectContaining({ external_id: 'text-embedding-004' })
    )
  })

  test('models tab edit dialog changes caps and label', async () => {
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
    screen.getByRole('button', { name: /models/i }).click()
    fireEvent.click(await screen.findByRole('button', { name: /edit model/i }))

    const labelInput = await screen.findByLabelText(/display name/i)
    fireEvent.change(labelInput, { target: { value: 'Flash' } })
    fireEvent.click(screen.getByRole('button', { name: /image \/ vision/i }))

    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))
    await waitFor(() =>
      expect(updateModel).toHaveBeenCalledWith(11, {
        label: 'Flash',
        caps: ['text', 'tools'],
        enabled: true,
        reasoning_effort: '',
      })
    )
  })
})
