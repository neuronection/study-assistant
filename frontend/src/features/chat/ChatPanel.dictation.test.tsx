import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { ChatPanel } from './ChatPanel'
import type { ChatSession } from '@/lib/api'
import {
  installDictationMediaStub,
} from '@/test/dictationMedia'

const listChatSessions = vi.fn()
const listChatMessages = vi.fn()
const getChatContext = vi.fn()
const sendChatMessage = vi.fn()
const listAiTools = vi.fn()
const listMaterials = vi.fn()
const listNotes = vi.fn()
const listQuizzes = vi.fn()
const listExercises = vi.fn()
const listCourses = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listChatSessions: () => listChatSessions(),
    listChatMessages: (...args: unknown[]) => listChatMessages(...(args as [number])),
    getChatContext: (...args: unknown[]) => getChatContext(...(args as [number])),
    sendChatMessage: (...args: unknown[]) =>
      sendChatMessage(...(args as [number, string, unknown[] | undefined])),
    listAiTools: () => listAiTools(),
    listMaterials: () => listMaterials(),
    listNotes: () => listNotes(),
    listQuizzes: () => listQuizzes(),
    listExercises: () => listExercises(),
    listCourses: () => listCourses(),
    transcribeAudio: vi.fn(),
  }
})

import { transcribeAudio } from '@/lib/api'

const transcribeMock = vi.mocked(transcribeAudio)

vi.mock('@/lib/ws-client', () => ({
  getWsClient: () => ({
    subscribe: vi.fn(() => () => undefined),
  }),
}))

const SESSION: ChatSession = {
  id: 4,
  public_id: 'uuid-4',
  course_id: 7,
  node_id: null,
  title: 'New chat',
  use_embeddings: null,
  created_at: new Date().toISOString(),
}

function baseMocks() {
  listChatSessions.mockResolvedValue([SESSION])
  listChatMessages.mockResolvedValue([])
  getChatContext.mockResolvedValue({
    session_id: SESSION.id,
    course_id: SESSION.course_id,
    node: null,
    registry: [],
    latest_notes: [],
  })
}

function renderPanel() {
  baseMocks()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const rootRoute = createRootRoute()
  const route = createRoute({
    getParentRoute: () => rootRoute,
    path: '/',
    component: () => (
      <QueryClientProvider client={client}>
        <ChatPanel sessionId={4} onSessionCreated={() => undefined} />
      </QueryClientProvider>
    ),
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([route]),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  })
  return render(<RouterProvider router={router} />)
}

afterEach(() => {
  vi.unstubAllGlobals()
  transcribeMock.mockReset()
})

describe('ChatPanel dictation', () => {
  test('dictated text lands in the composer draft', async () => {
    installDictationMediaStub()
    transcribeMock.mockResolvedValue({ text: 'voice question', model: 'whisper-1' })
    renderPanel()

    fireEvent.click(await screen.findByRole('button', { name: 'Dictate' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Insert' }))

    const composer = await screen.findByPlaceholderText(
      'Ask about your material…',
    ) as HTMLTextAreaElement
    await waitFor(() => {
      expect(composer.value).toBe('voice question ')
    })
    expect(transcribeMock).toHaveBeenCalledTimes(1)
  })

  test('cancel keeps the draft empty', async () => {
    installDictationMediaStub()
    renderPanel()

    fireEvent.click(await screen.findByRole('button', { name: 'Dictate' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }))

    const composer = await screen.findByPlaceholderText(
      'Ask about your material…',
    ) as HTMLTextAreaElement
    expect(composer.value).toBe('')
    expect(transcribeMock).not.toHaveBeenCalled()
  })
})
