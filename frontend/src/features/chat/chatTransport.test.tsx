import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { mapStudyEvent, createStudyChatTransport } from './chatTransport'
import { StudyChatProvider, useStudyChatContext } from './useStudyChat'

const sendChatMessage = vi.fn()
const stopChatTurn = vi.fn()
let chatHandler: ((payload: unknown) => void) | null = null

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    sendChatMessage: (...args: unknown[]) =>
      sendChatMessage(...(args as [number, string, unknown[] | undefined])),
    stopChatTurn: (...args: unknown[]) => stopChatTurn(...(args as [number])),
  }
})

vi.mock('@/lib/ws-client', () => ({
  getWsClient: () => ({
    subscribe: vi.fn((topic: string, handler: (payload: unknown) => void) => {
      if (topic.startsWith('chat:')) {
        chatHandler = handler
      }
      return () => {
        chatHandler = null
      }
    }),
  }),
}))

const phaseLabel = (phase: string) => `phase:${phase}`

describe('mapStudyEvent', () => {
  test('flow_started opens the family flow without touching status', () => {
    expect(mapStudyEvent({ type: 'flow_started' }, { phaseLabel, runId: 'turn-1' })).toEqual({
      event: 'flow_started',
      flow: 'chat',
      run_id: 'turn-1',
    })
  })

  test('node_started maps the wire node id to the i18n label', () => {
    expect(
      mapStudyEvent({ type: 'node_started', node: 'reading' }, { phaseLabel, runId: 'turn-1' }),
    ).toEqual({
      event: 'node_started',
      node: 'reading',
      label: 'phase:reading',
      run_id: 'turn-1',
    })
  })

  test('answer deltas carry kind text and reasoning deltas kind reasoning', () => {
    expect(
      mapStudyEvent({ type: 'delta', text: 'Hello ' }, { phaseLabel, runId: 'turn-1' }),
    ).toEqual({ event: 'delta', kind: 'text', text: 'Hello ', run_id: 'turn-1' })
    expect(
      mapStudyEvent(
        { type: 'delta', text: 'thought', kind: 'reasoning' },
        { phaseLabel, runId: 'turn-1' },
      ),
    ).toEqual({ event: 'delta', kind: 'reasoning', text: 'thought', run_id: 'turn-1' })
    expect(mapStudyEvent({ type: 'delta' }, { phaseLabel })).toBeNull()
  })

  test('tool_call events pass the frozen wire fields through', () => {
    expect(
      mapStudyEvent(
        {
          type: 'tool_call',
          id: 'SYMPY@42',
          name: 'SYMPY',
          args: 'diff x**3',
          result: '3*x**2',
          title: 'Symbolic math',
          status: 'done',
          duration_ms: 120,
        },
        { phaseLabel, runId: 'turn-1' },
      ),
    ).toEqual({
      event: 'tool_call',
      id: 'SYMPY@42',
      name: 'SYMPY',
      title: 'Symbolic math',
      status: 'done',
      args: 'diff x**3',
      result: '3*x**2',
      durationMs: 120,
      run_id: 'turn-1',
    })
  })

  test('tool_call without a result or status reports running', () => {
    const event = mapStudyEvent(
      { type: 'tool_call', id: 'SEARCH@7', name: 'SEARCH', args: 'chain rule' },
      { phaseLabel },
    )
    expect(event).toMatchObject({ event: 'tool_call', id: 'SEARCH@7', status: 'running' })
  })

  test('flow_finished finalizes and flow_interrupted stops the turn', () => {
    expect(mapStudyEvent({ type: 'flow_finished' }, { phaseLabel, runId: 'turn-1' })).toEqual({
      event: 'flow_finished',
      run_id: 'turn-1',
    })
    expect(
      mapStudyEvent(
        { type: 'flow_interrupted', reason: 'user', partial: true },
        { phaseLabel, runId: 'turn-1' },
      ),
    ).toEqual({
      event: 'flow_interrupted',
      reason: 'user',
      partial: true,
    })
  })

  test('flow_failed maps to a retryable flow failure', () => {
    expect(
      mapStudyEvent(
        { type: 'flow_failed', code: 'turn_error', message: 'provider offline', retryable: true },
        { phaseLabel, runId: 'turn-1' },
      ),
    ).toEqual({
      event: 'flow_failed',
      code: 'turn_error',
      message: 'provider offline',
      retryable: true,
      run_id: 'turn-1',
    })
    expect(
      mapStudyEvent({ type: 'flow_failed', message: 'late' }, { phaseLabel, runId: 'turn-1' }),
    ).toMatchObject({ event: 'flow_failed', code: 'turn_error', retryable: true })
  })

  test('unknown event names are dropped (additive contract)', () => {
    expect(mapStudyEvent({ type: 'someday_new_event' }, { phaseLabel })).toBeNull()
  })
})

describe('createStudyChatTransport', () => {
  function makeTransport(getSessionId: () => number | null = () => 4) {
    return createStudyChatTransport({ getSessionId, phaseLabel })
  }

  test('send posts to the active session with attachments and clears them after', async () => {
    sendChatMessage.mockResolvedValue({ user_message: {}, job_id: 1 })
    let sessionId: number | null = 4
    const transport = makeTransport(() => sessionId)
    const seen: string[] = []
    transport.subscribe({ onEvent: (event) => seen.push(event.event) })
    transport.setAttachments([{ kind: 'note', id: 7 }])
    await transport.send({ text: 'hello' })
    expect(sendChatMessage).toHaveBeenCalledWith(4, 'hello', [{ kind: 'note', id: 7 }])
    sessionId = 5
    await transport.send({ text: 'again' })
    expect(sendChatMessage).toHaveBeenLastCalledWith(5, 'again', [])
  })

  test('send without a session throws (the hook reports send_failed)', async () => {
    const transport = makeTransport(() => null)
    await expect(transport.send({ text: 'hello' })).rejects.toThrow('No active chat session')
  })

  test('stop calls the stop endpoint for the active session', async () => {
    stopChatTurn.mockResolvedValue({ stopped: true })
    const transport = makeTransport()
    await transport.stop?.()
    expect(stopChatTurn).toHaveBeenCalledWith(4)
  })

  test('stragglers from a previous turn are gated until the new stream starts', async () => {
    sendChatMessage.mockResolvedValue({ user_message: {}, job_id: 2 })
    const transport = makeTransport()
    const seen: { event: string; run_id?: string }[] = []
    transport.subscribe({ onEvent: (event) => seen.push({ event: event.event, run_id: 'run_id' in event ? event.run_id : undefined }) })

    transport.push({ type: 'flow_started', flow: 'chat', run_id: 'server-1' })
    transport.push({ type: 'delta', text: 'a' })
    transport.push({ type: 'flow_finished' })
    expect(seen).toEqual([
      { event: 'flow_started', run_id: 'turn-0' },
      { event: 'delta', run_id: 'turn-0' },
      { event: 'flow_finished', run_id: 'turn-0' },
    ])

    await transport.send({ text: 'next' })
    transport.push({ type: 'delta', text: 'straggler' })
    transport.push({ type: 'flow_failed', code: 'turn_error', message: 'late' })
    expect(seen).toHaveLength(3)

    transport.push({ type: 'flow_started', flow: 'chat', run_id: 'server-2' })
    transport.push({ type: 'delta', text: 'fresh' })
    expect(seen).toHaveLength(5)
    expect(seen[3]).toEqual({ event: 'flow_started', run_id: 'turn-1' })
    expect(seen[4]).toEqual({ event: 'delta', run_id: 'turn-1' })
  })
})

describe('useStudyChat (provider wiring)', () => {
  function renderInProvider(sessionId: number | null) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    return renderHook(() => useStudyChatContext(), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={client}>
          <StudyChatProvider sessionId={sessionId}>{children}</StudyChatProvider>
        </QueryClientProvider>
      ),
    })
  }

  test('a pushed turn streams through useChatStream and finalizes', async () => {
    sendChatMessage.mockResolvedValue({ user_message: {}, job_id: 1 })
    const { result } = renderInProvider(4)
    expect(result.current.stream.live).toBeNull()

    await act(async () => {
      await result.current.send('derive x^2')
    })
    expect(result.current.stream.status).toBe('pending')

    act(() => {
      chatHandler!({ type: 'flow_started', flow: 'chat', run_id: 'server-1' })
      chatHandler!({ type: 'delta', text: 'The answer is ' })
      chatHandler!({ type: 'delta', text: '$2x$' })
    })
    await waitFor(() => expect(result.current.stream.text).toBe('The answer is $2x$'))

    act(() => {
      chatHandler!({ type: 'flow_finished', run_id: 'server-1' })
    })
    await waitFor(() => expect(result.current.stream.live).toBeNull())
  })

  test('a server-stopped turn ends interrupted through flow_interrupted', async () => {
    sendChatMessage.mockResolvedValue({ user_message: {}, job_id: 1 })
    const { result } = renderInProvider(4)
    await act(async () => {
      await result.current.send('stop me')
    })
    act(() => {
      chatHandler!({ type: 'flow_started', flow: 'chat', run_id: 'server-2' })
      chatHandler!({ type: 'delta', text: 'partial answ' })
      chatHandler!({ type: 'flow_interrupted', reason: 'user', partial: true })
    })
    await waitFor(() => {
      expect(result.current.stream.status).toBe('interrupted')
      expect(result.current.stream.stopped).toBe(true)
      expect(result.current.stream.text).toBe('partial answ')
    })
  })

  test('reasoning and tool call events land in the live turn state', async () => {
    sendChatMessage.mockResolvedValue({ user_message: {}, job_id: 1 })
    const { result } = renderInProvider(4)
    await act(async () => {
      await result.current.send('think')
    })
    act(() => {
      chatHandler!({ type: 'flow_started', flow: 'chat', run_id: 'server-3' })
      chatHandler!({ type: 'delta', text: 'inner', kind: 'reasoning' })
      chatHandler!({ type: 'node_started', node: 'reading' })
      chatHandler!({
        type: 'tool_call',
        id: 'READ@9',
        name: 'READ',
        args: 'M12',
        result: 'ok',
        status: 'done',
      })
    })
    await waitFor(() => {
      expect(result.current.stream.reasoning).toBe('inner')
      expect(result.current.stream.nodes).toEqual([
        expect.objectContaining({ id: 'reading', status: 'running' }),
      ])
      expect(result.current.stream.toolCalls).toEqual([
        {
          id: 'READ@9',
          name: 'READ',
          title: undefined,
          status: 'done',
          args: 'M12',
          result: 'ok',
          durationMs: undefined,
        },
      ])
    })
  })

  test('coalesced deltas arrive in order and reset clears the tail', async () => {
    sendChatMessage.mockResolvedValue({ user_message: {}, job_id: 1 })
    const { result } = renderInProvider(4)
    await act(async () => {
      await result.current.send('hi')
    })
    act(() => {
      chatHandler!({ type: 'flow_started', flow: 'chat', run_id: 'server-4' })
      for (const chunk of ['a', 'b', 'c']) {
        chatHandler!({ type: 'delta', text: chunk })
      }
    })
    await waitFor(() => expect(result.current.stream.text).toBe('abc'))
    act(() => {
      result.current.stream.reset()
    })
    expect(result.current.stream.text).toBeNull()
    expect(result.current.stream.live).toBeNull()
  })
})
