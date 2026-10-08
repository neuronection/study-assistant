import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, test, vi } from 'vitest'

import { ChatPanel } from './ChatPanel'
import { StudyChatProvider } from './useStudyChat'
import { useChatStore } from '@/lib/chat-store'

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
  flow?: string
  run_id?: string
  text?: string
  kind?: string
  node?: string
  id?: string
  name?: string
  args?: string
  result?: string
  title?: string
  status?: string
  duration_ms?: number
  reason?: 'user' | 'server'
  partial?: boolean
  message?: string
  code?: string
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
      <StudyChatProvider sessionId={4}>
        <ChatPanel onSessionCreated={() => undefined} onClose={() => undefined} />
      </StudyChatProvider>
    </QueryClientProvider>
  )
}

function renderAdoptingPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  function Wrapper() {
    const [sessionId, setSessionId] = useState<number | null>(null)
    return (
      <QueryClientProvider client={client}>
        <StudyChatProvider sessionId={sessionId}>
          <ChatPanel
            onSessionCreated={(session) => setSessionId(session.id)}
            onClose={() => undefined}
          />
        </StudyChatProvider>
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
    chatHandler!({ type: 'flow_started', flow: 'chat' } satisfies ChatEvent)
    chatHandler!({ type: 'delta', text: 'The answer is ' } satisfies ChatEvent)
    chatHandler!({ type: 'delta', text: '$2x$' } satisfies ChatEvent)
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
    chatHandler!({ type: 'flow_finished' } satisfies ChatEvent)
    await waitFor(() => {
      const bubble = screen.getByText(/answer is/, { exact: false })
      expect(bubble.closest('[data-as="chat-message"][data-status="done"]')).not.toBeNull()
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
    chatHandler!({ type: 'flow_started', flow: 'chat' } satisfies ChatEvent)
    chatHandler!({
      type: 'delta',
      text: 'inner thoughts',
      kind: 'reasoning',
    } satisfies ChatEvent)
    expect(await screen.findByText('inner thoughts')).toBeInTheDocument()

    chatHandler!({ type: 'delta', text: 'The answer is ' } satisfies ChatEvent)
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
    chatHandler!({ type: 'flow_started', flow: 'chat' } satisfies ChatEvent)
    chatHandler!({
      type: 'tool_call',
      id: 'CALC@42',
      name: 'CALC',
      args: 'sin(pi/6)',
      result: '0.5',
      status: 'done',
    } satisfies ChatEvent)
    const toggle = await screen.findByRole('button', { name: /CALC/ })
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
    chatHandler!({ type: 'flow_started', flow: 'chat' } satisfies ChatEvent)
    chatHandler!({
      type: 'tool_call',
      id: 'READ@7',
      name: 'READ',
      args: 'M12',
      title: 'Lecture 3',
      result: 'read 1234 chars',
      status: 'done',
    } satisfies ChatEvent)
    const toggle = await screen.findByRole('button', { name: /Lecture 3/ })
    expect(toggle).toHaveTextContent('READ')
    expect(toggle).toHaveTextContent('Lecture 3')
  })

  test('a pendingSend consumed on mount adopts the session and the turn survives the mount reset', async () => {
    listChatSessions.mockResolvedValue([SESSION])
    listChatMessages.mockResolvedValue([])
    sendChatMessage.mockResolvedValue({
      user_message: { id: 9, role: 'user', markdown: 'Summarize this', citations: [], grounded: null },
      job_id: 14,
    })
    act(() => {
      useChatStore.getState().openSession({ id: 4, publicId: 'uuid-4' })
      useChatStore.getState().queueSend({ content: 'Summarize this', mode: 'send' })
    })
    renderPanel()
    await waitFor(() => expect(sendChatMessage).toHaveBeenCalled())
    expect(await screen.findByRole('status')).toHaveAttribute(
      'aria-label',
      'Thinking…',
    )
    await waitFor(() => expect(chatHandler).not.toBeNull())
    chatHandler!({ type: 'flow_started', flow: 'chat' } satisfies ChatEvent)
    chatHandler!({ type: 'delta', text: 'Streaming the answer ' } satisfies ChatEvent)
    expect(await screen.findByText(/Streaming the answer/)).toBeInTheDocument()
    await waitFor(() => expect(useChatStore.getState().pendingSend).toBeNull())
    act(() => {
      useChatStore.getState().setOpen(false)
    })
  })

  test('thinking dots persist and the stream flows after adopting the created session', async () => {    listChatSessions.mockResolvedValue([])
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
    chatHandler!({ type: 'flow_started', flow: 'chat' } satisfies ChatEvent)
    chatHandler!({ type: 'delta', text: 'The answer is ' } satisfies ChatEvent)
    chatHandler!({ type: 'delta', text: '$2x$' } satisfies ChatEvent)
    expect(await screen.findByText(/The answer is/)).toBeInTheDocument()
  })

  test('a server-stopped turn keeps the partial answer and finalizes the panel', async () => {
    listChatSessions.mockResolvedValue([SESSION])
    listChatMessages.mockResolvedValue([])
    sendChatMessage.mockResolvedValue({
      user_message: { id: 9, role: 'user', markdown: 'hi', citations: [], grounded: null },
      job_id: 13,
    })
    renderPanel()
    const input = await screen.findByPlaceholderText('Ask about your material…')
    fireEvent.change(input, { target: { value: 'long answer please' } })
    fireEvent.submit(input.closest('form')!)
    await waitFor(() => expect(chatHandler).not.toBeNull())
    chatHandler!({ type: 'flow_started', flow: 'chat' } satisfies ChatEvent)
    chatHandler!({ type: 'delta', text: 'Partial answ' } satisfies ChatEvent)
    expect(await screen.findByText(/Partial answ/)).toBeInTheDocument()
    chatHandler!({
      type: 'flow_interrupted',
      reason: 'user',
      partial: true,
    } satisfies ChatEvent)

    listChatMessages.mockResolvedValue([
      { id: 9, role: 'user', markdown: 'long answer please', citations: [], grounded: null },
      {
        id: 10,
        role: 'assistant',
        markdown: 'Partial answ',
        citations: [],
        grounded: null,
      },
    ])
    await waitFor(() => {
      const bubble = screen.getByText(/Partial answ/, { exact: false })
      expect(bubble.closest('[data-as="chat-message"][data-status="done"]')).not.toBeNull()
    })
    await waitFor(() => expect(screen.queryByRole('status')).not.toBeInTheDocument())
  })

  test('flow_failed clears pending and renders the transcript error card', async () => {
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
    chatHandler!({ type: 'flow_started', flow: 'chat' } satisfies ChatEvent)
    chatHandler!({ type: 'delta', text: 'Partial answ' } satisfies ChatEvent)
    chatHandler!({ type: 'flow_failed', code: 'turn_error', message: 'provider offline' } satisfies ChatEvent)
    // The uniform card replaces the thinking indicator in the transcript…
    const alert = await screen.findByRole('alert')
    expect(screen.queryByText('Thinking…')).not.toBeInTheDocument()
    expect(alert).toHaveTextContent('provider offline')
    // The uniform card's actions: regenerate the failed turn. The old
    // footer's dismiss button is gone — the card clears via retry or
    // navigation instead.
    expect(screen.getByRole('button', { name: 'Regenerate answer' })).toBeInTheDocument()
  })

  test('unconfigured AI renders the uniform card with the settings affordance', async () => {
    listChatSessions.mockResolvedValue([SESSION])
    listChatMessages.mockResolvedValue([])
    sendChatMessage.mockResolvedValue({
      user_message: { id: 9, role: 'user', markdown: 'hi', citations: [], grounded: null },
      job_id: 13,
    })
    // The settings deep-link is a router Link — mount under a minimal tree.
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const rootRoute = createRootRoute({
      component: () => (
        <QueryClientProvider client={client}>
          <StudyChatProvider sessionId={4}>
            <ChatPanel onSessionCreated={() => undefined} onClose={() => undefined} />
          </StudyChatProvider>
        </QueryClientProvider>
      ),
    })
    const stub = (path: string) =>
      createRoute({ getParentRoute: () => rootRoute, path, component: () => null })
    const settingsRoute = createRoute({
      getParentRoute: () => rootRoute,
      path: '/settings',
      validateSearch: (search: Record<string, unknown>) => ({
        tab: typeof search.tab === 'string' ? search.tab : undefined,
        section: typeof search.section === 'string' ? search.section : undefined,
      }),
      component: () => null,
    })
    const router = createRouter({
      routeTree: rootRoute.addChildren([settingsRoute, stub('/chat')]),
      history: createMemoryHistory({ initialEntries: ['/chat'] }),
    })
    render(<RouterProvider router={router} />)
    const input = await screen.findByPlaceholderText('Ask about your material…')
    fireEvent.change(input, { target: { value: 'hello?' } })
    fireEvent.submit(input.closest('form')!)
    await waitFor(() => expect(chatHandler).not.toBeNull())
    chatHandler!({ type: 'flow_started', flow: 'chat' } satisfies ChatEvent)
    chatHandler!({
      type: 'flow_failed',
      code: 'ai_not_configured',
      message: 'AI is not configured yet. An admin can add a provider and assign models in Settings → AI Configuration.',
    } satisfies ChatEvent)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(
      'AI is not configured yet. An admin can add a provider and assign models in Settings → AI Configuration.',
    )
    // The settings deep-link renders when the kit carries the affordance;
    // the card itself (message + regenerate + dismiss) is the uniform part.
    expect(await screen.findByText('Open AI settings')).toBeInTheDocument()
  })
})
