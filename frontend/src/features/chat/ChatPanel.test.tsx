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
const createChatSession = vi.fn()
const listChatMessages = vi.fn()
const sendChatMessage = vi.fn()
const patchChatMessageState = vi.fn()
const listAiTools = vi.fn()
const getChatContext = vi.fn()
const listMaterials = vi.fn()
const listNotes = vi.fn()
const listQuizzes = vi.fn()
const listExercises = vi.fn()
const listCourses = vi.fn()
const uploadMaterial = vi.fn()
const listFolders = vi.fn()
const createFolder = vi.fn()
const renameChatSession = vi.fn()
const deleteChatSession = vi.fn()
const editChatMessage = vi.fn()
const regenerateChatMessage = vi.fn()
const selectChatVariant = vi.fn()
const stopChatTurn = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listChatSessions: () => listChatSessions(),
    createChatSession: (...args: unknown[]) => createChatSession(...(args as [])),
    listChatMessages: (...args: unknown[]) => listChatMessages(...(args as [number])),
    sendChatMessage: (...args: unknown[]) =>
      sendChatMessage(...(args as [number, string, unknown[] | undefined])),
    patchChatMessageState: (...args: unknown[]) =>
      patchChatMessageState(...(args as [number, unknown[]])),
    listAiTools: () => listAiTools(),
    getChatContext: (...args: unknown[]) => getChatContext(...(args as [number])),
    listMaterials: (...args: unknown[]) => listMaterials(...(args as [])),
    listNotes: (...args: unknown[]) => listNotes(...(args as [])),
    listQuizzes: (...args: unknown[]) => listQuizzes(...(args as [])),
    listExercises: (...args: unknown[]) => listExercises(...(args as [])),
    listCourses: () => listCourses(),
    uploadMaterial: (...args: unknown[]) => uploadMaterial(...(args as [])),
    listFolders: (...args: unknown[]) => listFolders(...(args as [])),
    createFolder: (...args: unknown[]) => createFolder(...(args as [])),
    renameChatSession: (...args: unknown[]) =>
      renameChatSession(...(args as [number, string])),
    deleteChatSession: (id: number) => deleteChatSession(id),
    editChatMessage: (...args: unknown[]) =>
      editChatMessage(...(args as [number, string])),
    regenerateChatMessage: (...args: unknown[]) =>
      regenerateChatMessage(...(args as [number])),
    selectChatVariant: (...args: unknown[]) =>
      selectChatVariant(...(args as [number])),
    stopChatTurn: (...args: unknown[]) => stopChatTurn(...(args as [number])),
  }
})

vi.mock('@/lib/ws-client', () => ({
  getWsClient: () => ({
    subscribe: vi.fn(() => () => undefined),
  }),
}))

function renderPanel(
  props: {
    sessionId?: number | null
    onSessionCreated?: (session: ChatSession) => void
    variant?: 'sidebar' | 'page'
    onExpand?: () => void
    onCollapse?: () => void
  } = {},
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const rootRoute = createRootRoute()
  const routes = [
    createRoute({
      getParentRoute: () => rootRoute,
      path: '/',
      component: () => (
        <QueryClientProvider client={client}>
          <ChatPanel
            sessionId={props.sessionId ?? null}
            onSessionCreated={props.onSessionCreated ?? (() => undefined)}
            onClose={() => undefined}
            variant={props.variant}
            onExpand={props.onExpand}
            onCollapse={props.onCollapse}
          />
        </QueryClientProvider>
      ),
    }),
    createRoute({
      getParentRoute: () => rootRoute,
      path: '/library/$materialId',
      component: () => null,
    }),
    createRoute({
      getParentRoute: () => rootRoute,
      path: '/note/$noteId',
      component: () => null,
    }),
    createRoute({
      getParentRoute: () => rootRoute,
      path: '/courses/$courseId',
      component: () => null,
    }),
    createRoute({
      getParentRoute: () => rootRoute,
      path: '/courses/$courseId/n/$nodeId',
      component: () => null,
    }),
    createRoute({
      getParentRoute: () => rootRoute,
      path: '/quiz/$activityId',
      component: () => null,
    }),
    createRoute({
      getParentRoute: () => rootRoute,
      path: '/exercises/$exerciseId',
      component: () => null,
    }),
  ]
  const router = createRouter({
    routeTree: rootRoute.addChildren(routes),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  })
  return render(<RouterProvider router={router} />)
}

const SESSION = { id: 4, public_id: 'uuid-4', course_id: null, title: 'New chat', created_at: new Date().toISOString() }

const ASSISTANT = {
  id: 2,
  role: 'assistant',
  markdown: 'The rule is $f(x)$ [1]',
  citations: [
    {
      index: 1,
      chunk_id: 9,
      material_id: 3,
      title: 'rules.txt',
      quote: 'the quoted source text',
    },
  ],
  grounded: true,
}

describe('ChatPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  test('new-chat mode sends without a pre-created session', async () => {
    listChatSessions.mockResolvedValue([])
    createChatSession.mockResolvedValue({
      id: 99,
      course_id: null,
      title: 'what is the rule?',
    })
    sendChatMessage.mockResolvedValue({
      user_message: {
        id: 1,
        role: 'user',
        markdown: 'what is the rule?',
        citations: [],
        grounded: null,
      },
      job_id: 12,
    })
    listChatMessages.mockResolvedValue([])
    getChatContext.mockResolvedValue({
      session_id: 99,
      course_id: null,
      node: null,
      registry: [],
      latest_notes: [],
    })
    renderPanel()
    expect(await screen.findByText('Quiz me on what we discussed')).toBeInTheDocument()
    const input = (await screen.findByPlaceholderText(
      'Ask about your material…',
    )) as HTMLTextAreaElement
    expect(input.disabled).toBe(false)
    fireEvent.change(input, { target: { value: 'what is the rule?' } })
    fireEvent.submit(input.closest('form')!)
    await waitFor(() =>
      expect(createChatSession).toHaveBeenCalledWith(null, undefined, 'what is the rule?'),
    )
    await waitFor(() =>
      expect(sendChatMessage).toHaveBeenCalledWith(99, 'what is the rule?', []),
    )
    await waitFor(() => expect(input.value).toBe(''))
  })

  test('new-chat mode reports the created session back to the host', async () => {
    listChatSessions.mockResolvedValue([])
    createChatSession.mockResolvedValue({
      id: 99,
      public_id: 'uuid-99',
      course_id: null,
      title: 'what is the rule?',
    })
    sendChatMessage.mockResolvedValue({
      user_message: {
        id: 1,
        role: 'user',
        markdown: 'what is the rule?',
        citations: [],
        grounded: null,
      },
      job_id: 12,
    })
    listChatMessages.mockResolvedValue([])
    getChatContext.mockResolvedValue({
      session_id: 99,
      course_id: null,
      node: null,
      registry: [],
      latest_notes: [],
    })
    const onSessionCreated = vi.fn()
    renderPanel({ onSessionCreated })
    const input = (await screen.findByPlaceholderText(
      'Ask about your material…',
    )) as HTMLTextAreaElement
    fireEvent.change(input, { target: { value: 'what is the rule?' } })
    fireEvent.submit(input.closest('form')!)
    await waitFor(() =>
      expect(onSessionCreated).toHaveBeenCalledWith(
        expect.objectContaining({ id: 99, public_id: 'uuid-99' }),
      ),
    )
  })

  test('renders conversation citations after picking a session', async () => {
    listChatSessions.mockResolvedValue([SESSION])
    listChatMessages.mockResolvedValue([
      { id: 1, role: 'user', markdown: 'what is the rule?', citations: [], grounded: null },
      ASSISTANT,
    ])
    renderPanel({ sessionId: 4 })
    await screen.findByText('what is the rule?')
    expect(await screen.findByText(/\[1\] rules\.txt/)).toBeInTheDocument()
  })

  test('shows not-grounded marker when ungrounded', async () => {
    listChatSessions.mockResolvedValue([SESSION])
    listChatMessages.mockResolvedValue([
      {
        id: 3,
        role: 'assistant',
        markdown: 'ungrounded claim',
        citations: [],
        grounded: false,
      },
    ])
    renderPanel({ sessionId: 4 })
    expect(await screen.findByText('Not grounded in your material')).toBeInTheDocument()
  })

  test('renders assistant mentions as clickable chips', async () => {
    listChatSessions.mockResolvedValue([SESSION])
    getChatContext.mockResolvedValue({
      session_id: 4,
      course_id: 1,
      node: { id: 9, title: 'Techniques' },
      registry: [
        { ref: 'M12', kind: 'material', id: 12, title: 'Lecture 3', course_id: 1 },
      ],
      latest_notes: [{ id: 5, title: 'Latest note' }],
    })
    listChatMessages.mockResolvedValue([
      {
        id: 5,
        role: 'assistant',
        markdown: 'Study [M12] and [N3] first.',
        citations: [],
        mentions: [
          { ref: 'M12', kind: 'material', id: 12, title: 'Lecture 3', course_id: 1 },
          { ref: 'N3', kind: 'note', id: 3, title: 'Chain rule note', course_id: 1 },
        ],
        grounded: null,
      },
    ])
    renderPanel({ sessionId: 4 })
    expect(await screen.findByText('Lecture 3')).toBeInTheDocument()
    expect(screen.getByText('Chain rule note')).toBeInTheDocument()
  })

  test('renders persisted tool calls as collapsible cards', async () => {
    listChatSessions.mockResolvedValue([SESSION])
    getChatContext.mockResolvedValue({
      session_id: 4,
      course_id: null,
      node: null,
      registry: [],
      latest_notes: [],
    })
    listChatMessages.mockResolvedValue([
      {
        id: 7,
        role: 'assistant',
        markdown: 'The derivative is $3x^2$.',
        citations: [],
        mentions: [],
        reads: [],
        tool_calls: [
          { name: 'SYMPY', argument: 'diff x**3', phase: 'math', result: '3*x**2' },
        ],
        grounded: null,
      },
    ])
    renderPanel({ sessionId: 4 })
    const toggle = await screen.findByRole('button', {
      name: 'Show details for Symbolic math',
    })
    expect(toggle).toHaveTextContent('SYMPY')
    expect(toggle).toHaveTextContent('diff x**3')
    fireEvent.click(toggle)
    expect(await screen.findByText('Argument')).toBeInTheDocument()
    expect(screen.getByText('= 3*x**2')).toBeInTheDocument()
  })

  test('context panel shows what the AI sees and read indicators', async () => {
    listChatSessions.mockResolvedValue([SESSION])
    getChatContext.mockResolvedValue({
      session_id: 4,
      course_id: 1,
      node: { id: 9, title: 'Techniques' },
      registry: [
        { ref: 'M12', kind: 'material', id: 12, title: 'Lecture 3', course_id: 1 },
      ],
      latest_notes: [{ id: 5, title: 'Latest note' }],
    })
    listChatMessages.mockResolvedValue([
      {
        id: 6,
        role: 'assistant',
        markdown: 'Based on full reading.',
        citations: [],
        mentions: [],
        reads: [
          {
            ref: 'M12',
            kind: 'material',
            id: 12,
            title: 'Lecture 3',
            course_id: 1,
            chars: 3200,
          },
        ],
        grounded: null,
      },
    ])
    renderPanel({ sessionId: 4 })
    expect(await screen.findAllByText('Lecture 3')).not.toHaveLength(0)
    const toggle = screen.getByRole('button', { name: /what the AI sees/i })
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    fireEvent.click(toggle)
    expect(await screen.findByText('Techniques')).toBeInTheDocument()
    expect(screen.getByText('Latest note')).toBeInTheDocument()
    expect(screen.getAllByText('Lecture 3').length).toBeGreaterThanOrEqual(2)
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
  })

  test('send posts the drafted message', async () => {
    listChatSessions.mockResolvedValue([SESSION])
    listChatMessages.mockResolvedValue([])
    sendChatMessage.mockResolvedValue({
      user_message: { id: 9, role: 'user', markdown: 'hi', citations: [], grounded: null },
      job_id: 12,
    })
    renderPanel({ sessionId: 4 })
    const input = await screen.findByPlaceholderText('Ask about your material…')
    fireEvent.change(input, { target: { value: 'chain rule?' } })
    fireEvent.submit(input.closest('form')!)
    await waitFor(() =>
      expect(sendChatMessage).toHaveBeenCalledWith(4, 'chain rule?', []),
    )
  })

  test('renders user messages as markdown with math', async () => {
    listChatSessions.mockResolvedValue([SESSION])
    getChatContext.mockResolvedValue({
      session_id: 4,
      course_id: null,
      node: null,
      registry: [],
      latest_notes: [],
    })
    listChatMessages.mockResolvedValue([
      {
        id: 11,
        role: 'user',
        markdown: 'What is $\\frac{1}{2}$ and **bold**?',
        citations: [],
        grounded: null,
      },
    ])
    renderPanel({ sessionId: 4 })
    await waitFor(() => {
      expect(screen.getByText('bold', { exact: false }).closest('strong')).not.toBeNull()
    })
    expect(document.querySelector('.katex')).not.toBeNull()
  })

  test('renders attachments on user messages as chips', async () => {
    listChatSessions.mockResolvedValue([SESSION])
    getChatContext.mockResolvedValue({
      session_id: 4,
      course_id: 1,
      node: null,
      registry: [],
      latest_notes: [],
    })
    listChatMessages.mockResolvedValue([
      {
        id: 8,
        role: 'user',
        markdown: 'review this',
        citations: [],
        grounded: null,
        mentions: [
          { ref: 'M12', kind: 'material', id: 12, title: 'Lecture 3', course_id: 1 },
        ],
      },
    ])
    renderPanel({ sessionId: 4 })
    expect(await screen.findByText('review this')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Open Material: Lecture 3/ })).toBeInTheDocument()
  })

  test('plus button attaches a note and sends it with the message', async () => {
    listChatSessions.mockResolvedValue([SESSION])
    getChatContext.mockResolvedValue({
      session_id: 4,
      course_id: 1,
      node: null,
      registry: [],
      latest_notes: [],
    })
    listMaterials.mockResolvedValue([])
    listNotes.mockResolvedValue({
      items: [{ id: 7, title: 'Chain rule note', tags: ['calculus'] }],
      next_cursor: null,
    })
    sendChatMessage.mockResolvedValue({
      user_message: {
        id: 10,
        role: 'user',
        markdown: 'use my note',
        citations: [],
        grounded: null,
        mentions: [
          { ref: 'N7', kind: 'note', id: 7, title: 'Chain rule note', course_id: 1 },
        ],
      },
      job_id: 14,
    })
    listChatMessages.mockResolvedValue([])
    renderPanel({ sessionId: 4 })
    fireEvent.click(await screen.findByRole('button', { name: 'Attach an item' }))
    fireEvent.click(await screen.findByTitle('Notes'))
    fireEvent.click(await screen.findByText('Chain rule note'))
    expect(
      await screen.findByRole('button', { name: 'Remove Chain rule note' }),
    ).toBeInTheDocument()
    const input = await screen.findByPlaceholderText('Ask about your material…')
    fireEvent.change(input, { target: { value: 'use my note' } })
    fireEvent.submit(input.closest('form')!)
    await waitFor(() =>
      expect(sendChatMessage).toHaveBeenCalledWith(4, 'use my note', [
        { kind: 'note', id: 7 },
      ]),
    )
  })

  test('upload tab uploads to the chat uploads folder and attaches the material', async () => {
    listChatSessions.mockResolvedValue([SESSION])
    getChatContext.mockResolvedValue({
      session_id: 4,
      course_id: 1,
      node: null,
      registry: [],
      latest_notes: [],
    })
    listFolders.mockResolvedValue([
      { id: 3, name: 'Chat uploads', course_id: 1, parent_id: null },
    ])
    createFolder.mockResolvedValue({
      id: 33,
      name: 'New chat (#4)',
      path: 'New chat (#4)',
      course_id: 1,
      parent_id: 3,
      source_id: null,
      created_at: new Date().toISOString(),
    })
    uploadMaterial.mockResolvedValue({
      material: { id: 21, title: 'scan.pdf', kind: 'pdf', status: 'pending' },
      job_id: 30,
      deduped: false,
    })
    listChatMessages.mockResolvedValue([])
    renderPanel({ sessionId: 4 })
    fireEvent.click(await screen.findByRole('button', { name: 'Attach an item' }))
    fireEvent.click(await screen.findByTitle('Upload a file'))
    const fileInput = await screen.findByLabelText('Choose a file')
    fireEvent.change(fileInput, {
      target: { files: [new File(['data'], 'scan.pdf', { type: 'application/pdf' })] },
    })
    await waitFor(() => expect(uploadMaterial).toHaveBeenCalled())
    expect(uploadMaterial.mock.calls[0][1]).toBe(1)
    expect(uploadMaterial.mock.calls[0][2]).toBe(33)
    expect(createFolder).toHaveBeenCalledWith('New chat (#4)', 3, 1)
    expect(
      await screen.findByRole('button', { name: 'Remove scan.pdf' }),
    ).toBeInTheDocument()
  })

  test('empty conversation shows suggestions that fill the draft', async () => {
    listChatSessions.mockResolvedValue([SESSION])
    getChatContext.mockResolvedValue({
      session_id: 4,
      course_id: null,
      node: null,
      registry: [],
      latest_notes: [],
    })
    listChatMessages.mockResolvedValue([])
    renderPanel({ sessionId: 4 })
    const suggestion = await screen.findByText('Quiz me on what we discussed')
    fireEvent.click(suggestion)
    const input = screen.getByPlaceholderText(
      'Ask about your material…',
    ) as HTMLTextAreaElement
    expect(input.value).toBe('Quiz me on what we discussed')
  })

  test('tools button opens the tool catalog with only chat tools', async () => {
    listChatSessions.mockResolvedValue([])
    listChatMessages.mockResolvedValue([])
    listAiTools.mockResolvedValue([
      {
        name: 'CALC',
        description: 'Numeric evaluation of an arithmetic expression.',
        example: 'CALC sin(pi/6)',
        arguments: [
          { name: 'expression', type: 'string', required: true, description: null },
        ],
        response: 'The evaluated number, or an error line.',
        scope: 'Chat answers.',
      },
      {
        name: 'COURSES',
        description: 'List the learner’s courses.',
        example: 'COURSES',
        arguments: [],
        response: 'JSON object with the requested rows.',
        scope: 'Read-only — lists the learner’s data.',
      },
    ])
    renderPanel()
    fireEvent.click(await screen.findByTitle('Available tools'))
    expect(await screen.findByText('CALC')).toBeInTheDocument()
    expect(screen.getAllByText('COURSES').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Arguments').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Response').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Scope').length).toBeGreaterThan(0)
    expect(screen.queryByText(/MCP resource tools/i)).not.toBeInTheDocument()
  })

  test('renders widget blocks and patches their state', async () => {
    listChatSessions.mockResolvedValue([SESSION])
    getChatContext.mockResolvedValue({
      session_id: 4,
      course_id: null,
      node: null,
      registry: [],
      latest_notes: [],
    })
    listChatMessages.mockResolvedValue([
      {
        id: 30,
        role: 'assistant',
        markdown: 'Which rule did you use?',
        blocks: [
          { type: 'text', md: 'Which rule did you use?' },
          {
            type: 'widget',
            widget: 'checklist',
            id: 'w1',
            props: { prompt: 'Select all that apply', items: ['factor', 'chain rule'] },
          },
        ],
        citations: [],
        grounded: null,
      },
    ])
    patchChatMessageState.mockResolvedValue({ state: { w1: { checked: ['factor'] } } })
    renderPanel({ sessionId: 4 })
    expect(await screen.findByText('Select all that apply')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('factor'))
    await waitFor(() =>
      expect(patchChatMessageState).toHaveBeenCalledWith(30, [
        { op: 'add', path: '/checked', value: ['factor'] },
      ]),
    )
  })

  test('sidebar shows expand and close actions with a resize handle', async () => {
    listChatSessions.mockResolvedValue([])
    listChatMessages.mockResolvedValue([])
    renderPanel()
    expect(await screen.findByTitle('Open in full page')).toBeInTheDocument()
    expect(screen.getByTitle('Close chat')).toBeInTheDocument()
    expect(screen.getByRole('separator', { name: 'Resize chat width' })).toBeInTheDocument()
  })

  test('page variant shows collapse and hides close and resize', async () => {
    listChatSessions.mockResolvedValue([])
    listChatMessages.mockResolvedValue([])
    renderPanel({ variant: 'page', onCollapse: () => undefined })
    expect(await screen.findByTitle('Back to sidebar')).toBeInTheDocument()
    expect(screen.queryByTitle('Close chat')).not.toBeInTheDocument()
    expect(screen.queryByRole('separator', { name: 'Resize chat width' })).not.toBeInTheDocument()
  })

  test('expand action calls onExpand', async () => {
    listChatSessions.mockResolvedValue([])
    listChatMessages.mockResolvedValue([])
    const onExpand = vi.fn()
    renderPanel({ onExpand })
    fireEvent.click(await screen.findByTitle('Open in full page'))
    expect(onExpand).toHaveBeenCalledTimes(1)
  })

  test('dragging the resize handle changes the panel width', async () => {
    listChatSessions.mockResolvedValue([])
    listChatMessages.mockResolvedValue([])
    renderPanel()
    const handle = await screen.findByRole('separator', { name: 'Resize chat width' })
    fireEvent.pointerDown(handle, { clientX: 384, pointerId: 1 })
    fireEvent.pointerMove(handle, { clientX: 300, pointerId: 1 })
    const aside = handle.closest('aside')
    expect(aside).not.toBeNull()
    expect(aside?.style.width).toBe('468px')
  })
})

describe('ChatPanel message actions (plan 40B)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  function baseMocks() {
    listChatSessions.mockResolvedValue([SESSION])
    getChatContext.mockResolvedValue({
      session_id: 4,
      course_id: null,
      node: null,
      registry: [],
      latest_notes: [],
    })
  }

  function userMessage(overrides: Record<string, unknown> = {}) {
    return {
      id: 1,
      role: 'user',
      markdown: 'first question',
      citations: [],
      mentions: [],
      reads: [],
      tool_calls: [],
      proposals: [],
      grounded: null,
      parent_id: null,
      variant_index: 1,
      variant_count: 1,
      sibling_ids: [1],
      ...overrides,
    }
  }

  test('copy button writes the markdown to the clipboard', async () => {
    baseMocks()
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    listChatMessages.mockResolvedValue([
      userMessage(),
      {
        id: 2,
        role: 'assistant',
        markdown: 'Answer one',
        citations: [],
        mentions: [],
        reads: [],
        tool_calls: [],
        proposals: [],
        grounded: true,
        parent_id: 1,
      },
    ])
    renderPanel({ sessionId: 4 })
    await screen.findByText('first question')
    fireEvent.click(screen.getAllByTitle('Copy message')[0])
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('first question'))
    expect(await screen.findByTitle('Copied')).toBeInTheDocument()
  })

  test('edit mode resends through the branch endpoint', async () => {
    baseMocks()
    listChatMessages.mockResolvedValue([userMessage()])
    editChatMessage.mockResolvedValue({
      user_message: userMessage({ markdown: 'edited question' }),
      job_id: 7,
    })
    renderPanel({ sessionId: 4 })
    await screen.findByText('first question')
    fireEvent.click(screen.getByTitle('Edit message'))
    const box = screen.getByRole('textbox', { name: 'Edit message' }) as HTMLTextAreaElement
    expect(box.value).toBe('first question')
    fireEvent.change(box, { target: { value: 'edited question' } })
    fireEvent.click(screen.getByTitle('Save & resend'))
    await waitFor(() => expect(editChatMessage).toHaveBeenCalledWith(1, 'edited question'))
  })

  test('retry regenerates from the assistant parent question', async () => {
    baseMocks()
    listChatMessages.mockResolvedValue([
      userMessage(),
      {
        id: 2,
        role: 'assistant',
        markdown: 'Answer one',
        citations: [],
        mentions: [],
        reads: [],
        tool_calls: [],
        proposals: [],
        grounded: true,
        parent_id: 1,
      },
    ])
    regenerateChatMessage.mockResolvedValue({
      user_message: userMessage(),
      job_id: 8,
    })
    renderPanel({ sessionId: 4 })
    await screen.findByText('Answer one')
    fireEvent.click(screen.getByTitle('Regenerate answer'))
    await waitFor(() => expect(regenerateChatMessage).toHaveBeenCalledWith(1))
  })

  test('variant switcher selects the sibling variant', async () => {
    baseMocks()
    listChatMessages.mockResolvedValue([
      userMessage({
        variant_index: 2,
        variant_count: 2,
        sibling_ids: [9, 1],
      }),
      {
        id: 2,
        role: 'assistant',
        markdown: 'Answer two',
        citations: [],
        mentions: [],
        reads: [],
        tool_calls: [],
        proposals: [],
        grounded: true,
        parent_id: 1,
      },
    ])
    selectChatVariant.mockResolvedValue([])
    renderPanel({ sessionId: 4 })
    await screen.findByText(/2\/2/)
    fireEvent.click(screen.getByTitle('Previous variant'))
    await waitFor(() => expect(selectChatVariant).toHaveBeenCalledWith(9))
    expect(screen.getByTitle('Next variant')).toBeInTheDocument()
  })

describe('ChatPanel stop button (plan 40D)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  test('shows a stop control while a turn is pending and calls the stop endpoint', async () => {
    listChatSessions.mockResolvedValue([SESSION])
    getChatContext.mockResolvedValue({
      session_id: 4,
      course_id: null,
      node: null,
      registry: [],
      latest_notes: [],
    })
    listChatMessages.mockResolvedValue([
      {
        id: 1,
        role: 'user',
        markdown: 'question',
        citations: [],
        mentions: [],
        reads: [],
        tool_calls: [],
        proposals: [],
        grounded: null,
      },
    ])
    sendChatMessage.mockResolvedValue({
      user_message: { id: 1, role: 'user', markdown: 'question' },
      job_id: 3,
    })
    stopChatTurn.mockResolvedValue({ stopped: true })
    renderPanel({ sessionId: 4 })
    const input = (await screen.findByPlaceholderText(
      'Ask about your material…',
    )) as HTMLTextAreaElement
    fireEvent.change(input, { target: { value: 'question' } })
    fireEvent.submit(input.closest('form')!)
    const stop = await screen.findByRole('button', { name: 'Stop generating' })
    fireEvent.click(stop)
    await waitFor(() => expect(stopChatTurn).toHaveBeenCalledWith(4))
  })
})

})
