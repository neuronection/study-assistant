import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { PlannerWeekView, weekDays } from './PlannerWeekView'
import type { PlanItem } from '@/lib/api'

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, values?: Record<string, unknown>) =>
        values ? `${key}:${JSON.stringify(values)}` : key,
      i18n: actual.setDefaults,
    }),
  }
})

function makeItem(overrides: Partial<PlanItem>): PlanItem {
  return {
    id: 1,
    course_id: 1,
    node_id: null,
    title: 'task',
    detail: null,
    kind: 'study',
    due_date: '2026-09-16',
    done_at: null,
    origin: 'manual',
    sort_key: 0,
    ...overrides,
  }
}

const TODAY = '2026-09-16'

describe('PlannerWeekView', () => {
  test('weekDays returns the Monday-start week around today', () => {
    expect(weekDays(TODAY)).toEqual([
      '2026-09-14',
      '2026-09-15',
      '2026-09-16',
      '2026-09-17',
      '2026-09-18',
      '2026-09-19',
      '2026-09-20',
    ])
  })

  test('renders seven columns, highlights today, places items by date', () => {
    const { container } = render(
      <PlannerWeekView
        items={[
          makeItem({ id: 1, title: 'midweek task', due_date: '2026-09-16' }),
          makeItem({ id: 2, title: 'friday task', due_date: '2026-09-18' }),
          makeItem({ id: 3, title: 'outside week', due_date: '2026-09-25' }),
        ]}
        todayIso={TODAY}
        onMove={vi.fn()}
        onToggleDone={vi.fn()}
      />
    )
    expect(container.querySelectorAll('[data-testid="week-day"]')).toHaveLength(7)
    const today = container.querySelector(
      '[data-day="2026-09-16"]'
    ) as HTMLElement | null
    expect(today).not.toBeNull()
    expect(today!.className).toContain('border-primary')
    expect(today!.textContent).toContain('midweek task')
    expect(today!.textContent).not.toContain('outside week')
    expect(today!.textContent).toContain('planner.weekday_wed')
  })

  test('overdue items get the warning border, done items strike through', () => {
    render(
      <PlannerWeekView
        items={[
          makeItem({ id: 1, title: 'late task', due_date: '2026-09-15' }),
          makeItem({
            id: 2,
            title: 'finished',
            due_date: '2026-09-16',
            done_at: '2026-09-16T10:00:00Z',
          }),
        ]}
        todayIso={TODAY}
        onMove={vi.fn()}
        onToggleDone={vi.fn()}
      />
    )
    const late = screen.getByText('late task').closest('div[class*="border"]')
    expect(late?.className).toContain('border-l-warning')
    const doneTitle = screen.getByText('finished')
    expect(doneTitle.className).toContain('line-through')
  })

  test('dropping an item on another day reschedules it', () => {
    const onMove = vi.fn()
    const { container } = render(
      <PlannerWeekView
        items={[makeItem({ id: 9, title: 'movable', due_date: '2026-09-16' })]}
        todayIso={TODAY}
        onMove={onMove}
        onToggleDone={vi.fn()}
      />
    )
    const friday = container.querySelector(
      '[data-day="2026-09-18"]'
    ) as HTMLElement | null
    expect(friday).not.toBeNull()
    fireEvent.dragOver(friday!)
    fireEvent.drop(friday!, {
      dataTransfer: { getData: () => '9' },
    })
    expect(onMove).toHaveBeenCalledTimes(1)
    expect(onMove).toHaveBeenCalledWith(expect.objectContaining({ id: 9 }), '2026-09-18')
  })
})
