import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { OnboardingWizard } from './OnboardingWizard'
import { useWizardStore } from './wizardStore'

const getOnboardingState = vi.fn()
const getWorkingDir = vi.fn()
const listPresets = vi.fn()
const createProvider = vi.fn()
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
    getWorkingDir: () => getWorkingDir(),
    listPresets: () => listPresets(),
    createProvider: (body: unknown) => createProvider(body),
    listModels: () => listModels(),
    updateModel: (id: number, body: unknown) => updateModel(id, body),
    listTaskDefaults: () => listTaskDefaults(),
    assignTaskDefault: (requires: string, modelId: number | null) =>
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
  id: 7,
  provider_id: 1,
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
    getWorkingDir.mockResolvedValue(WORKING_DIR)
    listPresets.mockResolvedValue({
      google: { name: 'Google', type: 'google', base_url: '' },
    })
    listModels.mockResolvedValue([MODEL])
    listTaskDefaults.mockResolvedValue([])
    listCourses.mockResolvedValue([])
    navigate.mockReset()
  })

  afterEach(() => {
    window.localStorage.clear()
  })

  test('auto-opens on a fresh install', async () => {
    renderWizard()
    expect(await screen.findByText('Welcome to Study Assistant')).toBeInTheDocument()
  })

  test('does not auto-open when a provider already exists', async () => {
    getOnboardingState.mockResolvedValue(PROVIDER_STATE)
    renderWizard()
    await waitFor(() => expect(getOnboardingState).toHaveBeenCalled())
    expect(screen.queryByText('Welcome to Study Assistant')).not.toBeInTheDocument()
  })

  test('does not auto-open when previously dismissed', async () => {
    window.localStorage.setItem('ca-onboarding-done', '1')
    renderWizard()
    await waitFor(() => expect(getOnboardingState).toHaveBeenCalled())
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  test('skip persists the dismissal and closes', async () => {
    renderWizard()
    fireEvent.click(await screen.findByRole('button', { name: 'Skip for now' }))
    await waitFor(() =>
      expect(window.localStorage.getItem('ca-onboarding-done')).toBe('1')
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

  test('provider creation advances to the models step', async () => {
    createProvider.mockResolvedValue({ id: 3, name: 'Google' })
    renderWizard()
    fireEvent.click(await screen.findByRole('button', { name: 'Get started' }))
    expect(await screen.findByText('Where should your data live?')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    fireEvent.change(await screen.findByLabelText('Name', { selector: 'input' }), {
      target: { value: 'Google' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add provider' }))
    await waitFor(() => expect(createProvider).toHaveBeenCalled())
    expect(await screen.findByText('Choose your models')).toBeInTheDocument()
  })

  test('full flow: course creation wires the files step and the done summary', async () => {
    createCourse.mockResolvedValue({ id: 12, title: 'Calculus I' })
    listCourses.mockResolvedValue([{ id: 12, title: 'Calculus I' }])
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
      expect(window.localStorage.getItem('ca-onboarding-done')).toBe('1')
    )
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
