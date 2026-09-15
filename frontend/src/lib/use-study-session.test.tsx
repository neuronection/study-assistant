import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { useStudySession } from './use-study-session'

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

function makeWrapper() {
  const client = new QueryClient()
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>
  }
}

function Probe(options: Parameters<typeof useStudySession>[0]) {
  useStudySession(options)
  return null
}

describe('useStudySession', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    startStudySession.mockReset()
    beatStudySession.mockReset()
    startStudySession.mockResolvedValue({ id: 7 })
    beatStudySession.mockResolvedValue({ id: 7 })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  test('starts a session, heartbeats, and ends on unmount', async () => {
    const view = render(
      <Probe
        kind="quiz"
        entityRef="activity:42"
        courseId={3}
        nodeId={9}
        enabled={true}
      />,
      { wrapper: makeWrapper() }
    )
    await act(async () => {})
    expect(startStudySession).toHaveBeenCalledWith({
      kind: 'quiz',
      source: 'auto',
      entity_ref: 'activity:42',
      course_id: 3,
      node_id: 9,
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000)
    })
    expect(beatStudySession).toHaveBeenCalledTimes(1)
    expect(beatStudySession).toHaveBeenCalledWith(7, 'heartbeat')

    view.unmount()
    await act(async () => {})
    expect(beatStudySession).toHaveBeenLastCalledWith(7, 'end')
  })

  test('disabled hook never contacts the API', async () => {
    render(<Probe kind="read" enabled={false} />, { wrapper: makeWrapper() })
    await act(async () => {})
    expect(startStudySession).not.toHaveBeenCalled()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(180_000)
    })
    expect(beatStudySession).not.toHaveBeenCalled()
  })

  test('enabling later starts the session once', async () => {
    const view = render(<Probe kind="note" enabled={false} />, {
      wrapper: makeWrapper(),
    })
    await act(async () => {})
    expect(startStudySession).not.toHaveBeenCalled()

    view.rerender(<Probe kind="note" enabled={true} />)
    await act(async () => {})
    expect(startStudySession).toHaveBeenCalledTimes(1)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000)
    })
    expect(beatStudySession).toHaveBeenCalledWith(7, 'heartbeat')
  })

  test('unstable course context does not restart the session', async () => {
    const view = render(
      <Probe kind="quiz" courseId={undefined} enabled={true} />,
      { wrapper: makeWrapper() }
    )
    await act(async () => {})
    expect(startStudySession).toHaveBeenCalledTimes(1)
    view.rerender(<Probe kind="quiz" courseId={5} enabled={true} />)
    view.rerender(<Probe kind="quiz" courseId={5} nodeId={2} enabled={true} />)
    await act(async () => {})
    expect(startStudySession).toHaveBeenCalledTimes(1)
    expect(startStudySession).toHaveBeenLastCalledWith(
      expect.objectContaining({ kind: 'quiz', source: 'auto' })
    )
  })

  test('start failures never surface or heartbeat', async () => {
    startStudySession.mockRejectedValue(new Error('down'))
    const view = render(<Probe kind="read" enabled={true} />, {
      wrapper: makeWrapper(),
    })
    await act(async () => {})
    await act(async () => {
      await vi.advanceTimersByTimeAsync(180_000)
    })
    expect(beatStudySession).not.toHaveBeenCalled()
    view.unmount()
    await act(async () => {})
    expect(beatStudySession).not.toHaveBeenCalled()
  })
})
