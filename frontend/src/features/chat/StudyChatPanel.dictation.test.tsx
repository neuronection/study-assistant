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

import { StudyChatPanel } from './StudyChatPanel'
import { StudyChatProvider } from './useStudyChat'
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
const listTasks = vi.fn()

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
    listTasks: () => listTasks(),
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
  id: '4',
  public_id: 'uuid-4',
  course_id: '7',
  node_id: null,
  title: 'New chat',
  quizme: false,
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

function renderPanel(tasks: unknown[] | 'loading' | 'error' = []) {
  baseMocks()
  if (tasks === 'loading') {
    listTasks.mockReturnValue(new Promise(() => undefined))
  } else if (tasks === 'error') {
    listTasks.mockRejectedValue(new Error('tasks failed'))
  } else {
    listTasks.mockResolvedValue(tasks)
  }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const rootRoute = createRootRoute()
  const route = createRoute({
    getParentRoute: () => rootRoute,
    path: '/',
    component: () => (
      <QueryClientProvider client={client}>
        <StudyChatProvider sessionId="4">
          <StudyChatPanel onSessionCreated={() => undefined} />
        </StudyChatProvider>
      </QueryClientProvider>
    ),
  })
  const settingsRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/settings',
    component: () => null,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([route, settingsRoute]),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  })
  const result = render(<RouterProvider router={router} />)
  return { ...result, router }
}

function sttTask(overrides: Record<string, unknown> = {}) {
  return {
    task: 'transcribe',
    requires: 'stt',
    model_id: null,
    model_label: null,
    fallback_model_id: null,
    fallback_model_label: null,
    default_model_label: null,
    ...overrides,
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
  transcribeMock.mockReset()
})

describe('StudyChatPanel dictation', () => {
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

  test('points to model assignment when no speech-to-text task is assigned', async () => {
    renderPanel([sttTask()])
    expect(await screen.findByRole('note')).toHaveTextContent('Dictation unavailable')
    expect(screen.getByRole('note')).toHaveTextContent('No speech-to-text model assigned')
    expect(
      screen.getByRole('button', { name: 'Assign a speech-to-text model' }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Dictate' })).not.toBeInTheDocument()
  })

  test('the unavailable settings action opens the task assignment settings', async () => {
    const { router } = renderPanel([sttTask()])
    fireEvent.click(await screen.findByRole('button', { name: 'Assign a speech-to-text model' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/settings'))
    expect(router.state.location.search).toEqual({ tab: 'ai', section: 'tasks' })
  })

  test.each([
    ['primary', { model_id: 'whisper-1', model_label: 'Whisper' }],
    ['fallback', { fallback_model_id: 'whisper-2', fallback_model_label: 'Whisper fallback' }],
    ['default', { default_model_label: 'Default speech model' }],
  ])('keeps the mic when a %s assignment exists', async (_case, overrides) => {
    renderPanel([sttTask(overrides)])
    expect(await screen.findByRole('button', { name: 'Dictate' })).toBeInTheDocument()
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })

  test('keeps the mic while the assignment query is unknown', async () => {
    renderPanel([])
    expect(await screen.findByRole('button', { name: 'Dictate' })).toBeInTheDocument()
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })

  test.each([
    ['loading', 'loading'],
    ['error', 'error'],
  ] as const)('keeps the mic while the assignment query is %s', async (_case, mode) => {
    renderPanel(mode)
    expect(await screen.findByRole('button', { name: 'Dictate' })).toBeInTheDocument()
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
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
