import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { TasksTab } from './TasksTab'

const listProviders = vi.fn()
const listModels = vi.fn()
const listTasks = vi.fn()
const listTaskDefaults = vi.fn()
const getCosts = vi.fn()
const assignTask = vi.fn()
const assignTaskDefault = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listProviders: () => listProviders(),
    listModels: () => listModels(),
    listTasks: () => listTasks(),
    listTaskDefaults: () => listTaskDefaults(),
    getCosts: () => getCosts(),
    assignTask: (task: string, modelId: number | null) => assignTask(task, modelId),
    assignTaskDefault: (requires: string, modelId: number | null, fallback: number | null) =>
      assignTaskDefault(requires, modelId, fallback),
  }
})

const PROVIDERS = [
  {
    id: 1,
    name: 'TypeSafe',
    type: 'decision',
    base_url: 'https://api.typesafe.ai',
    preset_key: 'typesafe',
    enabled: true,
    is_local: false,
    country: null,
    masked_key: null,
    status: null,
    created_at: '',
  },
]

const MODELS = [
  {
    id: 10,
    provider_id: 1,
    external_id: 'jev-latest',
    label: 'Jev (latest)',
    caps: ['decision'],
    decision_transport: 'systemone',
    enabled: true,
    missing: false,
    reasoning_effort: null,
  },
]

const TASKS = [
  {
    task: 'chat',
    description: 'Course chat',
    requires: 'text',
    model_id: null,
    fallback_model_id: null,
    model_label: null,
    fallback_model_label: null,
    inherits_default: false,
    default_model_label: null,
    default_fallback_model_label: null,
    monthly_cap_usd: null,
  },
]

const DEFAULTS = [
  { requires: 'text', model_id: null, fallback_model_id: null, model_label: null, fallback_model_label: null },
  { requires: 'vision', model_id: null, fallback_model_id: null, model_label: null, fallback_model_label: null },
  { requires: 'embeddings', model_id: null, fallback_model_id: null, model_label: null, fallback_model_label: null },
  { requires: 'stt', model_id: null, fallback_model_id: null, model_label: null, fallback_model_label: null },
  { requires: 'tts', model_id: null, fallback_model_id: null, model_label: null, fallback_model_label: null },
  { requires: 'decision:tool-dispatch', model_id: 10, fallback_model_id: null, model_label: 'Jev (latest)', fallback_model_label: null },
  { requires: 'decision:boolean-gate', model_id: null, fallback_model_id: null, model_label: null, fallback_model_label: null },
  { requires: 'decision:choice', model_id: null, fallback_model_id: null, model_label: null, fallback_model_label: null },
  { requires: 'decision:score', model_id: null, fallback_model_id: null, model_label: null, fallback_model_label: null },
]

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <TasksTab />
    </QueryClientProvider>
  )
}

beforeEach(() => {
  listProviders.mockReset().mockResolvedValue(PROVIDERS)
  listModels.mockReset().mockResolvedValue(MODELS)
  listTasks.mockReset().mockResolvedValue(TASKS)
  listTaskDefaults.mockReset().mockResolvedValue(DEFAULTS)
  getCosts.mockReset().mockResolvedValue({ month: '2026-10', total_usd: 0, per_task: [] })
  assignTask.mockReset().mockResolvedValue({})
  assignTaskDefault.mockReset().mockResolvedValue({})
})

describe('TasksTab decision group (plan 26 Phase 3)', () => {
  test('renders the Decision models group with the four family slots and the privacy notice', async () => {
    renderTab()

    expect(await screen.findByText('Decision models')).toBeInTheDocument()
    expect(
      screen.getByText(/decision models run in the cloud/i)
    ).toBeInTheDocument()
    expect(screen.getByText('Tool dispatch')).toBeInTheDocument()
    expect(screen.getByText('Boolean gate')).toBeInTheDocument()
    expect(screen.getByText('Choice')).toBeInTheDocument()
    expect(screen.getByText('Score')).toBeInTheDocument()
  })

  test('decision pickers offer only decision-declaring models (D2b/D4)', async () => {
    renderTab()
    await screen.findByText('Tool dispatch')

    const dispatchPicker = screen.getAllByRole('combobox', { name: /tool dispatch/i })[0]
    fireEvent.click(dispatchPicker)
    const jevOption = await screen.findByRole('option', { name: /jev \(latest\)/i })
    const listbox = jevOption.closest('[role="listbox"]')
    expect(listbox).not.toBeNull()
    const names = Array.from(listbox!.querySelectorAll('[role="option"]')).map(
      (option) => option.textContent
    )
    expect(names).toEqual(['Jev (latest)'])
  })

  test('assigning a decision slot posts the decision:<cap> requires key', async () => {
    renderTab()
    await screen.findByText('Tool dispatch')

    fireEvent.click(screen.getByRole('combobox', { name: 'Boolean gate' }))
    fireEvent.click(await screen.findByRole('option', { name: /jev \(latest\)/i }))

    await waitFor(() =>
      expect(assignTaskDefault).toHaveBeenCalledWith('decision:boolean-gate', 10, null)
    )
    expect(assignTask).not.toHaveBeenCalled()
  })

  test('the decision fallback picker posts the fallback model', async () => {
    renderTab()
    await screen.findByText('Tool dispatch')

    fireEvent.click(screen.getByRole('combobox', { name: 'Fallback — Boolean gate' }))
    fireEvent.click(await screen.findByRole('option', { name: /jev \(latest\)/i }))

    await waitFor(() => {
      expect(assignTaskDefault).toHaveBeenCalled()
      const [requires, modelId, fallbackId] = assignTaskDefault.mock.calls[0]
      expect(requires).toBe('decision:boolean-gate')
      expect(modelId).toBe(null)
      expect(fallbackId).toBe(10)
    })
  })
})
