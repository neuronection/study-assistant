import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { TasksTab } from './TasksTab'

const listProviders = vi.fn()
const listModels = vi.fn()
const listTasks = vi.fn()
const listTaskDefaults = vi.fn()
const listPresets = vi.fn()
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
    listPresets: () => listPresets(),
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
    monthly_cap_usd: null,
  },
]

const DECISION_KINDS = [
  'decision:tool-dispatch',
  'decision:boolean-gate',
  'decision:choice',
  'decision:score',
] as const

interface DefaultRow {
  requires: string
  model_id: number | null
  fallback_model_id: number | null
  model_label: string | null
  fallback_model_label: string | null
  resolved_inherit_label?: string | null
}

function defaultsFixture(options: {
  defaultModelId?: number | null
  kindModelId?: number | null
  resolvedInheritLabel?: string | null
} = {}) {
  const { defaultModelId = null, kindModelId = null, resolvedInheritLabel = null } = options
  const rows: DefaultRow[] = [
    { requires: 'text', model_id: null, fallback_model_id: null, model_label: null, fallback_model_label: null },
    { requires: 'vision', model_id: null, fallback_model_id: null, model_label: null, fallback_model_label: null },
    { requires: 'embeddings', model_id: null, fallback_model_id: null, model_label: null, fallback_model_label: null },
    { requires: 'stt', model_id: null, fallback_model_id: null, model_label: null, fallback_model_label: null },
    { requires: 'tts', model_id: null, fallback_model_id: null, model_label: null, fallback_model_label: null },
    {
      requires: 'decision',
      model_id: defaultModelId,
      fallback_model_id: null,
      model_label: defaultModelId != null ? 'Jev (latest)' : null,
      fallback_model_label: null,
    },
  ]
  for (const slot of DECISION_KINDS) {
    rows.push({
      requires: slot,
      model_id: kindModelId,
      fallback_model_id: null,
      model_label: kindModelId != null ? 'Jev (latest)' : null,
      fallback_model_label: null,
      resolved_inherit_label: resolvedInheritLabel,
    })
  }
  return rows
}

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
  listTaskDefaults.mockReset().mockResolvedValue(defaultsFixture())
  listPresets.mockReset().mockResolvedValue({})
  getCosts.mockReset().mockResolvedValue({ month: '2026-10', total_usd: 0, per_task: [] })
  assignTask.mockReset().mockResolvedValue({})
  assignTaskDefault.mockReset().mockResolvedValue({})
})

describe('TasksTab Decision defaults (plan 29 / ADR-0036, uniform section ruling)', () => {
  test('the decision default rides the Default models section; the four kinds form the Decision kinds group with the privacy notice', async () => {
    renderTab()

    expect(await screen.findByText('Default models')).toBeInTheDocument()
    expect(screen.getByText('Default decision model')).toBeInTheDocument()
    expect(screen.getByText('Decision kinds')).toBeInTheDocument()
    expect(screen.getByText(/decision models run in the cloud/i)).toBeInTheDocument()
    expect(screen.getByText('Tool dispatch')).toBeInTheDocument()
    expect(screen.getByText('Boolean gate')).toBeInTheDocument()
    expect(screen.getByText('Choice')).toBeInTheDocument()
    expect(screen.getByText('Score')).toBeInTheDocument()
    // No legacy card title.
    expect(screen.queryByText('Decision defaults')).not.toBeInTheDocument()
    expect(screen.queryByText('Decision models')).not.toBeInTheDocument()
  })

  test('an empty default shows the D4 hint line and the canonical preset suggestion', async () => {
    listPresets.mockResolvedValue({
      typesafe: { name: 'TypeSafe', decision_default: 'typesafe/jev-1.13' },
    })
    renderTab()

    expect(
      await screen.findByText(/assign one decision model to power all four/i)
    ).toBeInTheDocument()
    // The suggestion rides the same hint line once the presets query lands.
    expect(await screen.findByText(/suggested: typesafe\/jev-1\.13/i)).toBeInTheDocument()
  })

  test('decision pickers offer only decision-declaring models — no explicit inherit entry; the empty trigger reads the short state word (D2b/D4)', async () => {
    renderTab()
    await screen.findByText('Tool dispatch')

    // The unset kind picker's trigger reads the short muted state word —
    // honestly bare "Inherited" while the default is empty, and no
    // defaults-to meta line when nothing resolves.
    const toolDispatch = screen.getByRole('combobox', { name: 'Tool dispatch' })
    expect(toolDispatch).toHaveTextContent('Inherited')
    expect(screen.queryByText(/defaults to/i)).not.toBeInTheDocument()

    fireEvent.click(toolDispatch)
    const jevOption = await screen.findByRole('option', { name: /^Jev \(latest\)$/ })
    const listbox = jevOption.closest('[role="listbox"]')
    expect(listbox).not.toBeNull()
    const names = Array.from(listbox!.querySelectorAll('[role="option"]')).map(
      (option) => option.textContent
    )
    // No labeled inherit entry: an unset kind simply *is* the inherit
    // state (the backend resolves the default).
    expect(names).toEqual(['Jev (latest)'])
  })

  test('the resolved default moves to a "Defaults to" meta line; the trigger keeps the short state word (matrix 7)', async () => {
    listTaskDefaults.mockResolvedValue(
      defaultsFixture({ defaultModelId: 10, resolvedInheritLabel: 'Jev (latest)' })
    )
    renderTab()
    const booleanGate = await screen.findByRole('combobox', { name: 'Boolean gate' })

    // Empty kind = inherit: the trigger reads the short muted state word
    // and the resolution detail rides the meta line under the description
    // (the label arrives with the defaults query — wait for it). All four
    // unset kinds resolve to the same default here.
    await waitFor(() =>
      expect(screen.getAllByText('Defaults to Jev (latest)')).toHaveLength(4)
    )
    expect(booleanGate).toHaveTextContent('Inherited')

    fireEvent.click(booleanGate)
    const jevOption = await screen.findByRole('option', { name: /^Jev \(latest\)$/ })
    const listbox = jevOption.closest('[role="listbox"]')
    const names = Array.from(listbox!.querySelectorAll('[role="option"]')).map(
      (option) => option.textContent
    )
    expect(names).toEqual(['Jev (latest)'])
  })

  test('assigning a decision kind posts the decision:<cap> override (matrix 2)', async () => {
    renderTab()
    await screen.findByText('Tool dispatch')

    fireEvent.click(screen.getByRole('combobox', { name: 'Boolean gate' }))
    fireEvent.click(await screen.findByRole('option', { name: /jev \(latest\)/i }))

    await waitFor(() =>
      expect(assignTaskDefault).toHaveBeenCalledWith('decision:boolean-gate', 10, null)
    )
    expect(assignTask).not.toHaveBeenCalled()
  })

  test('the default decision row posts the decision requires key', async () => {
    renderTab()
    await screen.findByText('Default decision model')

    fireEvent.click(screen.getByRole('combobox', { name: 'Default decision model' }))
    fireEvent.click(await screen.findByRole('option', { name: /jev \(latest\)/i }))

    await waitFor(() =>
      expect(assignTaskDefault).toHaveBeenCalledWith('decision', 10, null)
    )
  })

  test('the X clear on a kind row assigns null — the inherit state (D3)', async () => {
    listTaskDefaults.mockResolvedValue(
      defaultsFixture({ defaultModelId: 10, kindModelId: 10, resolvedInheritLabel: 'Jev (latest)' })
    )
    renderTab()
    await screen.findByText('Tool dispatch')

    // An overridden kind shows its model in the trigger — no defaults-to
    // meta line for it.
    const booleanGate = screen.getByRole('combobox', { name: 'Boolean gate' })
    await waitFor(() => expect(booleanGate).toHaveTextContent('Jev (latest)'))
    expect(screen.queryByText(/defaults to/i)).not.toBeInTheDocument()

    fireEvent.click(
      await screen.findByRole('button', { name: 'Clear assignment — Boolean gate' })
    )

    await waitFor(() =>
      expect(assignTaskDefault).toHaveBeenCalledWith('decision:boolean-gate', null, null)
    )
  })

  test('"Simplify" appears when 4/4 kinds resolve to one model and the default is empty (matrix 6)', async () => {
    listTaskDefaults.mockResolvedValue(defaultsFixture({ kindModelId: 10 }))
    renderTab()

    expect(
      await screen.findByRole('button', { name: /simplify: use jev \(latest\) as default/i })
    ).toBeInTheDocument()
  })

  test('no "Simplify" when the default is already set (matrix 6)', async () => {
    listTaskDefaults.mockResolvedValue(
      defaultsFixture({ defaultModelId: 10, kindModelId: 10 })
    )
    renderTab()

    const defaultPicker = await screen.findByRole('combobox', {
      name: 'Default decision model',
    })
    await waitFor(() => expect(defaultPicker).toHaveTextContent('Jev (latest)'))
    expect(screen.queryByRole('button', { name: /simplify/i })).not.toBeInTheDocument()
  })

  test('no "Simplify" when only some kinds are assigned (matrix 6)', async () => {
    const partial = defaultsFixture()
    for (const [index, slot] of DECISION_KINDS.entries()) {
      const row = partial.find((entry) => entry.requires === slot)!
      row.model_id = index === 0 ? 10 : null
    }
    listTaskDefaults.mockResolvedValue(partial)
    renderTab()

    await screen.findByRole('button', { name: 'Clear assignment — Tool dispatch' })
    expect(
      screen.queryByRole('button', { name: 'Clear assignment — Boolean gate' })
    ).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /simplify/i })).not.toBeInTheDocument()
  })

  test('the Simplify chip posts the decision default (one click, never automatic)', async () => {
    listTaskDefaults.mockResolvedValue(defaultsFixture({ kindModelId: 10 }))
    renderTab()

    fireEvent.click(
      await screen.findByRole('button', { name: /simplify: use jev \(latest\) as default/i })
    )

    await waitFor(() =>
      expect(assignTaskDefault).toHaveBeenCalledWith('decision', 10, null)
    )
  })
})
