import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { ChatSessionList } from './ChatSessionList'
import type { ChatSession } from '@/lib/api'

const listChatSessions = vi.fn()
const renameChatSession = vi.fn()
const deleteChatSession = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listChatSessions: () => listChatSessions(),
    renameChatSession: (...args: unknown[]) =>
      renameChatSession(...(args as [number, string])),
    deleteChatSession: (id: number) => deleteChatSession(id),
  }
})

function renderList(
  props: {
    onSelectSession?: (session: ChatSession) => void
    onNewChat?: () => void
    activeSessionId?: number | null
  } = {},
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const rootRoute = createRootRoute()
  const indexRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/',
    component: () => (
      <QueryClientProvider client={client}>
        <div className="h-96 w-72">
          <ChatSessionList {...props} />
        </div>
      </QueryClientProvider>
    ),
  })
  const chatRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/chat',
    component: () => <div>chat-page</div>,
  })
  const chatDetailRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/chat/$chatId',
    component: () => <div>chat-detail</div>,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([indexRoute, chatRoute, chatDetailRoute]),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  })
  return render(<RouterProvider router={router} />)
}

const SESSIONS = [
  {
    id: 4,
    public_id: 'uuid-4',
    course_id: null,
    node_id: null,
    title: 'Chain rule chat',
    created_at: new Date().toISOString(),
  },
  {
    id: 5,
    public_id: 'uuid-5',
    course_id: null,
    node_id: null,
    title: 'Integration review',
    created_at: new Date(Date.now() - 86_400_000).toISOString(),
  },
]

describe('ChatSessionList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  test('selecting a chat navigates to its route', async () => {
    listChatSessions.mockResolvedValue(SESSIONS)
    renderList()
    fireEvent.click(await screen.findByRole('button', { name: 'Chain rule chat · #4' }))
    expect(await screen.findByText('chat-detail')).toBeInTheDocument()
  })

  test('filters chats by search', async () => {
    listChatSessions.mockResolvedValue(SESSIONS)
    renderList()
    const input = await screen.findByRole('textbox', { name: 'Search chats…' })
    fireEvent.change(input, { target: { value: 'integration' } })
    expect(screen.queryByText('Chain rule chat')).not.toBeInTheDocument()
    expect(screen.getByText('Integration review')).toBeInTheDocument()
  })

  test('new chat navigates to the chat page', async () => {
    listChatSessions.mockResolvedValue(SESSIONS)
    renderList()
    fireEvent.click(await screen.findByRole('button', { name: 'New chat' }))
    expect(await screen.findByText('chat-page')).toBeInTheDocument()
  })

  test('selecting a chat in sidepanel mode calls onSelectSession instead of navigating', async () => {
    listChatSessions.mockResolvedValue(SESSIONS)
    const onSelectSession = vi.fn()
    renderList({ onSelectSession })
    fireEvent.click(await screen.findByRole('button', { name: 'Chain rule chat · #4' }))
    expect(onSelectSession).toHaveBeenCalledWith(
      expect.objectContaining({ id: 4, public_id: 'uuid-4' }),
    )
    expect(screen.queryByText('chat-detail')).not.toBeInTheDocument()
  })

  test('new chat in sidepanel mode calls onNewChat instead of navigating', async () => {
    listChatSessions.mockResolvedValue(SESSIONS)
    const onNewChat = vi.fn()
    renderList({ onNewChat })
    fireEvent.click(await screen.findByRole('button', { name: 'New chat' }))
    expect(onNewChat).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('chat-page')).not.toBeInTheDocument()
  })

  test('deleting the active sidepanel chat calls onNewChat', async () => {
    listChatSessions.mockResolvedValue(SESSIONS)
    deleteChatSession.mockResolvedValue({ deleted_item_id: 4 })
    const onNewChat = vi.fn()
    renderList({ onNewChat, activeSessionId: 4 })
    fireEvent.pointerDown(await screen.findByRole('button', { name: 'Actions for Chain rule chat' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Delete chat' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Delete chat' }))
    await waitFor(() => expect(onNewChat).toHaveBeenCalledTimes(1))
  })

  test('renames a chat from its menu', async () => {
    listChatSessions.mockResolvedValue(SESSIONS)
    renameChatSession.mockResolvedValue({ ...SESSIONS[0], title: 'Renamed' })
    renderList()
    fireEvent.pointerDown(await screen.findByRole('button', { name: 'Actions for Chain rule chat' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Rename chat' }))
    const input = await screen.findByRole('textbox', { name: 'Rename chat' })
    fireEvent.change(input, { target: { value: 'Renamed' } })
    fireEvent.submit(input.closest('form')!)
    await waitFor(() => expect(renameChatSession).toHaveBeenCalledWith(4, 'Renamed'))
  })

  test('deletes a chat from its menu', async () => {
    listChatSessions.mockResolvedValue(SESSIONS)
    deleteChatSession.mockResolvedValue({ deleted_item_id: 4 })
    renderList()
    fireEvent.pointerDown(await screen.findByRole('button', { name: 'Actions for Chain rule chat' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Delete chat' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Delete chat' }))
    await waitFor(() => expect(deleteChatSession).toHaveBeenCalledWith(4))
  })
})
