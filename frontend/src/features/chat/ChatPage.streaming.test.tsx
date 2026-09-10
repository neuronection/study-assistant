import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  Outlet,
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { ChatPage } from './ChatPage'

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

function renderChatPage(): { getPath: () => string } {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const rootRoute = createRootRoute({ component: () => <Outlet /> })
  const chatRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/chat',
    component: () => (
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>
    ),
  })
  const chatIndexRoute = createRoute({
    getParentRoute: () => chatRoute,
    path: '/',
    component: () => null,
  })
  const chatDetailRoute = createRoute({
    getParentRoute: () => chatRoute,
    path: '$chatId',
    component: () => null,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([
      chatRoute.addChildren([chatIndexRoute, chatDetailRoute]),
    ]),
    history: createMemoryHistory({ initialEntries: ['/chat'] }),
  })
  render(<RouterProvider router={router} />)
  return { getPath: () => router.state.location.pathname }
}

describe('ChatPage full-page streaming', () => {
  test('the first send navigates to the created session and the stream survives the route change', async () => {
    const created = {
      id: 99,
      public_id: 'uuid-99',
      course_id: null,
      title: 'derive x^2',
      use_embeddings: true,
      quizme: false,
    }
    listChatSessions.mockImplementation(async () =>
      createChatSession.mock.calls.length > 0 ? [created] : [],
    )
    listChatMessages.mockResolvedValue([])
    createChatSession.mockResolvedValue(created)
    sendChatMessage.mockResolvedValue({
      user_message: { id: 9, role: 'user', markdown: 'derive x^2', citations: [], grounded: null },
      job_id: 12,
    })
    const page = renderChatPage()
    expect(page.getPath()).toBe('/chat')

    const input = await screen.findByPlaceholderText('Ask about your material…')
    fireEvent.change(input, { target: { value: 'derive x^2' } })
    fireEvent.submit(input.closest('form')!)

    await waitFor(() => expect(createChatSession).toHaveBeenCalled())
    await waitFor(() => expect(page.getPath()).toBe('/chat/uuid-99'))

    expect(await screen.findByRole('status')).toHaveAttribute(
      'aria-label',
      'Thinking…',
    )

    await waitFor(() => expect(chatHandler).not.toBeNull())
    chatHandler!({ type: 'stream_start' } satisfies ChatEvent)
    chatHandler!({ type: 'stream_delta', delta: 'The answer is ' } satisfies ChatEvent)
    chatHandler!({ type: 'stream_delta', delta: '$2x$' } satisfies ChatEvent)
    expect(await screen.findByText(/The answer is/)).toBeInTheDocument()

    listChatMessages.mockResolvedValue([
      { id: 9, role: 'user', markdown: 'derive x^2', citations: [], grounded: null },
      {
        id: 10,
        role: 'assistant',
        markdown: 'The answer is $2x$',
        citations: [],
        grounded: true,
      },
    ])
    chatHandler!({ type: 'assistant_message', message: {} } satisfies ChatEvent)
    await waitFor(() => {
      const bubble = screen.getByText(/answer is/, { exact: false })
      expect(bubble.closest('[data-as="chat-message"][data-status="done"]')).not.toBeNull()
    })
    await waitFor(() => expect(screen.queryByRole('status')).not.toBeInTheDocument())
  })
})
