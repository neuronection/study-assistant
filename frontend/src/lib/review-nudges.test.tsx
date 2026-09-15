import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { useNudgeStore, useReviewNudgeInterval, useReviewNudgeSetting } from './review-nudges'
import { storageKeys } from '@/lib/constants'

type NotificationCtor = new (title: string, options?: NotificationOptions) => Notification

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
}))

const notificationTitles: string[] = []
const mockNotificationImpl = function (this: unknown, title: string) {
  notificationTitles.push(title)
  return { title, onclick: null } as unknown as Notification
}
const mockNotification = vi.fn(mockNotificationImpl) as unknown as NotificationCtor

const mockApi = {
  permission: 'default' as NotificationPermission,
  requestPermission: vi.fn(async () => 'granted' as NotificationPermission),
  Notification: mockNotification,
}

function setGlobalNotification(value: unknown) {
  Object.defineProperty(window, 'Notification', {
    configurable: true,
    writable: true,
    value,
  })
}

function Probe() {
  const { enabled, permission, setEnabled } = useReviewNudgeSetting()
  useReviewNudgeInterval()
  return (
    <div>
      <span data-testid="enabled">{String(enabled)}</span>
      <span data-testid="permission">{permission}</span>
      <button type="button" onClick={() => setEnabled(true)}>
        enable
      </button>
      <button type="button" onClick={() => setEnabled(false)}>
        disable
      </button>
    </div>
  )
}

function renderProbe() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <Probe />
    </QueryClientProvider>
  )
}

describe('useReviewNudges', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    useNudgeStore.setState({ enabled: false })
    getNotifications.mockReset()
    getNotifications.mockResolvedValue({ due_cards: 7 })
    try {
      window.localStorage.clear()
    } catch {
      return
    }
    notificationTitles.length = 0
    mockApi.permission = 'default'
    mockApi.requestPermission.mockReset()
    mockApi.requestPermission.mockImplementation(async () => {
      mockApi.permission = 'granted'
      return 'granted'
    })
    setGlobalNotification(mockApi)
  })

  afterEach(() => {
    vi.useRealTimers()
    setGlobalNotification(undefined)
  })

  test('defaults to off with the detected permission', () => {
    renderProbe()
    expect(screen.getByTestId('enabled').textContent).toBe('false')
    expect(screen.getByTestId('permission').textContent).toBe('default')
  })

  test('enabling requests permission and persists the flag', async () => {
    renderProbe()
    fireEvent.click(screen.getByText('enable'))
    await act(async () => {})
    expect(mockApi.requestPermission).toHaveBeenCalled()
    expect(screen.getByTestId('enabled').textContent).toBe('true')
    expect(window.localStorage.getItem(storageKeys.reviewNudges)).toBe('1')
  })

  test('denied permission keeps the nudge off', async () => {
    mockApi.requestPermission.mockImplementation(async () => {
      mockApi.permission = 'denied'
      return 'denied'
    })
    renderProbe()
    fireEvent.click(screen.getByText('enable'))
    await act(async () => {})
    expect(screen.getByTestId('permission').textContent).toBe('denied')
    expect(screen.getByTestId('enabled').textContent).toBe('false')
    expect(window.localStorage.getItem(storageKeys.reviewNudges)).toBeNull()
  })

  test('unsupported environments report honestly and never enable', async () => {
    setGlobalNotification(undefined)
    renderProbe()
    expect(screen.getByTestId('permission').textContent).toBe('unsupported')
    fireEvent(screen.getByText('enable'), new MouseEvent('click', { bubbles: true }))
    await act(async () => {})
    expect(screen.getByTestId('enabled').textContent).toBe('false')
  })

  test('fires one summary notification per interval when due cards exist', async () => {
    renderProbe()
    fireEvent.click(screen.getByText('enable'))
    await act(async () => {})
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30 * 60 * 1000)
    })
    expect(notificationTitles.length).toBeGreaterThanOrEqual(1)
    expect(notificationTitles[0]).toContain('7')

    await act(async () => {
      await vi.advanceTimersByTimeAsync(29 * 60 * 1000)
    })
    const firedAfter29 = notificationTitles.length
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2 * 60 * 1000)
    })
    expect(notificationTitles.length).toBe(firedAfter29 + 1)
  })

  test('no notification when nothing is due', async () => {
    getNotifications.mockResolvedValue({ due_cards: 0 })
    renderProbe()
    fireEvent.click(screen.getByText('enable'))
    await act(async () => {})
    await act(async () => {
      await vi.advanceTimersByTimeAsync(90 * 60 * 1000)
    })
    expect(notificationTitles.length).toBe(0)
  })
})
