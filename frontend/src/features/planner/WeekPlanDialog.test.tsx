import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { WeekPlanDialog } from './WeekPlanDialog'
import type { PlannerCapacity, WeekPlanPreview } from '@/lib/api'

const preview = vi.hoisted(() => vi.fn())
const capacity = vi.hoisted(() => vi.fn())
const commit = vi.hoisted(() => vi.fn())
const saveCapacity = vi.hoisted(() => vi.fn())

vi.mock('@/lib/api', () => ({
  previewWeekPlan: preview,
  getPlannerCapacity: capacity,
  commitWeekPlan: commit,
  updatePlannerCapacity: saveCapacity,
}))

const PREVIEW: WeekPlanPreview = {
  start: '2026-11-11',
  end: '2026-11-17',
  capacity_minutes: [60, 60, 60, 60, 60, 60, 60],
  light_week: false,
  days: [
    {
      day: '2026-11-11',
      minutes: 40,
      items: [
        {
          day: '2026-11-11',
          course_id: 'c1',
          course_title: 'Calculus',
          kind: 'review',
          title: 'Review 12 due cards',
          detail: '12 cards due',
          minutes: 15,
          evidence: '12 due cards',
          fixed: false,
        },
        {
          day: '2026-11-11',
          course_id: 'c1',
          course_title: 'Calculus',
          kind: 'study',
          title: 'Study Limits',
          detail: null,
          minutes: 25,
          evidence: 'not studied yet',
          fixed: false,
        },
      ],
    },
  ],
  overflow: 2,
  existing_generated: 0,
  total_minutes: 40,
}

const CAPACITY: PlannerCapacity = {
  minutes: [60, 60, 60, 60, 60, 60, 60],
  blackout_dates: [],
  light_week: false,
}

function renderDialog() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <WeekPlanDialog onClose={vi.fn()} />
    </QueryClientProvider>,
  )
}

describe('WeekPlanDialog', () => {
  beforeEach(() => {
    preview.mockReset().mockResolvedValue(PREVIEW)
    capacity.mockReset().mockResolvedValue(CAPACITY)
    commit.mockReset().mockResolvedValue({ created: 2, replaced: 0 })
    saveCapacity.mockReset().mockResolvedValue(CAPACITY)
  })

  test('shows the draft, overflow warning and commits', async () => {
    renderDialog()
    expect(await screen.findByText('Review 12 due cards')).toBeInTheDocument()
    expect(screen.getByText(/2 blocks did not fit/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Add to plan/ }))
    await waitFor(() => expect(commit).toHaveBeenCalled())
    expect(await screen.findByText(/2 blocks added/)).toBeInTheDocument()
  })

  test('opens capacity editing and saves', async () => {
    renderDialog()
    await screen.findByText('Review 12 due cards')
    fireEvent.click(screen.getByRole('button', { name: 'Capacity' }))
    const input = screen.getByLabelText('Day 1 minutes')
    fireEvent.change(input, { target: { value: '90' } })
    fireEvent.click(screen.getByRole('button', { name: /Save capacity/ }))
    await waitFor(() =>
      expect(saveCapacity).toHaveBeenCalledWith(
        expect.objectContaining({ minutes: [90, 60, 60, 60, 60, 60, 60] })
      )
    )
  })
})
