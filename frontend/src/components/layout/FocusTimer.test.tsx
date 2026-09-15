import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { FocusTimer } from './FocusTimer'
import { FOCUS_PRESETS, useFocusTimerStore } from '@/lib/focus-timer-store'

const startStudySession = vi.fn()
const beatStudySession = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    startStudySession: (body: unknown) => startStudySession(body),
    beatStudySession: (id: number, action: string) => beatStudySession(id, action),
  }
})

vi.mock('@tanstack/react-router', () => ({
  useLocation: (options?: {
    select?: (location: { pathname: string }) => unknown
  }) =>
    options?.select
      ? options.select({ pathname: '/courses/5/n/9' })
      : { pathname: '/courses/5/n/9' },
}))

function renderTimer() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <FocusTimer />
    </QueryClientProvider>
  )
}

describe('FocusTimer', () => {
  beforeEach(() => {
    startStudySession.mockReset()
    beatStudySession.mockReset()
    startStudySession.mockResolvedValue({ id: 31 })
    beatStudySession.mockResolvedValue({ id: 31 })
    act(() =>
      useFocusTimerStore.setState({
        phase: 'idle',
        presetKey: FOCUS_PRESETS[0].key,
        focusMin: FOCUS_PRESETS[0].focusMin,
        breakMin: FOCUS_PRESETS[0].breakMin,
        endsAt: 0,
        remainingSec: 0,
        sessionId: null,
        startedAtSec: 0,
      })
    )
  })

  afterEach(() => {
    act(() => useFocusTimerStore.setState({ phase: 'idle', sessionId: null }))
  })

  test('picker starts a timer focus session with the active route context', async () => {
    renderTimer()
    fireEvent.click(await screen.findByRole('button', { name: /start a focus timer/i }))
    fireEvent.click(await screen.findByRole('button', { name: /25 min \+ 5 break/ }))
    await waitFor(() =>
      expect(startStudySession).toHaveBeenCalledWith({
        kind: 'focus',
        source: 'timer',
        course_id: 5,
        node_id: 9,
      })
    )
    expect(await screen.findByText('25:00')).toBeInTheDocument()
    expect(useFocusTimerStore.getState().phase).toBe('focus')
  })

  test('completion ends the session and offers the break', async () => {
    act(() =>
      useFocusTimerStore.setState({
        phase: 'focus',
        focusMin: 25,
        breakMin: 5,
        remainingSec: 1500,
        endsAt: Date.now() + 1_500_000,
        sessionId: 31,
      })
    )
    renderTimer()
    expect(await screen.findByText('25:00')).toBeInTheDocument()
    act(() =>
      useFocusTimerStore.setState({
        remainingSec: 1,
        endsAt: Date.now() - 1000,
      })
    )
    act(() => useFocusTimerStore.getState().tick())
    expect(useFocusTimerStore.getState().phase).toBe('done')
    await waitFor(() => expect(beatStudySession).toHaveBeenCalledWith(31, 'end'))
    fireEvent.click(await screen.findByRole('button', { name: /break 5 min/i }))
    expect(useFocusTimerStore.getState().phase).toBe('break')
    expect(await screen.findByText('05:00')).toBeInTheDocument()
  })

  test('break completion returns to the picker', () => {
    act(() =>
      useFocusTimerStore.setState({
        phase: 'break',
        breakMin: 5,
        remainingSec: 1,
        endsAt: Date.now() - 1000,
      })
    )
    renderTimer()
    act(() => useFocusTimerStore.getState().tick())
    expect(useFocusTimerStore.getState().phase).toBe('idle')
    expect(
      screen.getByRole('button', { name: /start a focus timer/i })
    ).toBeInTheDocument()
  })

  test('pause ends the logged session, resume logs a new one', async () => {
    act(() =>
      useFocusTimerStore.setState({
        phase: 'focus',
        focusMin: 25,
        breakMin: 5,
        remainingSec: 600,
        endsAt: Date.now() + 600_000,
        sessionId: 31,
        lastContext: { courseId: 5, nodeId: 9 },
      })
    )
    renderTimer()
    fireEvent.click(await screen.findByRole('button', { name: /pause/i }))
    await waitFor(() => expect(beatStudySession).toHaveBeenCalledWith(31, 'end'))
    expect(useFocusTimerStore.getState().phase).toBe('paused')

    fireEvent.click(screen.getByRole('button', { name: /resume/i }))
    await waitFor(() =>
      expect(startStudySession).toHaveBeenCalledWith({
        kind: 'focus',
        source: 'timer',
        course_id: 5,
        node_id: 9,
      })
    )
    expect(useFocusTimerStore.getState().phase).toBe('focus')
  })

  test('give up returns to the idle pill', async () => {
    act(() =>
      useFocusTimerStore.setState({
        phase: 'focus',
        focusMin: 25,
        breakMin: 5,
        remainingSec: 600,
        endsAt: Date.now() + 600_000,
        sessionId: 31,
      })
    )
    renderTimer()
    fireEvent.click(await screen.findByRole('button', { name: /give up/i }))
    expect(useFocusTimerStore.getState().phase).toBe('idle')
    await waitFor(() => expect(beatStudySession).toHaveBeenCalledWith(31, 'end'))
    expect(
      await screen.findByRole('button', { name: /start a focus timer/i })
    ).toBeInTheDocument()
  })
})
