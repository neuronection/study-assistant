import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, test, vi } from 'vitest'

import { ChatPanel } from './ChatPanel'

const listChatSessions = vi.fn()
const createChatSession = vi.fn()
const listChatMessages = vi.fn()
const sendChatMessage = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listChatSessions: () => listChatSessions(),
    createChatSession: (...args: unknown[]) => createChatSession(...(args as [])),
    listChatMessages: (...args: unknown[]) => listChatMessages(...(args as [number])),
    sendChatMessage: (...args: unknown[]) =>
      sendChatMessage(...(args as [number, string])),
  }
})

type ChatEvent = {
  type: string
  delta?: string
  kind?: string
  phase?: string
  name?: string
  argument?: string
  result?: string
  title?: string
  detail?: string
  message?: unknown
}

let chatHandler: ((payload: unknown) => void) | null = null

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

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ChatPanel sessionId={4} onSessionCreated={() => undefined} onClose={() => undefined} />
    </QueryClientProvider>
  )
}

function renderAdoptingPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  function Wrapper() {
    const [sessionId, setSessionId] = useState<number | null>(null)
    return (
      <QueryClientProvider client={client}>
        <ChatPanel
          sessionId={sessionId}
          onSessionCreated={(session) => setSessionId(session.id)}
          onClose={() => undefined}
        />
      </QueryClientProvider>
    )
  }
  return render(<Wrapper />)
}

const SESSION = { id: 4, public_id: 'uuid-4', course_id: null, title: 'New chat' }

describe('ChatPanel streaming', () => {
  test('stream deltas render progressively then finalize', async () => {
    listChatSessions.mockResolvedValue([SESSION])
    listChatMessages.mockResolvedValue([])
    sendChatMessage.mockResolvedValue({
      user_message: { id: 9, role: 'user', markdown: 'hi', citations: [], grounded: null },
      job_id: 12,
    })
    renderPanel()
    const input = await screen.findByPlaceholderText('Ask about your material…')
    fireEvent.change(input, { target: { value: 'derive x^2' } })
    fireEvent.submit(input.closest('form')!)
    await waitFor(() => expect(sendChatMessage).toHaveBeenCalled())
    expect(await screen.findByRole('status')).toHaveAttribute(
      'aria-label',
      'Thinking…',
    )
    expect(await screen.findByText('Thinking…')).toBeInTheDocument()

    expect(chatHandler).not.toBeNull()
    chatHandler!({ type: 'stream_start' } satisfies ChatEvent)
    chatHandler!({ type: 'stream_delta', delta: 'The answer is ' } satisfies ChatEvent)
    chatHandler!({ type: 'stream_delta', delta: '$2x$' } satisfies ChatEvent)
    expect(await screen.findByText(/The answer is/)).toBeInTheDocument()

    listChatMessages.mockResolvedValue([
      { id: 9, role: 'user', markdown: 'derive x^2', citations: [], grounded: null },
      {
        id: 10,
        role: 'assistant',
        markdown: 'The answer is $2x$ [1]',
        citations: [],
        grounded: true,
      },
    ])
    chatHandler!({ type: 'assistant_message', message: {} } satisfies ChatEvent)
    await waitFor(() => {
      const bubble = screen.getByText(/answer is/, { exact: false })
      expect(bubble.closest('.bg-subtle')).not.toBeNull()
    })
  })

  test('reasoning deltas stream into a separate thinking bubble', async () => {
    listChatSessions.mockResolvedValue([SESSION])
    listChatMessages.mockResolvedValue([])
    sendChatMessage.mockResolvedValue({
      user_message: { id: 9, role: 'user', markdown: 'hi', citations: [], grounded: null },
      job_id: 12,
    })
    renderPanel()
    const input = await screen.findByPlaceholderText('Ask about your material…')
    fireEvent.change(input, { target: { value: 'derive x^2' } })
    fireEvent.submit(input.closest('form')!)
    await waitFor(() => expect(chatHandler).not.toBeNull())
    chatHandler!({ type: 'stream_start' } satisfies ChatEvent)
    chatHandler!({
      type: 'stream_delta',
      delta: 'inner thoughts',
      kind: 'reasoning',
    } satisfies ChatEvent)
    expect(await screen.findByText('inner thoughts')).toBeInTheDocument()

    chatHandler!({ type: 'stream_delta', delta: 'The answer is ' } satisfies ChatEvent)
    expect(await screen.findByText(/The answer is/)).toBeInTheDocument()
    expect(screen.getByText('inner thoughts')).toBeInTheDocument()
  })

  test('tool call renders a collapsible card with argument and result', async () => {
    listChatSessions.mockResolvedValue([SESSION])
    listChatMessages.mockResolvedValue([])
    sendChatMessage.mockResolvedValue({
      user_message: { id: 9, role: 'user', markdown: 'hi', citations: [], grounded: null },
      job_id: 13,
    })
    renderPanel()
    const input = await screen.findByPlaceholderText('Ask about your material…')
    fireEvent.change(input, { target: { value: 'verify' } })
    fireEvent.submit(input.closest('form')!)
    await waitFor(() => expect(chatHandler).not.toBeNull())
    chatHandler!({ type: 'stream_start' } satisfies ChatEvent)
    chatHandler!({
      type: 'tool_call',
      name: 'CALC',
      argument: 'sin(pi/6)',
      result: '0.5',
      phase: 'math',
    } satisfies ChatEvent)
    const toggle = await screen.findByRole('button', { name: 'Show details for Calculate' })
    expect(toggle).toHaveTextContent('CALC')
    expect(toggle).toHaveTextContent('sin(pi/6)')
    fireEvent.click(toggle)
    expect(await screen.findByText('Argument')).toBeInTheDocument()
    expect(screen.getByText('Result')).toBeInTheDocument()
    expect(screen.getByText('= 0.5')).toBeInTheDocument()
  })

  test('read tool call shows the resolved title', async () => {
    listChatSessions.mockResolvedValue([SESSION])
    listChatMessages.mockResolvedValue([])
    sendChatMessage.mockResolvedValue({
      user_message: { id: 9, role: 'user', markdown: 'hi', citations: [], grounded: null },
      job_id: 13,
    })
    renderPanel()
    const input = await screen.findByPlaceholderText('Ask about your material…')
    fireEvent.change(input, { target: { value: 'read my note' } })
    fireEvent.submit(input.closest('form')!)
    await waitFor(() => expect(chatHandler).not.toBeNull())
    chatHandler!({ type: 'stream_start' } satisfies ChatEvent)
    chatHandler!({
      type: 'tool_call',
      name: 'READ',
      argument: 'M12',
      title: 'Lecture 3',
      result: 'read 1234 chars',
      phase: 'read',
    } satisfies ChatEvent)
    const toggle = await screen.findByRole('button', { name: 'Show details for Read item' })
    expect(toggle).toHaveTextContent('READ')
    expect(toggle).toHaveTextContent('Lecture 3')
  })

  test('thinking dots persist and the stream flows after adopting the created session', async () => {
    listChatSessions.mockResolvedValue([])
    listChatMessages.mockResolvedValue([])
    createChatSession.mockResolvedValue({
      id: 99,
      public_id: 'uuid-99',
      course_id: null,
      title: 'derive x^2',
    })
    sendChatMessage.mockResolvedValue({
      user_message: { id: 9, role: 'user', markdown: 'hi', citations: [], grounded: null },
      job_id: 13,
    })
    renderAdoptingPanel()
    const input = await screen.findByPlaceholderText('Ask about your material…')
    fireEvent.change(input, { target: { value: 'derive x^2' } })
    fireEvent.submit(input.closest('form')!)
    await waitFor(() => expect(createChatSession).toHaveBeenCalled())
    expect(await screen.findByRole('status')).toHaveAttribute(
      'aria-label',
      'Thinking…',
    )
    await waitFor(() => expect(chatHandler).not.toBeNull())
    chatHandler!({ type: 'stream_start' } satisfies ChatEvent)
    chatHandler!({ type: 'stream_delta', delta: 'The answer is ' } satisfies ChatEvent)
    chatHandler!({ type: 'stream_delta', delta: '$2x$' } satisfies ChatEvent)
    expect(await screen.findByText(/The answer is/)).toBeInTheDocument()
  })

  test('turn_error clears pending and shows the failure banner', async () => {
    listChatSessions.mockResolvedValue([SESSION])
    listChatMessages.mockResolvedValue([])
    sendChatMessage.mockResolvedValue({
      user_message: { id: 9, role: 'user', markdown: 'hi', citations: [], grounded: null },
      job_id: 13,
    })
    renderPanel()
    const input = await screen.findByPlaceholderText('Ask about your material…')
    fireEvent.change(input, { target: { value: 'hello?' } })
    fireEvent.submit(input.closest('form')!)
    await waitFor(() => expect(chatHandler).not.toBeNull())
    chatHandler!({ type: 'stream_start' } satisfies ChatEvent)
    chatHandler!({ type: 'stream_delta', delta: 'Partial answ' } satisfies ChatEvent)
    chatHandler!({ type: 'turn_error', detail: 'provider offline' } satisfies ChatEvent)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The tutor failed to answer. (provider offline)')
    await waitFor(() =>
      expect(screen.queryByRole('status')).not.toBeInTheDocument(),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss error' }))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
