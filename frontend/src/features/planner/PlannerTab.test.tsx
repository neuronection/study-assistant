import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { PlannerTab } from './PlannerTab'

const listPlanItems = vi.fn()
const createPlanItem = vi.fn()
const updatePlanItem = vi.fn()
const deletePlanItem = vi.fn()
const generatePlan = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listPlanItems: (id: number) => listPlanItems(id),
    createPlanItem: (id: number, body: unknown) => createPlanItem(id, body),
    updatePlanItem: (id: number, itemId: number, body: unknown) =>
      updatePlanItem(id, itemId, body),
    deletePlanItem: (id: number, itemId: number) => deletePlanItem(id, itemId),
    generatePlan: (id: number) => generatePlan(id),
  }
})

function todayPlus(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}

function makeItem(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: 1,
    course_id: 5,
    node_id: null,
    title: 'Study: Limits',
    detail: null,
    kind: 'study',
    due_date: todayPlus(0),
    done_at: null,
    origin: 'draft',
    sort_key: 0,
    ...overrides,
  }
}

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <PlannerTab courseId="5" />
    </QueryClientProvider>
  )
}

describe('PlannerTab', () => {
  test('groups open items under day headings and shows drafts with keep/discard', async () => {
    listPlanItems.mockResolvedValue([
      makeItem({ id: 1, origin: 'draft' }),
      makeItem({ id: 2, title: 'manual item', origin: 'manual' }),
    ])
    renderTab()

    expect(await screen.findByText('Study: Limits')).toBeInTheDocument()
    expect(screen.getByText('manual item')).toBeInTheDocument()
    expect(screen.getAllByTestId('plan-day').length).toBe(1)
    const keepButtons = screen.getAllByRole('button', { name: 'Keep' })
    expect(keepButtons.length).toBe(1)

    fireEvent.click(keepButtons[0])
    await waitFor(() =>
      expect(updatePlanItem).toHaveBeenCalledWith(5, 1, {
        title: 'Study: Limits',
        due_date: todayPlus(0),
        kind: 'study',
      })
    )
  })

  test('check-off marks the item done and it moves to the done section', async () => {
    listPlanItems.mockResolvedValue([makeItem({ id: 3, origin: 'manual' })])
    updatePlanItem.mockResolvedValue({})
    renderTab()

    fireEvent.click(await screen.findByRole('button', { name: 'Mark done' }))
    await waitFor(() => expect(updatePlanItem).toHaveBeenCalledWith(5, 3, { done: true }))
  })

  test('generate calls the deterministic drafting endpoint', async () => {
    listPlanItems.mockResolvedValue([])
    generatePlan.mockResolvedValue({ created: 0, items: [] })
    renderTab()

    fireEvent.click(await screen.findByRole('button', { name: /generate plan/i }))
    await waitFor(() => expect(generatePlan).toHaveBeenCalledWith(5))
    expect(screen.getByText(/nothing planned yet/i)).toBeInTheDocument()
  })
})
