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

import { ChatPanel } from './ChatPanel'
import type { ChatSession } from '@/lib/api'

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
const uploadMaterial = vi.fn()
const listFolders = vi.fn()
const createFolder = vi.fn()

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
    listMaterials: (...args: unknown[]) => listMaterials(...(args as [])),
    listNotes: (...args: unknown[]) => listNotes(...(args as [])),
    listQuizzes: (...args: unknown[]) => listQuizzes(...(args as [])),
    listExercises: (...args: unknown[]) => listExercises(...(args as [])),
    listCourses: () => listCourses(),
    uploadMaterial: (...args: unknown[]) => uploadMaterial(...(args as [])),
    listFolders: (...args: unknown[]) => listFolders(...(args as [])),
    createFolder: (...args: unknown[]) => createFolder(...(args as [])),
  }
})

vi.mock('@/components/math/MathInput', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@/components/math/MathInput')>()
  return {
    ...actual,
    MathInput: ({
      value,
      onChange,
    }: {
      value: string
      onChange: (value: string) => void
    }) => (
      <input
        aria-label="Equation editor"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    ),
  }
})

vi.mock('@/lib/ws-client', () => ({
  getWsClient: () => ({
    subscribe: vi.fn(() => () => undefined),
  }),
}))

function renderPanel(sessionId: number | null, session: ChatSession = SESSION) {
  baseMocks(session)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const rootRoute = createRootRoute()
  const route = createRoute({
    getParentRoute: () => rootRoute,
    path: '/',
    component: () => (
      <QueryClientProvider client={client}>
        <ChatPanel sessionId={sessionId} onSessionCreated={() => undefined} />
      </QueryClientProvider>
    ),
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([route]),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  })
  return render(<RouterProvider router={router} />)
}

const SESSION: ChatSession = {
  id: 4,
  public_id: 'uuid-4',
  course_id: 7,
  node_id: null,
  title: 'New chat',
  use_embeddings: null,
  created_at: new Date().toISOString(),
}

const COURSELESS_SESSION: ChatSession = { ...SESSION, course_id: null }

function baseMocks(session: ChatSession = SESSION) {
  listChatSessions.mockResolvedValue([session])
  listChatMessages.mockResolvedValue([])
  getChatContext.mockResolvedValue({
    session_id: session.id,
    course_id: session.course_id,
    node: null,
    registry: [],
    latest_notes: [],
  })
}

describe('ChatPanel composer extras (plan 40C)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    baseMocks()
    listFolders.mockResolvedValue([
      { id: 55, name: 'Chat uploads', course_id: 7, parent_id: null },
    ])
    listMaterials.mockResolvedValue([])
    createFolder.mockImplementation(
      async (name: string, parentId: number | null, courseId: number) => ({
        id: 500 + createFolder.mock.calls.length,
        name,
        path: name,
        course_id: courseId,
        parent_id: parentId,
        source_id: null,
        created_at: new Date().toISOString(),
      }),
    )
    uploadMaterial.mockResolvedValue({
      material: { id: 77, title: 'drawing.png', kind: 'image' },
    })
  })

  test('equation dialog inserts inline latex at the cursor into the draft', async () => {
    renderPanel(4)
    fireEvent.click(await screen.findByRole('button', { name: 'Attach an item' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Insert equation…' }))
    const field = await screen.findByRole('textbox', { name: 'Equation editor' })
    fireEvent.change(field, { target: { value: '\\int_0^1 x^2 dx' } })
    fireEvent.click(screen.getByRole('button', { name: 'Insert' }))
    const composer = screen.getByPlaceholderText(
      'Ask about your material…',
    ) as HTMLTextAreaElement
    expect(composer.value).toBe('$\\int_0^1 x^2 dx$')
  })

  test('draw dialog attaches a material chip via the chat uploads folder', async () => {
    vi.mock('@/components/canvas/DrawCanvas', () => ({
      DrawCanvas: ({ onChange }: { onChange: (strokes: unknown[]) => void }) => (
        <button type="button" onClick={() => onChange([{ points: [[0, 0]] }])}>
          add-stroke
        </button>
      ),
      strokesToPng: () =>
        'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
    }))
    renderPanel(4)
    fireEvent.click(await screen.findByRole('button', { name: 'Attach an item' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Open drawing canvas…' }))
    const saveButton = await screen.findByRole('button', { name: 'Attach drawing' })
    expect(saveButton).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'add-stroke' }))
    expect(saveButton).not.toBeDisabled()
    fireEvent.click(saveButton)
    await waitFor(() => {
      expect(uploadMaterial).toHaveBeenCalledWith(
        expect.any(File),
        7,
        501,
      )
    })
    const sent = uploadMaterial.mock.calls[0][0] as File
    expect(sent.name).toBe('Drawing 1.png')
    expect(createFolder).toHaveBeenCalledWith('New chat (#4)', 55, 7)
  })

  test('draw uploads enumerate per conversation folder', async () => {
    listMaterials.mockResolvedValue([
      { id: 1, title: 'Drawing 1.png' },
      { id: 2, title: 'Drawing 3.png' },
    ])
    uploadMaterial.mockResolvedValue({
      material: { id: 77, title: 'Drawing 4.png', kind: 'image' },
    })
    renderPanel(4)
    fireEvent.click(await screen.findByRole('button', { name: 'Attach an item' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Open drawing canvas…' }))
    fireEvent.click(await screen.findByRole('button', { name: 'add-stroke' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Attach drawing' }))
    await waitFor(() => expect(uploadMaterial).toHaveBeenCalled())
    const sent = uploadMaterial.mock.calls[0][0] as File
    expect(sent.name).toBe('Drawing 4.png')
    expect(listMaterials).toHaveBeenCalledWith(501, 7)
  })

  test('course-less session falls back to the Unsorted course for drawing uploads', async () => {
    listCourses.mockResolvedValue([
      {
        id: 9,
        title: 'Unsorted',
        subject: null,
        level: null,
        description: null,
        color: null,
        archived_at: null,
        material_count: 0,
      },
      {
        id: 11,
        title: 'Calculus',
        subject: null,
        level: null,
        description: null,
        color: null,
        archived_at: null,
        material_count: 2,
      },
    ])
    listFolders.mockResolvedValue([{ id: 65, name: 'Chat uploads', course_id: 9, parent_id: null }])
    uploadMaterial.mockResolvedValue({
      material: { id: 88, title: 'drawing.png', kind: 'image' },
    })
    renderPanel(4, COURSELESS_SESSION)
    fireEvent.click(await screen.findByRole('button', { name: 'Attach an item' }))
    expect(await screen.findByRole('button', { name: 'Open drawing canvas…' }))
    expect(screen.getByRole('button', { name: 'Capture screenshot…' }))
    fireEvent.click(screen.getByRole('button', { name: 'Open drawing canvas…' }))
    const saveButton = await screen.findByRole('button', { name: 'Attach drawing' })
    expect(screen.getByText(/files into the Unsorted library/))
    fireEvent.click(screen.getByRole('button', { name: 'add-stroke' }))
    fireEvent.click(saveButton)
    await waitFor(() => expect(uploadMaterial).toHaveBeenCalled())
    expect(uploadMaterial.mock.calls[0][1]).toBe(9)
    expect(uploadMaterial.mock.calls[0][2]).toBe(501)
    expect(createFolder).toHaveBeenCalledWith('New chat (#4)', 65, 9)
  })

  test('course-less session without a resolvable course hides drawing, screenshot and upload', async () => {
    listCourses.mockResolvedValue([
      {
        id: 11,
        title: 'Calculus',
        subject: null,
        level: null,
        description: null,
        color: null,
        archived_at: null,
        material_count: 0,
      },
      {
        id: 12,
        title: 'Algebra',
        subject: null,
        level: null,
        description: null,
        color: null,
        archived_at: null,
        material_count: 0,
      },
    ])
    renderPanel(4, COURSELESS_SESSION)
    fireEvent.click(await screen.findByRole('button', { name: 'Attach an item' }))
    expect(await screen.findByRole('button', { name: 'Insert equation…' }))
    expect(screen.queryByRole('button', { name: 'Open drawing canvas…' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Capture screenshot…' })).toBeNull()
    fireEvent.click(screen.getByRole('tab', { name: 'Upload a file' }))
    expect(await screen.findByText('Uploads need a course — create one first, then try again.'))
  })

  test('screenshot dialog shows a graceful error when capture is unsupported', async () => {
    const original = navigator.mediaDevices
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {},
    })
    try {
      renderPanel(4)
      fireEvent.click(await screen.findByRole('button', { name: 'Attach an item' }))
      fireEvent.click(
        await screen.findByRole('button', { name: 'Capture screenshot…' }),
      )
      await screen.findByRole('alert')
      expect(screen.getByRole('alert').textContent).toContain(
        'Screen capture is unavailable here',
      )
    } finally {
      Object.defineProperty(navigator, 'mediaDevices', {
        configurable: true,
        value: original,
      })
    }
  })
})
