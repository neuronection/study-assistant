import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  redirect,
  RouterProvider,
} from '@tanstack/react-router'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { NodeWorkspace } from './NodeWorkspace'
import { useChatStore } from '@/lib/chat-store'
import { clearWindowDropTarget, getWindowDropTarget } from '@/lib/window-drop-store'

const nodeWorkspace = vi.fn()
const courseTree = vi.fn()
const listCourses = vi.fn()
const listNotes = vi.fn()
const listNoteTags = vi.fn()
const getNote = vi.fn()
const listMaterials = vi.fn()
const getMaterial = vi.fn()
const getMaterialLinks = vi.fn()
const listStudyStates = vi.fn()
const listQuizzes = vi.fn()
const listExercises = vi.fn()
const listFlashcards = vi.fn()
const dueFlashcards = vi.fn()
const reviewFlashcard = vi.fn()
const listChatSessions = vi.fn()
const generateQuiz = vi.fn()
const generateFlashcards = vi.fn()
const createChatSession = vi.fn()
const createNote = vi.fn()
const addNodeConcept = vi.fn()
const removeNodeConcept = vi.fn()
const conceptGraph = vi.fn()
const extractConcepts = vi.fn()
const commitConcepts = vi.fn()
const updateNode = vi.fn()
const updateCourse = vi.fn()
const addNode = vi.fn()
const outlineDraft = vi.fn()
const outlineCommit = vi.fn()
const draftNodeNote = vi.fn()
const getNodeArtifacts = vi.fn()
const similarExercise = vi.fn()
const drillPatterns = vi.fn()
const updateNote = vi.fn()
const deleteNote = vi.fn()
const moveNote = vi.fn()
const moveQuiz = vi.fn()
const moveExercise = vi.fn()
const renameQuiz = vi.fn()
const deleteQuiz = vi.fn()
const renameExercise = vi.fn()
const deleteExercise = vi.fn()
const deallocateMaterial = vi.fn()
const deallocateNodeFolder = vi.fn()
const uploadMaterial = vi.fn()
const allocateMaterial = vi.fn()
const allocateNodeFolder = vi.fn()
const listFolders = vi.fn()
const createFolder = vi.fn()
const createTextMaterial = vi.fn()
const updateTextMaterial = vi.fn()
const previewAiContext = vi.fn()
const composeMaterial = vi.fn()
const listCourseTasks = vi.fn()
const assignCourseTask = vi.fn()
const listCourseTaskDefaults = vi.fn()
const assignCourseTaskDefault = vi.fn()
const listModels = vi.fn()

interface NavigateCall {
  to: string
  params?: Record<string, string>
  search?: unknown
}

function buildRouter(initialUrl: string) {
  const rootRoute = createRootRoute()
  const courseRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/courses/$courseId',
    validateSearch: (search: Record<string, unknown>): { tab?: string; note?: number } => ({
      tab: typeof search.tab === 'string' ? search.tab : undefined,
      note: typeof search.note === 'number' ? search.note : undefined,
    }),
    component: () => <NodeWorkspace courseId="3" />,
  })
  const nodeRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/courses/$courseId/n/$nodeId',
    validateSearch: (search: Record<string, unknown>): { tab?: string; note?: number } => ({
      tab: typeof search.tab === 'string' ? search.tab : undefined,
      note: typeof search.note === 'number' ? search.note : undefined,
    }),
    component: () => <NodeWorkspace courseId="3" nodeId="5" />,
  })
  const redirectRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/courses/$courseId/chapters/$chapterId',
    beforeLoad: ({ params }: { params: { courseId: string; chapterId: string } }) => {
      throw redirect({
        to: '/courses/$courseId/n/$nodeId',
        params: { courseId: params.courseId, nodeId: params.chapterId },
        replace: true,
      })
    },
  })
  const chatDetailRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/chat/$chatId',
    component: () => <div>chat-detail</div>,
  })
  return createRouter({
    routeTree: rootRoute.addChildren([courseRoute, nodeRoute, redirectRoute, chatDetailRoute]),
    history: createMemoryHistory({ initialEntries: [initialUrl] }),
  })
}

type WorkspaceRouter = ReturnType<typeof buildRouter>

const routerHolder: { current: WorkspaceRouter | null } = { current: null }
const navigateMock = vi.fn((options: NavigateCall) => {
  if (routerHolder.current !== null) {
    void routerHolder.current
      .navigate(options as Parameters<WorkspaceRouter['navigate']>[0])
      .catch(() => undefined)
  }
})

vi.mock('@/components/editor/LazyMarkdownEditor', () => ({
  LazyMarkdownEditor: ({
    value,
    onChange,
    ariaLabel,
  }: {
    value: string
    onChange: (markdown: string) => void
    ariaLabel: string
  }) => (
    <input
      aria-label={ariaLabel}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  ),
}))

vi.mock('@/lib/api', async (importOriginal) => {  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    nodeWorkspace: (id: number) => nodeWorkspace(id),
    courseTree: (id: number) => courseTree(id),
    listCourses: () => listCourses(),
    listNotes: (...args: unknown[]) => listNotes(...(args as [])),
    listNoteTags: (...args: unknown[]) => listNoteTags(...(args as [])),
    getNote: (id: number) => getNote(id),
    listMaterials: (...args: unknown[]) => listMaterials(...(args as [])),
    getMaterial: (id: number) => getMaterial(id),
    getMaterialLinks: (id: number) => getMaterialLinks(id),
    listStudyStates: () => listStudyStates(),
    listQuizzes: (...args: unknown[]) => listQuizzes(...(args as [])),
    listExercises: (...args: unknown[]) => listExercises(...(args as [])),
    listFlashcards: (...args: unknown[]) => listFlashcards(...(args as [])),
    dueFlashcards: (...args: unknown[]) => dueFlashcards(...(args as [])),
    reviewFlashcard: (cardId: number, rating: number) => reviewFlashcard(cardId, rating),
    listChatSessions: (nodeId?: number) => listChatSessions(nodeId),
    generateQuiz: (body: unknown) => generateQuiz(body),
    generateFlashcards: (body: unknown) => generateFlashcards(body),
    createChatSession: (...args: unknown[]) =>
      createChatSession(...(args as [number | null, number | null, string])),
    createNote: (body: unknown) => createNote(body),
    addNodeConcept: (...args: unknown[]) => addNodeConcept(...(args as [number, number])),
    removeNodeConcept: (...args: unknown[]) => removeNodeConcept(...(args as [number, number])),
    conceptGraph: (id: number) => conceptGraph(id),
    extractConcepts: (id: number) => extractConcepts(id),
    commitConcepts: (...args: unknown[]) => commitConcepts(...(args as [])),
    updateNode: (...args: unknown[]) => updateNode(...(args as [number, object])),
    updateCourse: (...args: unknown[]) => updateCourse(...(args as [number, object])),
    addNode: (...args: unknown[]) => addNode(...(args as [number, number, string])),
    outlineDraft: (id: number) => outlineDraft(id),
    outlineCommit: (id: number, chapters: unknown) => outlineCommit(id, chapters),
    draftNodeNote: (id: number) => draftNodeNote(id),
    getNodeArtifacts: (id: number, kind?: string) => getNodeArtifacts(id, kind),
    similarExercise: (id: number) => similarExercise(id),
    drillPatterns: () => drillPatterns(),
    updateNote: (...args: unknown[]) => updateNote(...(args as [number, object])),
    deleteNote: (id: number) => deleteNote(id),
    moveNote: (id: number, nodeId: number | null) => moveNote(id, nodeId),
    moveQuiz: (id: number, nodeId: number | null) => moveQuiz(id, nodeId),
    moveExercise: (id: number, nodeId: number | null) => moveExercise(id, nodeId),
    renameQuiz: (...args: unknown[]) => renameQuiz(...(args as [number, string])),
    deleteQuiz: (id: number) => deleteQuiz(id),
    renameExercise: (...args: unknown[]) => renameExercise(...(args as [number, string])),
    deleteExercise: (id: number) => deleteExercise(id),
    deallocateMaterial: (...args: unknown[]) => deallocateMaterial(...(args as [number, number])),
    deallocateNodeFolder: (...args: unknown[]) =>
      deallocateNodeFolder(...(args as [number, number])),
    uploadMaterial: (...args: unknown[]) => uploadMaterial(...(args as [])),
    allocateMaterial: (...args: unknown[]) => allocateMaterial(...(args as [number, number])),
    allocateNodeFolder: (...args: unknown[]) =>
      allocateNodeFolder(...(args as [number, number])),
    listFolders: (...args: unknown[]) => listFolders(...(args as [number?])),
    createFolder: (...args: unknown[]) => createFolder(...(args as [string, number | null, number])),
    createTextMaterial: (...args: unknown[]) => createTextMaterial(...(args as [])),
    updateTextMaterial: (...args: unknown[]) => updateTextMaterial(...(args as [])),
    previewAiContext: (courseId: number, spec: unknown) => previewAiContext(courseId, spec),
    composeMaterial: (body: unknown) => composeMaterial(body),
    listCourseTasks: (courseId: number) => listCourseTasks(courseId),
    assignCourseTask: (...args: unknown[]) =>
      assignCourseTask(...(args as [number, string, number | null, number | null])),
    listCourseTaskDefaults: (courseId: number) => listCourseTaskDefaults(courseId),
    assignCourseTaskDefault: (...args: unknown[]) =>
      assignCourseTaskDefault(
        ...(args as [number, string, number | null, number | null])
      ),
    listModels: () => listModels(),
  }
})

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return {
    ...actual,
    useNavigate: () => navigateMock,
  }
})

const TREE = [
  {
    id: 1,
    title: 'Calculus I',
    summary: null,
    objectives: [],
    order_idx: 0,
    depth: 0,
    is_root: true,
    children: [
      {
        id: 5,
        title: 'Derivatives',
        summary: null,
        objectives: [],
        order_idx: 0,
        depth: 1,
        is_root: false,
        children: [
          {
            id: 11,
            title: 'Chain rule',
            summary: null,
            objectives: [],
            order_idx: 0,
            depth: 2,
            is_root: false,
            children: [],
            materials: [],
          },
        ],
        materials: [],
      },
    ],
    materials: [],
  },
]

const ROOT_WS = {
  node: {
    id: 1,
    course_id: 3,
    course_title: 'Calculus I',
    title: 'Calculus I',
    summary: 'The course root',
    objectives: [],
    depth: 0,
    is_root: true,
    parent_id: null,
    breadcrumb: [{ id: 1, title: 'Calculus I', depth: 0 }],
  },
  children: [
    { id: 5, title: 'Derivatives', depth: 1, order_idx: 0, objectives: [], summary: null },
  ],
  folders: [],
  materials: [],
  child_materials: { 5: [] },
  notes: [],
  counts: {
    notes: { direct: 0, with_children: 0 },
    quizzes: { direct: 0, with_children: 0 },
    exercises: { direct: 0, with_children: 0 },
    flashcards: { direct: 0, with_children: 0 },
    child_nodes: 1,
  },
  concepts: [],
}

const NODE_WS = {
  node: {
    id: 5,
    course_id: 3,
    course_title: 'Calculus I',
    title: 'Derivatives',
    summary: 'Rates of change',
    objectives: ['Compute derivatives'],
    depth: 1,
    is_root: false,
    parent_id: 1,
    breadcrumb: [
      { id: 1, title: 'Calculus I', depth: 0 },
      { id: 5, title: 'Derivatives', depth: 1 },
    ],
  },
  children: [
    {
      id: 11,
      title: 'Chain rule',
      depth: 2,
      order_idx: 0,
      objectives: ['Apply the chain rule'],
      summary: null,
    },
  ],
  folders: [],
  materials: [
    {
      material_id: 7,
      title: 'chain-rule.pdf',
      kind: 'pdf',
      status: 'ready',
      read_status: 'reading',
      progress: 0.5,
      rationale: null,
      auto_assigned: false,
      confidence: null,
      via_folder_id: null,
      via_folder_name: null,
    },
  ],
  child_materials: {
    11: [
      {
        material_id: 8,
        title: 'worked problems',
        kind: 'txt',
        status: 'ready',
        read_status: 'unread',
        progress: 0,
        rationale: null,
        auto_assigned: false,
        confidence: null,
        via_folder_id: null,
        via_folder_name: null,
      },
    ],
  },
  notes: [],
  counts: {
    notes: { direct: 0, with_children: 0 },
    quizzes: { direct: 0, with_children: 0 },
    exercises: { direct: 0, with_children: 0 },
    flashcards: { direct: 0, with_children: 0 },
    child_nodes: 1,
  },
  concepts: [
    { id: 71, name: 'chain rule', direct: true, node_ids: [5] },
    { id: 72, name: 'limits', direct: false, node_ids: [11] },
  ],
}

const DRAFT = {
  chapters: [
    {
      title: 'Limits',
      summary: 'Approaching values',
      sections: [
        { title: 'Continuity', objectives: [], material_ids: [4], rationale: null, confidence: 0.9 },
        { title: 'Asymptotes', objectives: [], material_ids: [], rationale: null, confidence: 0.8 },
      ],
    },
    {
      title: 'Derivatives',
      summary: null,
      sections: [],
    },
  ],
}

function renderWorkspace(initialUrl: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = buildRouter(initialUrl)
  routerHolder.current = router
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}

function primeDefaults() {
  nodeWorkspace.mockImplementation((id: number) =>
    Promise.resolve(id === 1 ? ROOT_WS : NODE_WS)
  )
  courseTree.mockResolvedValue(TREE)
  listFolders.mockResolvedValue([])
  createFolder.mockImplementation(async (name: string, parentId: number | null) => ({
    id: 900 + createFolder.mock.calls.length,
    name,
    path: name,
    course_id: 3,
    parent_id: parentId,
    source_id: null,
    created_at: '2026-08-21T00:00:00Z',
  }))
  listCourses.mockResolvedValue([
    {
      id: 3,
      title: 'Calculus I',
      subject: null,
      level: null,
      description: null,
      color: '#3366cc',
      archived_at: null,
      material_count: 1,
    },
  ])
  listNotes.mockResolvedValue({ items: [], next_cursor: null })
  getNodeArtifacts.mockResolvedValue({ cheat_sheet: null, reviews: [] })
  listNoteTags.mockResolvedValue([])
  getNote.mockImplementation((id: number) =>
    Promise.resolve({
      id,
      title: `Note detail ${id}`,
      course_id: 3,
      node_id: 5,
      owner_type: 'standalone',
      owner_id: null,
      tags: [],
      pinned: false,
      updated_at: '2026-08-19T00:00:00Z',
      body: [],
      drawings: [],
    })
  )
  listMaterials.mockResolvedValue([])
  getMaterial.mockImplementation((id: number) =>
    Promise.resolve({
      material: {
        id,
        title: 'chain-rule.pdf',
        kind: 'pdf',
        status: 'ready',
        course_id: 3,
        folder_id: null,
        created_at: '2026-08-19T00:00:00Z',
        provenance: null,
      },
    })
  )
  getMaterialLinks.mockResolvedValue([
    {
      node_id: 5,
      owner_title: 'Derivatives',
      rationale: null,
      breadcrumb: [
        { id: 1, title: 'Calculus I' },
        { id: 5, title: 'Derivatives' },
      ],
      is_course_level: false,
    },
  ])
  listStudyStates.mockResolvedValue({})
  listQuizzes.mockResolvedValue([])
  listExercises.mockResolvedValue([])
  listFlashcards.mockResolvedValue([])
  dueFlashcards.mockResolvedValue([])
  reviewFlashcard.mockResolvedValue({ interval_days: 3, due_at: '2026-09-01T10:00:00Z', state: 'review' })
  listChatSessions.mockResolvedValue([])
  conceptGraph.mockResolvedValue({ concepts: [], links: [] })
  extractConcepts.mockResolvedValue({
    concepts: [{ name: 'chain rule', description: null, aliases: [] }],
    links: [],
    nodes: [],
  })
  commitConcepts.mockResolvedValue({ concepts: 1, created: 1, links: 0, nodes: 0 })
  updateNode.mockResolvedValue(undefined)
  updateCourse.mockResolvedValue(undefined)
  similarExercise.mockResolvedValue({ id: 61, title: 'Similar', step_count: 3 })
  drillPatterns.mockResolvedValue([])
  previewAiContext.mockResolvedValue({
    stats: { materials: [], chunks: [], notes: [], concepts: [], hints: 0 },
    rendered: '',
  })
  composeMaterial.mockResolvedValue({
    material: {
      id: 99,
      title: 'Derivatives — cheat sheet',
      kind: 'markdown',
      status: 'ready',
      filename: 'Cheat sheet.md',
      mime: 'text/markdown',
      pages: null,
      course_id: 3,
      group_id: null,
      folder_id: null,
      blob_sha: null,
      created_at: '2026-08-23T00:00:00Z',
    },
    job_id: null,
    deduped: false,
  })
  useChatStore.setState({ open: false, session: null })
}

afterEach(() => {
  clearWindowDropTarget()
})

describe('NodeWorkspace', () => {
  test('root workspace renders tabs, outline editor and child cards', async () => {
    primeDefaults()
    renderWorkspace('/courses/3')
    expect(await screen.findByRole('heading', { name: 'Calculus I' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Overview' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Practice' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ai outline/i })).toBeInTheDocument()
    expect(screen.getAllByText('Derivatives').length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /^practice$/i })).toBeInTheDocument()
  })

  test('node workspace renders breadcrumb and sidebar focus', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5')
    expect(await screen.findByRole('heading', { name: 'Derivatives' })).toBeInTheDocument()
    const crumb = within(screen.getByRole('navigation', { name: 'Breadcrumb' })).getByRole(
      'link',
      { name: 'Calculus I' }
    )
    expect(crumb).toHaveAttribute('href', '/courses/3')
    expect(screen.queryByRole('button', { name: /ai outline/i })).not.toBeInTheDocument()
    const sidebarRoot = screen.getAllByRole('link', { name: 'Calculus I' }).find(
      (link) => link.closest('aside') !== null
    )
    expect(sidebarRoot).toBeDefined()
    expect(screen.getByRole('treeitem', { selected: true })).toHaveTextContent('Derivatives')
  })

  test('breadcrumb last crumb is the page heading and the title row is not duplicated', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5')
    const nav = await screen.findByRole('navigation', { name: 'Breadcrumb' })
    const current = within(nav).getByText('Derivatives')
    expect(current.closest('h1')).not.toBeNull()
    expect(current.getAttribute('aria-current') ?? '').toBe('')
    expect(within(nav).getByText('Derivatives').closest('span')).toHaveAttribute(
      'aria-current',
      'page'
    )
    expect(within(nav).queryByRole('link', { name: 'Derivatives' })).not.toBeInTheDocument()
    expect(screen.getAllByRole('heading', { name: 'Derivatives' })).toHaveLength(1)
    expect(screen.getByRole('button', { name: /study here/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ask about this node/i })).toBeInTheDocument()
  })

  test('child cards show the subsection description when set', async () => {
    primeDefaults()
    nodeWorkspace.mockImplementation((id: number) =>
      Promise.resolve(
        id === 1
          ? {
              ...ROOT_WS,
              children: [
                { id: 5, title: 'Derivatives', depth: 1, order_idx: 0, objectives: [], summary: 'Rates of change' },
                { id: 6, title: 'Integrals', depth: 1, order_idx: 1, objectives: [], summary: null },
              ],
              child_materials: { 5: [], 6: [] },
            }
          : NODE_WS
      )
    )
    renderWorkspace('/courses/3')
    expect(await screen.findByText('Rates of change')).toBeInTheDocument()
  })

  test('clicking a tab navigates with the tab search param', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5')
    await screen.findByRole('heading', { name: 'Derivatives' })
    fireEvent.click(screen.getByRole('tab', { name: 'Tutor' }))
    expect(navigateMock).toHaveBeenCalledWith({
      to: '/courses/$courseId/n/$nodeId',
      params: { courseId: '3', nodeId: '5' },
      search: { tab: 'tutor' },
    })
  })

  test('study here opens the study launcher', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5')
    fireEvent.click(await screen.findByRole('button', { name: /study here/i }))
    console.log('DIALOG?', document.querySelectorAll('[role="dialog"]').length, 'BODY_TAIL:', document.body.innerHTML.slice(-400))
    expect(await screen.findByText('Write a note')).toBeInTheDocument()
    expect(screen.getByText('Mindmap')).toBeInTheDocument()
    expect(screen.getByText('Quiz')).toBeInTheDocument()
  })

  test('opening the study launcher closes an open tab-action popover', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5')
    fireEvent.pointerDown(await screen.findByRole('button', { name: /cheat sheet/i }))
    expect(
      screen.getByRole('menuitem', { name: /generate cheat sheet/i })
    ).toBeInTheDocument()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /study here/i }))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('Write a note')).toBeInTheDocument()
    expect(
      screen.queryByRole('menuitem', { name: /generate cheat sheet/i })
    ).not.toBeInTheDocument()
  })

  test('quick practice on a child card quizzes that child node', async () => {
    primeDefaults()
    generateQuiz.mockResolvedValue({ id: 43, title: 'Chain rule · quiz', question_count: 8 })
    renderWorkspace('/courses/3/n/5')
    fireEvent.click(await screen.findByRole('button', { name: /^practice$/i }))
    await waitFor(() =>
      expect(generateQuiz).toHaveBeenCalledWith({ course_id: 3, node_id: 11, count: 8 })
    )
  })

  test('concepts tab toggles coverage and adds via the picker', async () => {
    primeDefaults()
    addNodeConcept.mockResolvedValue({ node_id: 5, concept_id: 73 })
    removeNodeConcept.mockResolvedValue(undefined)
    conceptGraph.mockResolvedValue({
      concepts: [
        {
          id: 71,
          name: 'chain rule',
          aliases: [],
          nodes: [{ node_id: 5, node_title: 'Derivatives' }],
        },
        { id: 72, name: 'limits', aliases: [], nodes: [{ node_id: 11, node_title: 'Chain rule' }] },
        { id: 73, name: 'continuity', aliases: [], nodes: [] },
      ],
      links: [],
    })
    renderWorkspace('/courses/3/n/5?tab=concepts')
    expect(await screen.findByText('Concept coverage')).toBeInTheDocument()
    expect(screen.getByText('chain rule')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /covers this node/i }))
    await waitFor(() => expect(removeNodeConcept).toHaveBeenCalledWith(5, 71))

    fireEvent.click(screen.getByRole('button', { name: /cover here/i }))
    await waitFor(() => expect(addNodeConcept).toHaveBeenCalledWith(5, 72))

    const picker = screen.getByRole('combobox', { name: /add coverage/i })
    fireEvent.change(picker, { target: { value: '73' } })
    await waitFor(() => expect(addNodeConcept).toHaveBeenCalledWith(5, 73))
  })

  test('concepts tab extracts a draft from the tab bar and commits it', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5?tab=concepts')
    expect(await screen.findByText('Concept coverage')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /extract concepts/i }))
    await waitFor(() => expect(extractConcepts).toHaveBeenCalledWith(3))
    expect(await screen.findByText('Concept draft')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /commit/i }))
    await waitFor(() =>
      expect(commitConcepts).toHaveBeenCalledWith(3, {
        concepts: [{ name: 'chain rule', description: null, aliases: [] }],
        links: [],
        nodes: [],
      })
    )
  })

  test('overview cheat-sheet menu offers open existing and regenerate when a sheet exists', async () => {
    primeDefaults()
    getNodeArtifacts.mockResolvedValue({
      cheat_sheet: { material_id: 42, title: 'Derivatives — cheat sheet' },
      reviews: [
        { material_id: 50, title: 'Derivatives — Review 2026-08-21' },
        { material_id: 45, title: 'Derivatives — Review 2026-08-14' },
      ],
    })
    renderWorkspace('/courses/3/n/5')
    expect(await screen.findByRole('button', { name: /review 2026-08-21/i })).toBeInTheDocument()
    fireEvent.pointerDown(screen.getByRole('button', { name: /cheat sheet/i }))
    expect(screen.getByRole('menuitem', { name: /open existing/i })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /regenerate cheat sheet/i })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem', { name: /open existing/i }))
    expect(await screen.findByRole('dialog', { name: 'chain-rule.pdf' })).toBeInTheDocument()
  })

  test('overview cheat-sheet menu offers generate and opens the cheat-sheet builder', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5')
    fireEvent.pointerDown(await screen.findByRole('button', { name: /cheat sheet/i }))
    expect(screen.getByRole('menuitem', { name: /generate cheat sheet/i })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /open existing/i })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem', { name: /generate cheat sheet/i }))
    expect(await screen.findByLabelText('Document kind')).toHaveValue('cheat_sheet')
  })

  test('overview cheat-sheet builder composes with the cheat_sheet kind and previews the result', async () => {
    primeDefaults()
    getMaterial.mockResolvedValue({
      material: {
        id: 99,
        title: 'Derivatives — cheat sheet',
        kind: 'markdown',
        status: 'ready',
        filename: 'Cheat sheet.md',
        mime: 'text/markdown',
        pages: null,
        course_id: 3,
        group_id: null,
        folder_id: null,
        blob_sha: null,
        created_at: '2026-08-23T00:00:00Z',
      },
      extraction: {
        id: 1,
        material_id: 99,
        version: 1,
        extractor: 'text',
        markdown: '# Derivatives cheat sheet\n\n- Power rule: $f\'(x) = nx^{n-1}$',
        blocks: [],
      },
      index_card: null,
      drawings: [],
    })
    renderWorkspace('/courses/3/n/5')
    fireEvent.pointerDown(await screen.findByRole('button', { name: /cheat sheet/i }))
    fireEvent.click(screen.getByRole('menuitem', { name: /generate cheat sheet/i }))
    const submit = await screen.findByRole('button', { name: /^compose$/i })
    fireEvent.click(submit)
    await waitFor(() =>
      expect(composeMaterial).toHaveBeenCalledWith(
        expect.objectContaining({ node_id: 5, kind: 'cheat_sheet' })
      )
    )
    await waitFor(() => expect(getMaterial).toHaveBeenCalledWith(99))
    expect(await screen.findByText(/Power rule/)).toBeInTheDocument()
  })

  test('overview adds a child node under the current node', async () => {
    primeDefaults()
    addNode.mockResolvedValue({ id: 12, title: 'Integrals', order_idx: 1000, depth: 2 })
    renderWorkspace('/courses/3/n/5')
    fireEvent.click(await screen.findByRole('button', { name: 'Add child' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Node title' }), {
      target: { value: 'Integrals' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    await waitFor(() => expect(addNode).toHaveBeenCalledWith(3, 5, 'Integrals'))
  })

  test('overview empty state offers to add the first child', async () => {
    primeDefaults()
    nodeWorkspace.mockImplementation((id: number) =>
      Promise.resolve(id === 1 ? ROOT_WS : { ...NODE_WS, children: [], child_materials: {} })
    )
    renderWorkspace('/courses/3/n/5')
    expect(await screen.findByText(/No subsections yet/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add child' })).toBeInTheDocument()
  })

  test('fresh course root shows the guided onboarding card instead of the action bar', async () => {
    primeDefaults()
    nodeWorkspace.mockImplementation((id: number) =>
      Promise.resolve(id === 1 ? { ...ROOT_WS, children: [], child_materials: {} } : NODE_WS)
    )
    renderWorkspace('/courses/3')
    expect(await screen.findByTestId('course-onboarding')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /add materials/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /generate ai outline/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /add node/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /study this course/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ask the tutor/i })).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /compose study material/i })
    ).not.toBeInTheDocument()
  })

  test('onboarding add materials navigates to the materials tab', async () => {
    primeDefaults()
    nodeWorkspace.mockImplementation((id: number) =>
      Promise.resolve(id === 1 ? { ...ROOT_WS, children: [], child_materials: {} } : NODE_WS)
    )
    renderWorkspace('/courses/3')
    fireEvent.click(await screen.findByRole('button', { name: /add materials/i }))
    expect(navigateMock).toHaveBeenCalledWith({
      to: '/courses/$courseId',
      params: { courseId: '3' },
      search: { tab: 'materials' },
    })
  })

  test('onboarding generate outline drafts the course outline', async () => {
    primeDefaults()
    outlineDraft.mockResolvedValue(DRAFT)
    nodeWorkspace.mockImplementation((id: number) =>
      Promise.resolve(id === 1 ? { ...ROOT_WS, children: [], child_materials: {} } : NODE_WS)
    )
    renderWorkspace('/courses/3')
    fireEvent.click(await screen.findByRole('button', { name: /generate ai outline/i }))
    await waitFor(() => expect(outlineDraft).toHaveBeenCalledWith(3))
    expect(await screen.findByText('Limits')).toBeInTheDocument()
  })

  test('root overview hosts outline actions in the action bar', async () => {
    primeDefaults()
    renderWorkspace('/courses/3')
    expect(await screen.findByRole('heading', { name: 'Calculus I' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ai outline/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /add node/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add child' })).not.toBeInTheDocument()
  })

  test('root overview add node posts against the root', async () => {
    primeDefaults()
    addNode.mockResolvedValue({ id: 9, title: 'Integrals', order_idx: 1000, depth: 1 })
    renderWorkspace('/courses/3')
    fireEvent.click(await screen.findByRole('button', { name: /add node/i }))
    const input = screen.getByPlaceholderText('Node title')
    fireEvent.change(input, { target: { value: 'Integrals' } })
    fireEvent.submit(input.closest('form') as HTMLFormElement)
    await waitFor(() => expect(addNode).toHaveBeenCalledWith(3, 1, 'Integrals'))
  })

  test('root AI outline drafts, prunes and commits', async () => {
    primeDefaults()
    outlineDraft.mockResolvedValue(DRAFT)
    outlineCommit.mockResolvedValue({ chapters: 1, sections: 1, allocations: 1 })
    renderWorkspace('/courses/3')
    fireEvent.click(await screen.findByRole('button', { name: /ai outline/i }))
    expect(await screen.findByText('Limits')).toBeInTheDocument()
    expect(screen.getByText('Continuity')).toBeInTheDocument()

    const draftCard = screen
      .getByRole('button', { name: /commit outline/i })
      .closest('[data-as="card"]') as HTMLElement
    const derivativesRow = within(draftCard)
      .getByText('Derivatives')
      .closest('div') as HTMLElement
    fireEvent.click(within(derivativesRow).getByRole('button', { name: /remove/i }))
    await waitFor(() => expect(within(draftCard).queryByText('Derivatives')).not.toBeInTheDocument())
    expect(within(draftCard).getByText('Continuity')).toBeInTheDocument()

    fireEvent.click(within(draftCard).getByRole('button', { name: /commit outline/i }))
    await waitFor(() => expect(outlineCommit).toHaveBeenCalledWith(3, [DRAFT.chapters[0]]))
    await waitFor(() => expect(screen.queryByText('Limits')).not.toBeInTheDocument())
  })

  test('root AI outline cancel discards the draft', async () => {
    primeDefaults()
    outlineDraft.mockResolvedValue(DRAFT)
    renderWorkspace('/courses/3')
    fireEvent.click(await screen.findByRole('button', { name: /ai outline/i }))
    expect(await screen.findByText('Limits')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
    await waitFor(() => expect(screen.queryByText('Limits')).not.toBeInTheDocument())
  })

  test('tutor tab lists node-bound sessions and ask opens the sidebar', async () => {
    primeDefaults()
    listChatSessions.mockResolvedValue([
      { id: 9, course_id: 3, node_id: 5, title: 'Derivatives chat' },
    ])
    createChatSession.mockResolvedValue({ id: 12, public_id: 'uuid-12', course_id: 3, node_id: 5, title: 'Derivatives' })
    renderWorkspace('/courses/3/n/5?tab=tutor')
    expect(await screen.findByText('Derivatives chat')).toBeInTheDocument()
    await waitFor(() => expect(listChatSessions).toHaveBeenCalledWith(5))

    fireEvent.click(screen.getAllByRole('button', { name: /ask about this node/i })[0])
    await waitFor(() => expect(createChatSession).toHaveBeenCalledWith(3, 5, 'Derivatives'))
    await waitFor(() => expect(useChatStore.getState().open).toBe(true))
    expect(useChatStore.getState().session).toEqual({ id: 12, publicId: 'uuid-12' })
  })

  test('notes tab rolls up notes with node chips and opens a row in the drawer', async () => {
    primeDefaults()
    listNotes.mockResolvedValue({
      items: [
        {
          id: 21,
          title: 'Chain rule note',
          course_id: 3,
          node_id: 11,
          owner_type: 'standalone',
          owner_id: null,
          tags: [],
          pinned: false,
          updated_at: '2026-08-19T00:00:00Z',
        },
      ],
      next_cursor: null,
    })
    renderWorkspace('/courses/3/n/5?tab=notes')
    expect(await screen.findByText('Chain rule note')).toBeInTheDocument()
    expect(screen.getByText('Chain rule')).toBeInTheDocument()
    expect(listNotes).toHaveBeenCalledWith(undefined, 3, {
      tag: undefined,
      node_id: 5,
      limit: 50,
      cursor: undefined,
    })

    fireEvent.doubleClick(screen.getByRole('button', { name: /chain rule note/i }))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(await screen.findByRole('textbox', { name: 'Note title' })).toBeInTheDocument()

    const openCall = navigateMock.mock.calls.find(
      (call) =>
        call[0].to === '/courses/$courseId/n/$nodeId' && typeof call[0].search === 'function'
    )
    expect(openCall).toBeDefined()
    expect(
      navigateMock.mock.calls.every((call) => call[0].to !== '/notes/$noteId')
    ).toBe(true)
  })

  test('notes tab renames and deletes through the row menu', async () => {
    primeDefaults()
    listNotes.mockResolvedValue({
      items: [
        {
          id: 21,
          title: 'Chain rule note',
          course_id: 3,
          node_id: 11,
          owner_type: 'standalone',
          owner_id: null,
          tags: [],
          pinned: false,
          updated_at: '2026-08-19T00:00:00Z',
        },
      ],
      next_cursor: null,
    })
    updateNote.mockResolvedValue({})
    deleteNote.mockResolvedValue(undefined)
    renderWorkspace('/courses/3/n/5?tab=notes')
    await screen.findByText('Chain rule note')
    const kebabs = screen.getAllByRole('button', { name: 'Actions' })
    fireEvent.click(kebabs[kebabs.length - 1])
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Rename' }))
    const input = await screen.findByRole('textbox', { name: 'Rename note' })
    fireEvent.change(input, { target: { value: 'Renamed note' } })
    fireEvent.submit(input.closest('form')!)
    await waitFor(() => expect(updateNote).toHaveBeenCalledWith(21, { title: 'Renamed note' }))

    fireEvent.click(screen.getAllByRole('button', { name: 'Actions' })[0])
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Delete' }))
    expect(deleteNote).not.toHaveBeenCalled()
    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(deleteNote).toHaveBeenCalledWith(21))
  })

  test('practice tab deletes a quiz from the row menu', async () => {
    primeDefaults()
    listQuizzes.mockResolvedValue([
      { id: 50, title: 'Node quiz', type: 'quiz', course_id: 3, node_id: 5, question_count: 4 },
    ])
    deleteQuiz.mockResolvedValue(undefined)
    renderWorkspace('/courses/3/n/5?tab=practice')
    await screen.findByText('Node quiz')
    fireEvent.click(screen.getByRole('button', { name: 'Actions' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Delete' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(deleteQuiz).toHaveBeenCalledWith(50))
  })

  test('notes tab creates a note here and opens it in the drawer', async () => {
    primeDefaults()
    createNote.mockResolvedValue({ id: 30, body: [], drawings: [], tags: [] })
    renderWorkspace('/courses/3/n/5?tab=notes')
    fireEvent.click(await screen.findByRole('button', { name: /new note here/i }))
    await waitFor(() =>
      expect(createNote).toHaveBeenCalledWith({
        title: 'Untitled note',
        course_id: 3,
        node_id: 5,
        tags: [],
      })
    )
    expect(await screen.findByRole('textbox', { name: 'Note title' })).toBeInTheDocument()
    expect(
      navigateMock.mock.calls.every((call) => call[0].to !== '/notes/$noteId')
    ).toBe(true)
  })

  test('notes tab filters by tag and submitted search text', async () => {
    primeDefaults()
    listNotes.mockResolvedValue({
      items: [
        {
          id: 21,
          title: 'Chain rule note',
          course_id: 3,
          node_id: 11,
          owner_type: 'standalone',
          owner_id: null,
          tags: ['exam'],
          pinned: false,
          updated_at: '2026-08-19T00:00:00Z',
        },
      ],
      next_cursor: null,
    })
    listNoteTags.mockResolvedValue([{ tag: 'exam', count: 1 }])
    renderWorkspace('/courses/3/n/5?tab=notes')
    fireEvent.click(await screen.findByRole('button', { name: 'exam' }))
    await waitFor(() =>
      expect(listNotes).toHaveBeenLastCalledWith(undefined, 3, {
        tag: 'exam',
        node_id: 5,
        limit: 50,
        cursor: undefined,
      })
    )

    fireEvent.click(screen.getByRole('button', { name: 'Search' }))
    const input = await screen.findByRole('textbox', { name: /search notes/i })
    fireEvent.change(input, { target: { value: 'chain rule' } })
    await waitFor(() =>
      expect(listNotes).toHaveBeenLastCalledWith('chain rule', 3, {
        tag: 'exam',
        node_id: 5,
        limit: 50,
        cursor: undefined,
      })
    )
  })

  test('practice tab lists scoped quizzes and exercises with node chips', async () => {
    primeDefaults()
    listQuizzes.mockResolvedValue([
      { id: 50, title: 'Node quiz', type: 'quiz', course_id: 3, node_id: 5, question_count: 4 },
    ])
    listExercises.mockResolvedValue([
      { id: 60, title: 'Node exercise', course_id: 3, node_id: 11, difficulty: 2, step_count: 3 },
    ])
    renderWorkspace('/courses/3/n/5?tab=practice')
    expect(await screen.findByText('Node quiz')).toBeInTheDocument()
    expect(screen.getByText('Node exercise')).toBeInTheDocument()
    expect(screen.getAllByText('Derivatives').length).toBeGreaterThan(1)
    expect(screen.getByText('Chain rule')).toBeInTheDocument()
    expect(screen.getByText('Level 2')).toBeInTheDocument()
    expect(screen.getByText('4 questions')).toBeInTheDocument()
  })

  test('practice tab has one New practice action opening the builder', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5?tab=practice')
    expect(await screen.findByRole('button', { name: /new practice/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /generate quiz/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /generate exercise/i })).not.toBeInTheDocument()
  })

  test('practice tab rows navigate to the quiz runner and exercise player', async () => {
    primeDefaults()
    listQuizzes.mockResolvedValue([
      { id: 50, title: 'Node quiz', type: 'quiz', course_id: 3, node_id: 5, question_count: 4 },
    ])
    listExercises.mockResolvedValue([
      { id: 60, title: 'Node exercise', course_id: 3, node_id: 11, difficulty: 2, step_count: 3 },
    ])
    const first = renderWorkspace('/courses/3/n/5?tab=practice')
    fireEvent.doubleClick(await screen.findByRole('button', { name: /node quiz/i }))
    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith(
        expect.objectContaining({
          to: '/quiz/$activityId',
          params: { activityId: '50' },
          search: { from: '/courses/3/n/5?tab=practice' },
        })
      )
    )
    first.unmount()
    renderWorkspace('/courses/3/n/5?tab=practice')
    fireEvent.doubleClick(await screen.findByRole('button', { name: /node exercise/i }))
    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith(
        expect.objectContaining({
          to: '/exercises/$exerciseId',
          params: { exerciseId: '60' },
          search: { from: '/courses/3/n/5?tab=practice' },
        })
      )
    )
  })

  test('practice tab import opens the quiz import dialog course-prebound', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5?tab=practice')
    fireEvent.click(await screen.findByRole('button', { name: /^import$/i }))
    expect(await screen.findByText('Import caq quiz')).toBeInTheDocument()
    expect(screen.queryByLabelText('Course')).not.toBeInTheDocument()
  })

  test('practice tab similar action generates an isomorphic variant', async () => {
    primeDefaults()
    listExercises.mockResolvedValue([
      { id: 60, title: 'Node exercise', course_id: 3, node_id: 11, difficulty: 2, step_count: 3 },
    ])
    renderWorkspace('/courses/3/n/5?tab=practice')
    await screen.findByText('Node exercise')
    const kebabs = screen.getAllByRole('button', { name: 'Actions' })
    fireEvent.click(kebabs[kebabs.length - 1])
    fireEvent.click(
      await screen.findByRole('menuitem', { name: /generate a similar exercise/i })
    )
    await waitFor(() => expect(similarExercise).toHaveBeenCalledWith(60))
  })

  test('practice tab drills card uses the workspace course', async () => {
    primeDefaults()
    drillPatterns.mockResolvedValue([
      {
        pattern: 'sign_slip',
        name: 'Sign slip',
        description: 'dropping a minus sign',
        source: 'seeded',
        occurrences: 2,
      },
    ])
    renderWorkspace('/courses/3/n/5?tab=practice')
    expect(await screen.findByText('Sign slip')).toBeInTheDocument()
    expect(screen.getByText('2 mistakes')).toBeInTheDocument()
  })

  test('missing node shows a message', async () => {
    primeDefaults()
    nodeWorkspace.mockRejectedValue(new Error('404'))
    renderWorkspace('/courses/3/n/5')
    expect(await screen.findByText('This node no longer exists.')).toBeInTheDocument()
  })

  test('material rows open the drawer in place and close strips the param', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5?tab=materials')
    const row = await screen.findByRole('button', { name: /chain-rule\.pdf/i })
    fireEvent.click(row, { detail: 1 })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    fireEvent.doubleClick(row)
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toBeInTheDocument()
    await waitFor(() =>
      expect(routerHolder.current!.state.location.search).toMatchObject({ material: 7 })
    )
    expect(routerHolder.current!.state.location.pathname).toBe('/courses/3/n/5')

    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    await waitFor(() =>
      expect(
        (routerHolder.current!.state.location.search as { material?: number }).material
      ).toBeUndefined()
    )
    expect(routerHolder.current!.state.location.href).not.toContain('material=')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  test('materials tab toggles to grid and back', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5?tab=materials')
    await screen.findByRole('button', { name: /chain-rule\.pdf/i })
    fireEvent.click(screen.getByRole('button', { name: 'Grid view' }))
    await screen.findByRole('button', { name: /chain-rule\.pdf/i })
    fireEvent.click(screen.getByRole('button', { name: 'List view' }))
    expect(await screen.findByRole('button', { name: /chain-rule\.pdf/i })).toBeInTheDocument()
  })

  test('materials tab lists only the node materials, not child sections', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5?tab=materials')
    expect(await screen.findByRole('button', { name: /chain-rule\.pdf/i })).toBeInTheDocument()
    expect(screen.queryByText('worked problems')).not.toBeInTheDocument()
    expect(screen.queryByText('Chain rule')).not.toBeInTheDocument()
  })

  test('materials tab search filters materials and shows a no-results note', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5?tab=materials')
    await screen.findByRole('button', { name: /chain-rule\.pdf/i })
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))
    const input = await screen.findByRole('textbox', { name: 'Filter materials…' })
    fireEvent.change(input, { target: { value: 'no-such-material' } })
    expect(screen.queryByRole('button', { name: /chain-rule\.pdf/i })).not.toBeInTheDocument()
    expect(screen.getByText('Nothing matches this filter.')).toBeInTheDocument()
    fireEvent.change(input, { target: { value: 'chain' } })
    expect(screen.getByRole('button', { name: /chain-rule\.pdf/i })).toBeInTheDocument()
    expect(screen.queryByText('Nothing matches this filter.')).not.toBeInTheDocument()
  })

  test('materials tab right-click menu unassigns from the node', async () => {
    primeDefaults()
    deallocateMaterial.mockResolvedValue(undefined)
    renderWorkspace('/courses/3/n/5?tab=materials')
    const row = await screen.findByRole('button', { name: /chain-rule\.pdf/i })
    fireEvent.contextMenu(row)
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Remove from node' }))
    await waitFor(() => expect(deallocateMaterial).toHaveBeenCalledWith(5, 7))
  })

  test('materials tab uploads land in the course library and are assigned to the node', async () => {
    primeDefaults()
    uploadMaterial.mockResolvedValue({
      material: { id: 77, title: 'problems.pdf', kind: 'pdf', status: 'pending' },
      job_id: null,
      deduped: false,
    })
    allocateMaterial.mockResolvedValue({ node_id: 5, material_id: 77 })
    renderWorkspace('/courses/3/n/5?tab=materials')
    await screen.findByRole('button', { name: /chain-rule\.pdf/i })
    const input = screen.getByLabelText('Upload files')
    fireEvent.change(input, {
      target: { files: [new File(['data'], 'problems.pdf', { type: 'application/pdf' })] },
    })
    await waitFor(() => expect(uploadMaterial).toHaveBeenCalledTimes(1))
    expect(uploadMaterial.mock.calls[0][1]).toBe(3)
    expect(uploadMaterial.mock.calls[0][2]).toBeNull()
    await waitFor(() => expect(allocateMaterial).toHaveBeenCalledWith(5, 77))
  })

  test('empty materials tab offers an upload dropzone at course root', async () => {
    primeDefaults()
    renderWorkspace('/courses/3?tab=materials')
    expect(
      await screen.findByText('No materials here yet — upload files or assign from the library')
    ).toBeInTheDocument()
    expect(
      screen.getByLabelText('Drop files here or click to browse')
    ).toBeInTheDocument()
  })

  test('materials tab new menu offers create and upload entries', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5?tab=materials')
    await screen.findByRole('button', { name: /chain-rule\.pdf/i })

    fireEvent.click(screen.getByRole('button', { name: 'New…' }))
    expect(await screen.findByRole('menu')).toBeInTheDocument()
    for (const label of [
      'New folder',
      'New text file',
      'New Markdown file',
      'Upload files…',
      'Upload folder…',
    ]) {
      expect(screen.getByRole('menuitem', { name: label })).toBeInTheDocument()
    }
    expect(
      screen.queryByRole('button', { name: 'Choose what to upload' })
    ).not.toBeInTheDocument()
  })

  test('materials tab new Markdown file creates it unfiled and assigns it to the node', async () => {
    primeDefaults()
    createTextMaterial.mockResolvedValue({
      materialId: 88,
      content: '$x^2$ rules',
      refToReal: {},
      jobId: null,
    })
    allocateMaterial.mockResolvedValue({ node_id: 5, material_id: 88 })
    renderWorkspace('/courses/3/n/5?tab=materials')
    await screen.findByRole('button', { name: /chain-rule\.pdf/i })

    fireEvent.click(screen.getByRole('button', { name: 'New…' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'New Markdown file' }))
    const nameInput = await screen.findByPlaceholderText('File name')
    fireEvent.change(nameInput, { target: { value: 'derivation' } })
    fireEvent.change(screen.getByLabelText('File content (markdown + LaTeX)'), {
      target: { value: '$x^2$ rules' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    await waitFor(() =>
      expect(createTextMaterial).toHaveBeenCalledWith({
        course_id: 3,
        folder_id: null,
        filename: 'derivation.md',
        content: '$x^2$ rules',
        drawings: [],
      })
    )
    await waitFor(() => expect(allocateMaterial).toHaveBeenCalledWith(5, 88))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Save' })).not.toBeNull()
    )
    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    await waitFor(() =>
      expect(screen.queryByPlaceholderText('File name')).not.toBeInTheDocument()
    )
  })

  test('materials tab new folder creates it at library root and assigns it to the node', async () => {
    primeDefaults()
    allocateNodeFolder.mockResolvedValue(undefined)
    renderWorkspace('/courses/3/n/5?tab=materials')
    await screen.findByRole('button', { name: /chain-rule\.pdf/i })

    fireEvent.click(screen.getByRole('button', { name: 'New…' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'New folder' }))
    fireEvent.change(await screen.findByPlaceholderText('Folder name'), {
      target: { value: 'Practice set' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    await waitFor(() => expect(createFolder).toHaveBeenCalledWith('Practice set', null, 3))
    await waitFor(() => expect(allocateNodeFolder).toHaveBeenCalledWith(5, 901))
    await waitFor(() =>
      expect(screen.queryByPlaceholderText('Folder name')).not.toBeInTheDocument()
    )
  })

  test('materials tab right-click on empty pane opens the create menu', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5?tab=materials')
    await screen.findByRole('button', { name: /chain-rule\.pdf/i })

    const pane = document.querySelector('[data-marquee-surface]') as HTMLElement
    fireEvent.contextMenu(pane)
    expect(await screen.findByRole('menu')).toBeInTheDocument()
    expect(
      screen.getByRole('menuitem', { name: 'New Markdown file' })
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem', { name: 'New text file' }))
    expect(await screen.findByPlaceholderText('File name')).toBeInTheDocument()
  })

  test('notes tab right-click on empty pane opens the create menu', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5?tab=notes')
    await screen.findByRole('button', { name: 'New note here' })
    const text = await screen.findByText('No notes here yet.')
    fireEvent.contextMenu(text)
    expect(await screen.findByRole('menu')).toBeInTheDocument()
    expect(
      screen.getByRole('menuitem', { name: 'New note here' })
    ).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Draft notes' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem', { name: 'New note here' }))
    await waitFor(() => expect(createNote).toHaveBeenCalled())
  })

  test('materials tab marquee drag selects the intersecting entries', async () => {
    primeDefaults()
    const rectSpy = vi
      .spyOn(Element.prototype, 'getBoundingClientRect')
      .mockReturnValue({
        left: 0, top: 0, right: 400, bottom: 400, width: 400, height: 400, x: 0, y: 0,
        toJSON: () => ({}),
      } as DOMRect)
    renderWorkspace('/courses/3/n/5?tab=materials')
    await screen.findByRole('button', { name: /chain-rule\.pdf/i })

    const pane = document.querySelector('[data-marquee-surface]') as HTMLElement
    fireEvent.mouseDown(pane, { clientX: 0, clientY: 0, button: 0 })
    fireEvent.mouseMove(window, { clientX: 200, clientY: 200 })
    fireEvent.mouseUp(window, { clientX: 200, clientY: 200 })

    const wrapper = screen
      .getByText('chain-rule.pdf')
      .closest('[data-selectable-id]') as HTMLElement
    await waitFor(() =>
      expect(wrapper.querySelector('[class*="bg-primary/10"]')).not.toBeNull()
    )
    expect(screen.queryByText(/selected/i)).not.toBeInTheDocument()

    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() =>
      expect(wrapper.querySelector('[class*="bg-primary/10"]')).toBeNull()
    )
    rectSpy.mockRestore()
  })

  test('materials tab folder upload assigns the folder to the node, not the files', async () => {
    primeDefaults()
    uploadMaterial.mockClear()
    allocateMaterial.mockClear()
    createFolder.mockClear()
    allocateNodeFolder.mockClear()
    allocateNodeFolder.mockResolvedValue(undefined)
    uploadMaterial.mockImplementation(async (sent: File) => ({
      material: { id: 70 + sent.name.charCodeAt(0), title: sent.name, kind: 'pdf', status: 'pending' },
      job_id: null,
      deduped: false,
    }))
    allocateMaterial.mockResolvedValue(undefined)
    renderWorkspace('/courses/3/n/5?tab=materials')
    await screen.findByRole('button', { name: /chain-rule\.pdf/i })

    const input = screen.getByLabelText('Upload a folder')
    const pack = new File(['x'], 'pack.pdf')
    Object.defineProperty(pack, 'webkitRelativePath', { value: 'Lecture pack/pack.pdf' })
    const deep = new File(['x'], 'deep.pdf')
    Object.defineProperty(deep, 'webkitRelativePath', { value: 'Lecture pack/week1/deep.pdf' })
    fireEvent.change(input, { target: { files: [pack, deep] } })

    await waitFor(() => expect(uploadMaterial).toHaveBeenCalledTimes(2))
    expect(createFolder).toHaveBeenCalledWith('Lecture pack', null, 3)
    expect(createFolder).toHaveBeenCalledWith('week1', 901, 3)
    const targetFolders = uploadMaterial.mock.calls.map((call) => call[2])
    expect(new Set(targetFolders)).toEqual(new Set([901, 902]))
    await waitFor(() =>
      expect(allocateNodeFolder).toHaveBeenCalledWith(5, 901)
    )
    expect(allocateNodeFolder).toHaveBeenCalledTimes(1)
    expect(allocateMaterial).not.toHaveBeenCalled()
  })

  test('materials tab registers the window drop target for the node', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5?tab=materials')
    await screen.findByRole('button', { name: /chain-rule\.pdf/i })
    const target = getWindowDropTarget()
    expect(target?.label).toBe('Derivatives')
    expect(target?.upload()).not.toBeNull()
  })

  test('practice tab switches to a flashcards segment with its own actions', async () => {
    primeDefaults()
    listFlashcards.mockResolvedValue([
      {
        id: 7,
        kind: 'basic',
        front: [{ type: 'text', md: 'Power rule' }],
        back: [{ type: 'text', md: 'n times x to the n minus one' }],
        source: 'note',
        source_ref: null,
        node_id: 5,
        due_at: null,
        state: null,
      },
    ])
    renderWorkspace('/courses/3/n/5?tab=practice')
    const setsSegment = await screen.findByRole('tab', { name: /quizzes & exercises/i })
    expect(setsSegment).toHaveAttribute('aria-selected', 'true')
    fireEvent.click(screen.getByRole('tab', { name: /flashcards/i }))
    expect(setsSegment).toHaveAttribute('aria-selected', 'false')
    expect(await screen.findByText('Power rule')).toBeInTheDocument()
    expect(dueFlashcards).toHaveBeenCalledWith(20, undefined, 5)
  })

  test('practice tab keeps quiz actions on the sets segment only', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5?tab=practice')
    await screen.findByRole('button', { name: /new practice/i })
    fireEvent.click(await screen.findByRole('tab', { name: /flashcards/i }))
    expect(screen.getByRole('button', { name: /import \.apkg/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /new practice/i })).not.toBeInTheDocument()
  })

  test('cards tab shows the review queue scoped to the node', async () => {
    primeDefaults()
    dueFlashcards.mockResolvedValue([
      {
        id: 7,
        kind: 'basic',
        front: [{ type: 'text', md: 'Power rule for x to the n?' }],
        back: [{ type: 'text', md: 'n times x to the n minus one' }],
        source: 'note',
        source_ref: null,
        node_id: 5,
        due_at: null,
        state: null,
      },
    ])
    renderWorkspace('/courses/3/n/5?tab=cards')
    expect(await screen.findByText(/Power rule for/)).toBeInTheDocument()
    expect(dueFlashcards).toHaveBeenCalledWith(20, undefined, 5)

    fireEvent.click(screen.getByRole('button', { name: /show answer/i }))
    expect(await screen.findByText('n times x to the n minus one')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /good/i }))
    await waitFor(() => expect(reviewFlashcard).toHaveBeenCalledWith(7, 3))
  })

  test('old chapters route redirects to the node workspace', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/chapters/5')
    expect(await screen.findByRole('heading', { name: 'Derivatives' })).toBeInTheDocument()
  })

  test('header shows the settings popover with badge and description', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5')
    await screen.findByRole('heading', { name: 'Derivatives' })
    expect(screen.queryByText('Rates of change')).not.toBeInTheDocument()
    expect(screen.queryByRole('img', { name: /custom ai instructions/i })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /node settings/i }))
    const panel = screen.getByRole('dialog', { name: /node settings/i })
    expect(within(panel).getByRole('textbox', { name: /^title$/i })).toHaveValue('Derivatives')
    expect(within(panel).getByRole('textbox', { name: /description/i })).toHaveValue(
      'Rates of change'
    )

    fireEvent.change(within(panel).getByRole('textbox', { name: /ai instructions/i }), {
      target: { value: 'prefer numeric answers' },
    })
    fireEvent.click(within(panel).getByRole('button', { name: /save/i }))
    await waitFor(() => expect(updateNode).toHaveBeenCalledWith(5, { ai_hint: 'prefer numeric answers' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  test('overview no longer renders the AI instructions card', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5')
    await screen.findByRole('heading', { name: 'Derivatives' })
    expect(screen.queryByText('AI instructions for this node')).not.toBeInTheDocument()
  })

  test('root settings popover edits title and description through the course endpoint', async () => {
    primeDefaults()
    updateNode.mockClear()
    updateCourse.mockClear()
    renderWorkspace('/courses/3')
    await screen.findByRole('heading', { name: 'Calculus I' })

    fireEvent.click(screen.getByRole('button', { name: /node settings/i }))
    const panel = screen.getByRole('dialog', { name: /node settings/i })
    expect(within(panel).getByRole('textbox', { name: /^title$/i })).toHaveValue('Calculus I')

    fireEvent.change(within(panel).getByRole('textbox', { name: /^title$/i }), {
      target: { value: 'Calculus II' },
    })
    fireEvent.change(within(panel).getByRole('textbox', { name: /description/i }), {
      target: { value: 'A different description' },
    })
    fireEvent.click(within(panel).getByRole('button', { name: /save/i }))
    await waitFor(() =>
      expect(updateCourse).toHaveBeenCalledWith(3, {
        title: 'Calculus II',
        description: 'A different description',
      })
    )
    expect(updateNode).not.toHaveBeenCalled()
  })

  test('materials tab right-click unassigns and assigns to a node', async () => {
    primeDefaults()
    deallocateMaterial.mockResolvedValue(undefined)
    allocateMaterial.mockResolvedValue(undefined)
    renderWorkspace('/courses/3/n/5?tab=materials')
    expect(await screen.findByText('chain-rule.pdf')).toBeInTheDocument()

    fireEvent.contextMenu(screen.getByText('chain-rule.pdf'))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Remove from node' }))
    await waitFor(() => expect(deallocateMaterial).toHaveBeenCalledWith(5, 7))

    fireEvent.contextMenu(screen.getByText('chain-rule.pdf'))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Assign to node…' }))
    fireEvent.click(await screen.findByRole('treeitem', { name: /Chain rule/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Assign' }))
    await waitFor(() => expect(allocateMaterial).toHaveBeenCalledWith(11, 7))
  })

  test('materials tab shows assigned folders as folder rows with unassign', async () => {
    primeDefaults()
    deallocateNodeFolder.mockResolvedValue(undefined)
    nodeWorkspace.mockImplementation((id: number) =>
      Promise.resolve(
        id === 1
          ? ROOT_WS
          : {
              ...NODE_WS,
              folders: [
                {
                  folder_id: 10,
                  name: 'Lectures',
                  source_id: null,
                  member_count: 2,
                  rationale: null,
                  auto_assigned: false,
                },
              ],
              materials: [NODE_WS.materials[0]],
              folder_material_ids: [9],
            }
      )
    )
    renderWorkspace('/courses/3/n/5?tab=materials')
    await screen.findByRole('button', { name: /chain-rule\.pdf/i })

    expect(screen.queryByText('Assigned folders:')).not.toBeInTheDocument()
    const row = screen.getByTitle('2 materials in this folder join this node')
    expect(within(row).getByText('Lectures')).toBeInTheDocument()
    expect(within(row).getByText('2')).toBeInTheDocument()

    fireEvent.click(within(row).getByTitle('Unassign folder'))
    await waitFor(() => expect(deallocateNodeFolder).toHaveBeenCalledWith(5, 10))
  })

  test('materials tab does not list files from an assigned folder', async () => {
    primeDefaults()
    nodeWorkspace.mockImplementation((id: number) =>
      Promise.resolve(
        id === 1
          ? ROOT_WS
          : {
              ...NODE_WS,
              folders: [
                {
                  folder_id: 10,
                  name: 'Lectures',
                  source_id: null,
                  member_count: 2,
                  rationale: null,
                  auto_assigned: false,
                },
              ],
              materials: [],
              folder_material_ids: [8, 9],
            }
      )
    )
    renderWorkspace('/courses/3/n/5?tab=materials')
    await screen.findByTitle('2 materials in this folder join this node')

    expect(screen.queryByText(/week1\.pdf/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/notes\.pdf/i)).not.toBeInTheDocument()
    expect(screen.getByTitle('2 materials in this folder join this node')).toBeInTheDocument()
  })

  test('assigned folders render as grid tiles too', async () => {
    primeDefaults()
    nodeWorkspace.mockImplementation((id: number) =>
      Promise.resolve(
        id === 1
          ? ROOT_WS
          : {
              ...NODE_WS,
              folders: [
                {
                  folder_id: 10,
                  name: 'Lectures',
                  source_id: null,
                  member_count: 2,
                  rationale: null,
                  auto_assigned: false,
                },
              ],
              materials: [],
            }
      )
    )
    renderWorkspace('/courses/3/n/5?tab=materials')
    await screen.findByTitle('2 materials in this folder join this node')
    fireEvent.click(screen.getByRole('button', { name: 'Grid view' }))
    expect(
      await screen.findByTitle('2 materials in this folder join this node')
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Lectures/ })).toBeInTheDocument()
  })

  test('double-clicking an assigned folder opens it in the library', async () => {
    primeDefaults()
    nodeWorkspace.mockImplementation((id: number) =>
      Promise.resolve(
        id === 1
          ? ROOT_WS
          : {
              ...NODE_WS,
              folders: [
                {
                  folder_id: 10,
                  name: 'Lectures',
                  source_id: null,
                  member_count: 2,
                  rationale: null,
                  auto_assigned: false,
                },
              ],
            }
      )
    )
    renderWorkspace('/courses/3/n/5?tab=materials')
    const row = await screen.findByTitle('2 materials in this folder join this node')
    fireEvent.doubleClick(row)
    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith(
        expect.objectContaining({
          to: '/library',
          search: expect.objectContaining({ course: 3, folder: 10 }),
        })
      )
    )
  })

  test('linked-source assigned folder opens its library source', async () => {
    primeDefaults()
    nodeWorkspace.mockImplementation((id: number) =>
      Promise.resolve(
        id === 1
          ? ROOT_WS
          : {
              ...NODE_WS,
              folders: [
                {
                  folder_id: 10,
                  name: 'Lectures',
                  source_id: 77,
                  member_count: 2,
                  rationale: null,
                  auto_assigned: false,
                },
              ],
            }
      )
    )
    renderWorkspace('/courses/3/n/5?tab=materials')
    const row = await screen.findByTitle('2 materials in this folder join this node')
    fireEvent.doubleClick(row)
    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith(
        expect.objectContaining({
          to: '/library',
          search: expect.objectContaining({ course: 3, folder: 10, source: 77 }),
        })
      )
    )
  })

  test('assigned folder context menu unassigns it', async () => {
    primeDefaults()
    deallocateNodeFolder.mockResolvedValue(undefined)
    nodeWorkspace.mockImplementation((id: number) =>
      Promise.resolve(
        id === 1
          ? ROOT_WS
          : {
              ...NODE_WS,
              folders: [
                {
                  folder_id: 10,
                  name: 'Lectures',
                  source_id: null,
                  member_count: 2,
                  rationale: null,
                  auto_assigned: false,
                },
              ],
            }
      )
    )
    renderWorkspace('/courses/3/n/5?tab=materials')
    const row = await screen.findByTitle('2 materials in this folder join this node')
    fireEvent.contextMenu(row)
    expect(
      await screen.findByRole('menuitem', { name: 'Open in library' })
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Unassign folder' }))
    await waitFor(() => expect(deallocateNodeFolder).toHaveBeenCalledWith(5, 10))
  })

  test('materials tab bulk unassign removes selected materials and folders', async () => {
    primeDefaults()
    deallocateMaterial.mockResolvedValue(undefined)
    deallocateNodeFolder.mockResolvedValue(undefined)
    nodeWorkspace.mockImplementation((id: number) =>
      Promise.resolve(
        id === 1
          ? ROOT_WS
          : {
              ...NODE_WS,
              folders: [
                {
                  folder_id: 10,
                  name: 'Lectures',
                  source_id: null,
                  member_count: 2,
                  rationale: null,
                  auto_assigned: false,
                },
              ],
            }
      )
    )
    renderWorkspace('/courses/3/n/5?tab=materials')
    const row = await screen.findByTitle('2 materials in this folder join this node')
    fireEvent.mouseDown(row)
    fireEvent.mouseDown(screen.getByText('chain-rule.pdf'), { ctrlKey: true })
    expect(screen.queryByText(/selected/i)).not.toBeInTheDocument()
    fireEvent.mouseDown(screen.getByText('chain-rule.pdf'), { button: 2 })
    fireEvent.contextMenu(screen.getByText('chain-rule.pdf'))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Unassign' }))

    await waitFor(() => expect(deallocateMaterial).toHaveBeenCalledWith(5, 7))
    await waitFor(() => expect(deallocateNodeFolder).toHaveBeenCalledWith(5, 10))
  })

  test('materials tab assign-to-node also moves selected folders', async () => {
    primeDefaults()
    allocateMaterial.mockResolvedValue(undefined)
    allocateNodeFolder.mockResolvedValue(undefined)
    nodeWorkspace.mockImplementation((id: number) =>
      Promise.resolve(
        id === 1
          ? ROOT_WS
          : {
              ...NODE_WS,
              folders: [
                {
                  folder_id: 10,
                  name: 'Lectures',
                  source_id: null,
                  member_count: 2,
                  rationale: null,
                  auto_assigned: false,
                },
              ],
            }
      )
    )
    renderWorkspace('/courses/3/n/5?tab=materials')
    const row = await screen.findByTitle('2 materials in this folder join this node')
    fireEvent.mouseDown(row)
    fireEvent.mouseDown(screen.getByText('chain-rule.pdf'), { ctrlKey: true })
    fireEvent.mouseDown(screen.getByText('chain-rule.pdf'), { button: 2 })
    fireEvent.contextMenu(screen.getByText('chain-rule.pdf'))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Assign to node…' }))
    fireEvent.click(await screen.findByRole('treeitem', { name: /Chain rule/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Assign' }))
    await waitFor(() => expect(allocateMaterial).toHaveBeenCalledWith(11, 7))
    await waitFor(() => expect(allocateNodeFolder).toHaveBeenCalledWith(11, 10))
  })

  test('materials tab bulk unassign skips folder-member materials', async () => {
    primeDefaults()
    deallocateMaterial.mockResolvedValue(undefined)
    nodeWorkspace.mockImplementation((id: number) =>
      Promise.resolve(
        id === 1
          ? ROOT_WS
          : {
              ...NODE_WS,
              materials: [NODE_WS.materials[0]],
              folders: [
                {
                  folder_id: 10,
                  name: 'Lectures',
                  source_id: null,
                  member_count: 1,
                  rationale: null,
                  auto_assigned: false,
                },
              ],
              folder_material_ids: [9],
            }
      )
    )
    renderWorkspace('/courses/3/n/5?tab=materials')
    expect(await screen.findByText('chain-rule.pdf')).toBeInTheDocument()

    fireEvent.mouseDown(screen.getByText('chain-rule.pdf'))
    fireEvent.mouseDown(screen.getByText('chain-rule.pdf'), { button: 2 })
    fireEvent.contextMenu(screen.getByText('chain-rule.pdf'))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Remove from node' }))

    await waitFor(() => expect(deallocateMaterial).toHaveBeenCalledWith(5, 7))
    expect(deallocateMaterial).not.toHaveBeenCalledWith(5, 9)
  })

  test('notes tab bulk-deletes and moves the selection to a node', async () => {
    primeDefaults()
    listNotes.mockResolvedValue({
      items: [
        {
          id: 21,
          title: 'Limits note',
          course_id: 3,
          node_id: 5,
          owner_type: 'standalone',
          owner_id: null,
          tags: [],
          pinned: false,
          updated_at: '2026-08-19T00:00:00Z',
        },
        {
          id: 22,
          title: 'Chain note',
          course_id: 3,
          node_id: 5,
          owner_type: 'standalone',
          owner_id: null,
          tags: [],
          pinned: false,
          updated_at: '2026-08-19T00:00:00Z',
        },
      ],
      next_cursor: null,
    })
    deleteNote.mockResolvedValue({ deleted_item_id: 90 })
    moveNote.mockResolvedValue(undefined)
    renderWorkspace('/courses/3/n/5?tab=notes')
    await screen.findByText('Limits note')

    fireEvent.mouseDown(screen.getByText('Limits note'))
    fireEvent.mouseDown(screen.getByText('Chain note'), { ctrlKey: true })

    fireEvent.contextMenu(screen.getByText('Limits note'))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Delete' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(deleteNote).toHaveBeenCalledWith(21))
    await waitFor(() => expect(deleteNote).toHaveBeenCalledWith(22))

    fireEvent.mouseDown(screen.getByText('Limits note'))
    fireEvent.mouseDown(screen.getByText('Chain note'), { ctrlKey: true })
    fireEvent.contextMenu(screen.getByText('Limits note'))
    fireEvent.click(await screen.findByRole('menuitem', { name: /Move to node/i }))
    fireEvent.click(await screen.findByRole('treeitem', { name: /Chain rule/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Move' }))
    await waitFor(() => expect(moveNote).toHaveBeenCalledWith(21, 11))
    await waitFor(() => expect(moveNote).toHaveBeenCalledWith(22, 11))
  })

  test('notes tab marquee drag selects the intersecting notes without a count bar', async () => {
    primeDefaults()
    listNotes.mockResolvedValue({
      items: [
        {
          id: 21,
          title: 'Limits note',
          course_id: 3,
          node_id: 5,
          owner_type: 'standalone',
          owner_id: null,
          tags: [],
          pinned: false,
          updated_at: '2026-08-19T00:00:00Z',
        },
      ],
      next_cursor: null,
    })
    const rectSpy = vi
      .spyOn(Element.prototype, 'getBoundingClientRect')
      .mockReturnValue({
        left: 0, top: 0, right: 400, bottom: 400, width: 400, height: 400, x: 0, y: 0,
        toJSON: () => ({}),
      } as DOMRect)
    renderWorkspace('/courses/3/n/5?tab=notes')
    await screen.findByText('Limits note')

    const pane = document.querySelector('[data-marquee-surface]') as HTMLElement
    fireEvent.mouseDown(pane, { clientX: 0, clientY: 0, button: 0 })
    fireEvent.mouseMove(window, { clientX: 200, clientY: 200 })
    fireEvent.mouseUp(window, { clientX: 200, clientY: 200 })

    const wrapper = screen
      .getByText('Limits note')
      .closest('[data-selectable-id]') as HTMLElement
    await waitFor(() => expect(wrapper.className).toContain('bg-primary/10'))
    expect(screen.queryByText(/selected/i)).not.toBeInTheDocument()

    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(wrapper.className).not.toContain('bg-primary/10'))
    rectSpy.mockRestore()
  })

  test('notes drag carries the whole selection when a selected note is dragged', async () => {
    primeDefaults()
    listNotes.mockResolvedValue({
      items: [
        {
          id: 21,
          title: 'Limits note',
          course_id: 3,
          node_id: 5,
          owner_type: 'standalone',
          owner_id: null,
          tags: [],
          pinned: false,
          updated_at: '2026-08-19T00:00:00Z',
        },
        {
          id: 22,
          title: 'Chain note',
          course_id: 3,
          node_id: 5,
          owner_type: 'standalone',
          owner_id: null,
          tags: [],
          pinned: false,
          updated_at: '2026-08-19T00:00:00Z',
        },
      ],
      next_cursor: null,
    })
    renderWorkspace('/courses/3/n/5?tab=notes')
    await screen.findByText('Limits note')

    fireEvent.mouseDown(screen.getByText('Limits note'))
    fireEvent.mouseDown(screen.getByText('Chain note'), { ctrlKey: true })

    const payload: Record<string, string> = {}
    const wrapper = screen
      .getByText('Limits note')
      .closest('[data-selectable-id]') as HTMLElement
    fireEvent.mouseDown(screen.getByText('Limits note'))
    fireEvent.dragStart(wrapper, {
      dataTransfer: {
        setData: (mime: string, value: string) => {
          payload[mime] = value
        },
        getData: (mime: string) => payload[mime] ?? '',
        types: ['application/x-ca-item'],
        effectAllowed: '',
      },
    })

    const item = JSON.parse(payload['application/x-ca-item']) as {
      folderIds: number[]
      materialIds: number[]
      noteIds: number[]
    }
    expect(item.noteIds).toEqual([21, 22])
  })

  test('notes drag of an unselected note carries just it and selects it', async () => {
    primeDefaults()
    listNotes.mockResolvedValue({
      items: [
        {
          id: 21,
          title: 'Limits note',
          course_id: 3,
          node_id: 5,
          owner_type: 'standalone',
          owner_id: null,
          tags: [],
          pinned: false,
          updated_at: '2026-08-19T00:00:00Z',
        },
      ],
      next_cursor: null,
    })
    renderWorkspace('/courses/3/n/5?tab=notes')
    await screen.findByText('Limits note')

    const payload: Record<string, string> = {}
    const wrapper = screen
      .getByText('Limits note')
      .closest('[data-selectable-id]') as HTMLElement
    fireEvent.dragStart(wrapper, {
      dataTransfer: {
        setData: (mime: string, value: string) => {
          payload[mime] = value
        },
        getData: (mime: string) => payload[mime] ?? '',
        types: ['application/x-ca-item'],
        effectAllowed: '',
      },
    })

    const item = JSON.parse(payload['application/x-ca-item']) as {
      folderIds: number[]
      materialIds: number[]
      noteIds: number[]
    }
    expect(item.noteIds).toEqual([21])
    await waitFor(() => expect(wrapper.className).toContain('bg-primary/10'))
  })

  test('practice tab moves selected quizzes and deletes selected exercises', async () => {
    primeDefaults()
    listQuizzes.mockResolvedValue([
      { id: 50, title: 'Node quiz', type: 'quiz', course_id: 3, node_id: 5, question_count: 4 },
    ])
    listExercises.mockResolvedValue([
      { id: 60, title: 'Drill', course_id: 3, node_id: 5, step_count: 2, difficulty: null },
    ])
    moveQuiz.mockResolvedValue(undefined)
    deleteExercise.mockResolvedValue({ deleted_item_id: 91 })
    renderWorkspace('/courses/3/n/5?tab=practice')
    await screen.findByText('Node quiz')

    fireEvent.mouseDown(screen.getByText('Node quiz'))
    fireEvent.click(screen.getAllByRole('button', { name: /Move to node/i })[0])
    fireEvent.click(await screen.findByRole('treeitem', { name: /Chain rule/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Move' }))
    await waitFor(() => expect(moveQuiz).toHaveBeenCalledWith(50, 11))

    fireEvent.mouseDown(screen.getByText('Drill'))
    fireEvent.click(screen.getAllByRole('button', { name: 'Delete' })[0])
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(deleteExercise).toHaveBeenCalledWith(60))
  })

  test('settings tab appears at the course root only and deep-links to course details', async () => {
    primeDefaults()
    const root = renderWorkspace('/courses/3?tab=settings')
    expect(await screen.findByTestId('course-settings-tab')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Title' })).toHaveValue('Calculus I')
    expect(screen.getByRole('button', { name: /save/i })).toBeDisabled()
    root.unmount()

    renderWorkspace('/courses/3/n/5')
    expect(await screen.findByRole('heading', { name: 'Derivatives' })).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Settings' })).not.toBeInTheDocument()
    expect(screen.queryByTestId('course-settings-tab')).not.toBeInTheDocument()
  })

  test('settings tab saves the course title and description', async () => {
    primeDefaults()
    updateCourse.mockResolvedValue(undefined)
    renderWorkspace('/courses/3?tab=settings')
    await screen.findByTestId('course-settings-tab')
    fireEvent.change(screen.getByRole('textbox', { name: 'Title' }), {
      target: { value: 'Analysis I' },
    })
    fireEvent.change(screen.getByRole('textbox', { name: 'Description' }), {
      target: { value: 'Limits, derivatives, integrals' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))
    await waitFor(() =>
      expect(updateCourse).toHaveBeenCalledWith(3, {
        title: 'Analysis I',
        description: 'Limits, derivatives, integrals',
      })
    )
  })

  test('settings tasks subtab lists overrides and assigns a course model', async () => {
    primeDefaults()
    listModels.mockResolvedValue([
      { id: 1, label: 'local-mini', caps: ['text'], enabled: true, missing: false },
      { id: 2, label: 'vision-pro', caps: ['text', 'vision'], enabled: true, missing: false },
    ])
    listCourseTaskDefaults.mockResolvedValue([])
    listCourseTasks.mockResolvedValue([
      {
        task: 'chat',
        description: 'Tutor chat turns',
        requires: 'text',
        model_id: null,
        fallback_model_id: null,
        model_label: null,
        fallback_model_label: null,
        global_model_label: 'global-chat',
        global_fallback_model_label: null,
      },
      {
        task: 'ocr',
        description: 'Scanned page OCR',
        requires: 'vision',
        model_id: 2,
        fallback_model_id: null,
        model_label: 'vision-pro',
        fallback_model_label: null,
        global_model_label: null,
        global_fallback_model_label: null,
      },
    ])
    assignCourseTask.mockResolvedValue({})
    renderWorkspace('/courses/3?tab=settings')
    await screen.findByTestId('course-settings-tab')
    fireEvent.click(screen.getByRole('tab', { name: 'Tasks' }))

    expect(await screen.findByText('chat')).toBeInTheDocument()
    expect(screen.getByText(/using global-chat/i)).toBeInTheDocument()

    const chatModel = screen.getByRole('combobox', { name: 'chat course model' })
    expect(chatModel).toHaveValue('')
    fireEvent.change(chatModel, { target: { value: '1' } })
    await waitFor(() =>
      expect(assignCourseTask).toHaveBeenCalledWith(3, 'chat', 1, null)
    )

    const ocrModel = screen.getByRole('combobox', { name: 'ocr course model' })
    expect(ocrModel).toHaveValue('2')
    const ocrOptions = within(ocrModel).getAllByRole('option')
    expect(ocrOptions.map((entry) => entry.textContent)).toEqual([
      '— unassigned —',
      'vision-pro',
    ])
  })
})
