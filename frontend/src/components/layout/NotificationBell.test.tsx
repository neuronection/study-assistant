import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { actionableTotal, NotificationBell } from './NotificationBell'
import type { Notifications } from '@/lib/api'
import { storageKeys } from '@/lib/constants'

const getNotifications = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getNotifications: () => getNotifications(),
  }
})

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => vi.fn(),
  Link: ({ children }: { children: React.ReactNode }) => <a href="#">{children}</a>,
}))

function renderBell() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = render(
    <QueryClientProvider client={client}>
      <NotificationBell />
    </QueryClientProvider>
  )
  return { client, view }
}

const AGGREGATE: Notifications = {
  due_cards: 3,
  due_reviews: [
    { card_id: 1, kind: 'card_basic', course_id: 1, course_title: 'Calculus' },
  ],
  plan_today: [
    {
      item_id: 7,
      title: 'overdue task',
      kind: 'study',
      course_id: 1,
      course_title: 'Calculus',
      due_date: '2026-09-14',
      overdue: true,
    },
  ],
  plan_overdue_count: 1,
  exams: [
    {
      course_id: 1,
      course_title: 'Calculus',
      exam_date: '2026-09-20',
      days_left: 5,
    },
  ],
  pending_proposals: 0,
  generated_at: '2026-09-15T00:00:00Z',
}

describe('NotificationBell', () => {
  beforeEach(() => {
    getNotifications.mockReset()
    getNotifications.mockResolvedValue(AGGREGATE)
    try {
      window.localStorage.clear()
    } catch {
      return
    }
  })

  test('renders grouped sections from the aggregate', async () => {
    renderBell()
    const trigger = await screen.findByRole('button', { name: /notifications/i })
    fireEvent.click(trigger)
    expect(await screen.findByText('Due now')).toBeInTheDocument()
    expect(screen.getByText('3 cards due')).toBeInTheDocument()
    expect(screen.getByText(/overdue task/)).toBeInTheDocument()
    expect(screen.getByText('· 5d')).toBeInTheDocument()
  })

  test('marking seen writes the actionable total on close', async () => {
    renderBell()
    const trigger = await screen.findByRole('button', { name: /notifications/i })
    await waitFor(() => expect(trigger.getAttribute('data-state')).toBe('closed'))
    expect(screen.getByText('4')).toBeInTheDocument()

    fireEvent.click(trigger)
    await screen.findByText('Due now')
    fireEvent.click(trigger)
    await waitFor(() => {
      expect(window.localStorage.getItem(storageKeys.notificationsSeen)).toBe('4')
    })
    await waitFor(() => {
      expect(screen.queryByText('4')).not.toBeInTheDocument()
    })
  })

  test('seen marker suppresses the dot until new items arrive', async () => {
    window.localStorage.setItem(storageKeys.notificationsSeen, '4')
    const { client } = renderBell()
    await waitFor(() => expect(getNotifications).toHaveBeenCalled())
    await waitFor(() => expect(screen.queryByText('4')).not.toBeInTheDocument())

    getNotifications.mockResolvedValue({ ...AGGREGATE, due_cards: 5 })
    await act(async () => {
      await client.invalidateQueries({ queryKey: ['notifications'] })
    })
    expect(await screen.findByText('6')).toBeInTheDocument()
  })

  test('actionableTotal is null while loading, counts rows when loaded', () => {
    expect(actionableTotal(undefined)).toBeNull()
    expect(actionableTotal(AGGREGATE)).toBe(4)
  })
})

describe('NotificationBell pending proposals (plan 78-E)', () => {
  test('lists pending tutor suggestions and links to chat', async () => {
    getNotifications.mockResolvedValue({
      ...AGGREGATE,
      pending_proposals: 2,
    })
    const { view } = renderBell()
    const trigger = await screen.findByRole('button', { name: /notifications/i })
    fireEvent.click(trigger)
    expect(await screen.findByText(/2 tutor suggestions to review/)).toBeInTheDocument()
    expect(view.getByText(/waiting for you/i)).toBeInTheDocument()
  })
})
