import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import i18next from 'i18next'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { OnboardingWizard } from './OnboardingWizard'
import { useWizardStore } from './wizardStore'
import { storageKeys } from '@/lib/constants'

const getOnboardingState = vi.fn()
const getInstanceConfig = vi.fn()
const getWorkingDir = vi.fn()
const listPresets = vi.fn()
const listProviders = vi.fn()
const setupProviderPreset = vi.fn()
const createProvider = vi.fn()
const detectLocalEngines = vi.fn()
const listModels = vi.fn()
const updateModel = vi.fn()
const listTaskDefaults = vi.fn()
const assignTaskDefault = vi.fn()
const createCourse = vi.fn()
const createSampleCourse = vi.fn()
const listCourses = vi.fn()
const navigate = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getOnboardingState: () => getOnboardingState(),
    getInstanceConfig: () => getInstanceConfig(),
    getWorkingDir: () => getWorkingDir(),
    listPresets: () => listPresets(),
    listProviders: () => listProviders(),
    setupProviderPreset: (key: string, body: unknown) => setupProviderPreset(key, body),
    createProvider: (body: unknown) => createProvider(body),
    detectLocalEngines: () => detectLocalEngines(),
    listModels: () => listModels(),
    updateModel: (id: string, body: unknown) => updateModel(id, body),
    listTaskDefaults: () => listTaskDefaults(),
    assignTaskDefault: (requires: string, modelId: string | null) =>
      assignTaskDefault(requires, modelId),
    createCourse: (body: unknown) => createCourse(body),
    createSampleCourse: () => createSampleCourse(),
    listCourses: () => listCourses(),
  }
})

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigate,
  Link: ({ children }: { children: React.ReactNode }) => <a href="#">{children}</a>,
}))

const FRESH_STATE = {
  has_provider: false,
  has_enabled_model: false,
  defaults_set: [],
  has_course: false,
  has_material: false,
}

const WORKING_DIR = {
  path: '/data',
  default_path: '/data',
  custom: false,
  restart_pending: false,
}

const PROVIDER_STATE = { ...FRESH_STATE, has_provider: true }

const MODEL = {
  id: '7',
  provider_id: '1',
  external_id: 'gemini-2.5-flash',
  label: 'gemini-2.5-flash',
  caps: ['text', 'vision'],
  enabled: false,
  missing: false,
  reasoning_effort: null,
}

function renderWizard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <OnboardingWizard />
    </QueryClientProvider>
  )
}

describe('OnboardingWizard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
    useWizardStore.setState({ open: false })
    getOnboardingState.mockResolvedValue(FRESH_STATE)
    getInstanceConfig.mockResolvedValue({ identity_mode: 'desktop' })
    getWorkingDir.mockResolvedValue(WORKING_DIR)
    listPresets.mockResolvedValue({
      gemini: {
        name: 'Google',
        type: 'google',
        base_url: 'https://generativelanguage.googleapis.com',
        fixed_base: true,
        local: false,
        key_url: null,
        preferred_model: null,
        curated_models: null,
        stt_model: null,
        steps: null,
        free_tier_note: null,
      },
    })
    listProviders.mockResolvedValue([])
    setupProviderPreset.mockResolvedValue({
      ok: true,
      provider: { id: '3', name: 'Google', type: 'google', base_url: '' },
      catalog_count: 1,
      curated_missed: false,
    })
    detectLocalEngines.mockResolvedValue([])
    listModels.mockResolvedValue([MODEL])
    listTaskDefaults.mockResolvedValue([])
    listCourses.mockResolvedValue([])
    navigate.mockReset()
  })

  afterEach(async () => {
    window.localStorage.clear()
    await i18next.changeLanguage('en')
  })

  test('auto-opens on a fresh install', async () => {
    renderWizard()
    expect(await screen.findByText('Welcome to Study Assistant')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Welcome' })).toBeInTheDocument()
  })

  test('desktop identity exposes the working-directory step', async () => {
    renderWizard()
    fireEvent.click(await screen.findByRole('button', { name: 'Get started' }))
    expect(await screen.findByText('Where should your data live?')).toBeInTheDocument()
  })

  test('server identity omits the working-directory step and local-first copy', async () => {
    getInstanceConfig.mockResolvedValue({ identity_mode: 'server' })
    renderWizard()
    expect(await screen.findByText('Welcome to Study Assistant')).toBeInTheDocument()
    expect(
      screen.getByText(/This wizard connects an AI provider/i)
    ).toBeInTheDocument()
    expect(screen.queryByText(/everything stays on this machine/i)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Get started' }))
    expect(screen.queryByText('Where should your data live?')).not.toBeInTheDocument()
  })

  test('welcome step offers a language picker that applies instantly', async () => {
    renderWizard()
    expect(await screen.findByText('Welcome to Study Assistant')).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Language' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('combobox', { name: 'Language' }))
    const greek = await screen.findByRole('option', { name: /Ελληνικά/ })
    expect(greek.textContent).toContain('🇬🇷')
    fireEvent.click(greek)

    await waitFor(() => {
      expect(document.documentElement.lang).toBe('el')
    })
    expect(localStorage.getItem(storageKeys.locale)).toBe('el')
    expect(screen.getByRole('combobox', { name: 'Γλώσσα' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Καλώς ήρθατε' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Παράλειψη προς το παρόν' })).toBeInTheDocument()
  })

  test('does not auto-open when a provider already exists', async () => {
    getOnboardingState.mockResolvedValue(PROVIDER_STATE)
    renderWizard()
    await waitFor(() => expect(getOnboardingState).toHaveBeenCalled())
    expect(screen.queryByText('Welcome to Study Assistant')).not.toBeInTheDocument()
  })

  test('does not auto-open when previously dismissed', async () => {
    window.localStorage.setItem(storageKeys.onboardingDone, '1')
    renderWizard()
    await waitFor(() => expect(getOnboardingState).toHaveBeenCalled())
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  test('skip persists the dismissal and closes', async () => {
    renderWizard()
    fireEvent.click(await screen.findByRole('button', { name: 'Skip for now' }))
    await waitFor(() =>
      expect(window.localStorage.getItem(storageKeys.onboardingDone)).toBe('1')
    )
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  test('manual open works even when not fresh', async () => {
    getOnboardingState.mockResolvedValue(PROVIDER_STATE)
    renderWizard()
    await waitFor(() => expect(getOnboardingState).toHaveBeenCalled())
    act(() => useWizardStore.getState().openWizard())
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  test('provider step offers a detected local engine with one-click add', async () => {
    detectLocalEngines.mockResolvedValue([
      {
        preset_id: 'ollama',
        name: 'Ollama (local)',
        base_url: 'http://localhost:11434/v1',
        models: ['qwen3:8b', 'nomic-embed-text'],
      },
    ])
    createProvider.mockResolvedValue({ id: '9', name: 'Ollama (local)' })
    renderWizard()
    fireEvent.click(await screen.findByRole('button', { name: 'Get started' }))
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Local engines' }))
    expect(await screen.findByText('Ollama (local)')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /add ollama \(local\)/i }))
    await waitFor(() =>
      expect(createProvider).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Ollama (local)',
          base_url: 'http://localhost:11434/v1',
          is_local: true,
        })
      )
    )
    expect(await screen.findByText('Choose your models')).toBeInTheDocument()
  })

  test('provider creation advances to the models step', async () => {
    renderWizard()
    fireEvent.click(await screen.findByRole('button', { name: 'Get started' }))
    expect(await screen.findByText('Where should your data live?')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    fireEvent.click(await screen.findByRole('button', { name: /Google/ }))
    expect(screen.queryByLabelText('Connection name')).not.toBeInTheDocument()
    expect(screen.queryByText('Hosting')).not.toBeInTheDocument()
    expect(screen.queryByText('Country')).not.toBeInTheDocument()
    fireEvent.change(await screen.findByLabelText('API key'), {
      target: { value: 'sk-test' },
    })
    fireEvent.click(screen.getByRole('button', { name: /set up automatically/i }))
    await waitFor(() => expect(setupProviderPreset).toHaveBeenCalled())
    expect(setupProviderPreset).toHaveBeenCalledWith(
      'gemini',
      expect.objectContaining({
        options: expect.objectContaining({
          bind_chat: true,
          bind_vision: true,
          bind_stt: true,
          bind_embeddings: true,
        }),
      })
    )
    expect(await screen.findByText('Choose your models')).toBeInTheDocument()
  })

  test('full flow: course creation wires the files step and the done summary', async () => {
    createCourse.mockResolvedValue({ id: '12', title: 'Calculus I' })
    listCourses.mockResolvedValue([{ id: '12', title: 'Calculus I' }])
    getOnboardingState.mockResolvedValue({
      has_provider: true,
      has_enabled_model: true,
      defaults_set: ['text'],
      has_course: true,
      has_material: true,
    })
    renderWizard()
    await waitFor(() => expect(getOnboardingState).toHaveBeenCalled())
    act(() => useWizardStore.getState().openWizard())
    fireEvent.click(await screen.findByRole('button', { name: 'Get started' }))
    expect(await screen.findByText('Where should your data live?')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(await screen.findByText('Connect an AI provider')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(await screen.findByText('Choose your models')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(await screen.findByText('Pick default models')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))

    expect(await screen.findByText('Create your first course')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Course name'), {
      target: { value: 'Calculus I' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create course' }))
    expect(await screen.findByText(/"Calculus I" is ready/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(await screen.findByText('Add your first materials')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(await screen.findByText("You're all set")).toBeInTheDocument()
    expect(screen.getByText('AI provider')).toBeInTheDocument()
    const setUpRows = screen.getAllByText('set up')
    expect(setUpRows).toHaveLength(5)
    expect(setUpRows[0].className).toContain('text-success')

    fireEvent.click(screen.getByRole('button', { name: 'Go to Today' }))
    await waitFor(() =>
      expect(window.localStorage.getItem(storageKeys.onboardingDone)).toBe('1')
    )
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
