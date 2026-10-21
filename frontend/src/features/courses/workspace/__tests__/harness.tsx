import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  redirect,
  RouterProvider,
} from '@tanstack/react-router'
import { render } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

import { NodeWorkspace } from '../../NodeWorkspace'
import { useChatStore } from '@/lib/chat-store'
export { useChatStore }
import { clearWindowDropTarget, getWindowDropTarget } from '@/lib/window-drop-store'
export { clearWindowDropTarget, getWindowDropTarget }

export const nodeWorkspace = vi.fn()
export const courseTree = vi.fn()
export const getCourse = vi.fn()
export const listCourses = vi.fn()
export const listNotes = vi.fn()
export const listNoteTags = vi.fn()
export const getNote = vi.fn()
export const listMaterials = vi.fn()
export const getMaterial = vi.fn()
export const getMaterialLinks = vi.fn()
export const listStudyStates = vi.fn()
export const listQuizzes = vi.fn()
export const listExercises = vi.fn()
export const listFlashcards = vi.fn()
export const dueFlashcards = vi.fn()
export const reviewFlashcard = vi.fn()
export const listChatSessions = vi.fn()
export const generateQuiz = vi.fn()
export const generateFlashcards = vi.fn()
export const createChatSession = vi.fn()
export const createNote = vi.fn()
export const addNodeConcept = vi.fn()
export const removeNodeConcept = vi.fn()
export const conceptGraph = vi.fn()
export const extractConcepts = vi.fn()
export const commitConcepts = vi.fn()
export const updateNode = vi.fn()
export const updateCourse = vi.fn()
export const addNode = vi.fn()
export const outlineDraft = vi.fn()
export const outlineCommit = vi.fn()
export const draftNodeNote = vi.fn()
export const getNodeArtifacts = vi.fn()
export const similarExercise = vi.fn()
export const drillPatterns = vi.fn()
export const updateNote = vi.fn()
export const deleteNote = vi.fn()
export const moveNote = vi.fn()
export const moveQuiz = vi.fn()
export const moveExercise = vi.fn()
export const renameQuiz = vi.fn()
export const deleteQuiz = vi.fn()
export const renameExercise = vi.fn()
export const deleteExercise = vi.fn()
export const deallocateMaterial = vi.fn()
export const deallocateNodeFolder = vi.fn()
export const uploadMaterial = vi.fn()
export const allocateMaterial = vi.fn()
export const allocateNodeFolder = vi.fn()
export const mirrorFolder = vi.fn()
export const getUnassignedMaterials = vi.fn()
export const getPlacementSuggestions = vi.fn()
export const listFolders = vi.fn()
export const browseSource = vi.fn()
export const ingestSourceFile = vi.fn()
export const createFolder = vi.fn()
export const createTextMaterial = vi.fn()
export const updateTextMaterial = vi.fn()
export const previewAiContext = vi.fn()
export const composeMaterialAsync = vi.fn()
export const getJob = vi.fn()
export const listCourseTasks = vi.fn()
export const assignCourseTask = vi.fn()
export const listCourseTaskDefaults = vi.fn()
export const assignCourseTaskDefault = vi.fn()
export const listModels = vi.fn()
export const deriveMaterialsMock = vi.fn()

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
    validateSearch: (search: Record<string, unknown>): {
      tab?: string
      note?: string
      folder?: string
    } => ({
      tab: typeof search.tab === 'string' ? search.tab : undefined,
      note: search.note === undefined ? undefined : String(search.note),
      folder: search.folder === undefined ? undefined : String(search.folder),
    }),
    component: () => <NodeWorkspace courseId="3" />,
  })
  const nodeRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/courses/$courseId/n/$nodeId',
    validateSearch: (search: Record<string, unknown>): {
      tab?: string
      note?: string
      folder?: string
    } => ({
      tab: typeof search.tab === 'string' ? search.tab : undefined,
      note: search.note === undefined ? undefined : String(search.note),
      folder: search.folder === undefined ? undefined : String(search.folder),
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

export const routerHolder: { current: WorkspaceRouter | null } = { current: null }
export const navigateMock = vi.fn((options: NavigateCall) => {
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

vi.mock('@/features/notes/LazyNoteEditor', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/notes/LazyNoteEditor')>()
  return {
    LazyNoteEditor: ({
      noteId,
      onClose,
      onRequestClose,
    }: {
      noteId: string
      onClose?: () => void
      onRequestClose?: () => void
    }) =>
      onClose ? (
        <actual.LazyNoteEditor noteId={noteId} onClose={onClose} />
      ) : (
        <div data-testid="study-note-editor-stub">
          note:{noteId}
          <button type="button" onClick={() => onRequestClose?.()}>
            Close notes
          </button>
        </div>
      ),
  }
})

vi.mock('@/lib/api', async (importOriginal) => {  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    nodeWorkspace: (id: string) => nodeWorkspace(id),
    courseTree: (id: string) => courseTree(id),
    getCourse: (id: string) => getCourse(id),
    listCourses: () => listCourses(),
    listNotes: (...args: unknown[]) => listNotes(...(args as [])),
    listNoteTags: (...args: unknown[]) => listNoteTags(...(args as [])),
    getNote: (id: string) => getNote(id),
    listMaterials: (...args: unknown[]) => listMaterials(...(args as [])),
    getMaterial: (id: string) => getMaterial(id),
    getMaterialLinks: (id: string) => getMaterialLinks(id),
    listStudyStates: () => listStudyStates(),
    listQuizzes: (...args: unknown[]) => listQuizzes(...(args as [])),
    listExercises: (...args: unknown[]) => listExercises(...(args as [])),
    listFlashcards: (...args: unknown[]) => listFlashcards(...(args as [])),
    dueFlashcards: (...args: unknown[]) => dueFlashcards(...(args as [])),
    reviewFlashcard: (cardId: string, rating: number) => reviewFlashcard(cardId, rating),
    listChatSessions: (nodeId?: string) => listChatSessions(nodeId),
    generateQuiz: (body: unknown) => generateQuiz(body),
    generateFlashcards: (body: unknown) => generateFlashcards(body),
    createChatSession: (...args: unknown[]) =>
      createChatSession(...(args as [number | null, number | null, string])),
    createNote: (body: unknown) => createNote(body),
    addNodeConcept: (...args: unknown[]) => addNodeConcept(...(args as [number, number])),
    removeNodeConcept: (...args: unknown[]) => removeNodeConcept(...(args as [number, number])),
    conceptGraph: (id: string) => conceptGraph(id),
    extractConcepts: (id: string) => extractConcepts(id),
    commitConcepts: (...args: unknown[]) => commitConcepts(...(args as [])),
    updateNode: (...args: unknown[]) => updateNode(...(args as [number, object])),
    updateCourse: (...args: unknown[]) => updateCourse(...(args as [number, object])),
    addNode: (...args: unknown[]) => addNode(...(args as [number, number, string])),
    outlineDraft: (id: string) => outlineDraft(id),
    outlineCommit: (id: string, chapters: unknown) => outlineCommit(id, chapters),
    draftNodeNote: (id: string) => draftNodeNote(id),
    getNodeArtifacts: (id: string, kind?: string) => getNodeArtifacts(id, kind),
    similarExercise: (id: string) => similarExercise(id),
    drillPatterns: () => drillPatterns(),
    updateNote: (...args: unknown[]) => updateNote(...(args as [number, object])),
    deleteNote: (id: string) => deleteNote(id),
    moveNote: (id: string, nodeId: string | null) => moveNote(id, nodeId),
    moveQuiz: (id: string, nodeId: string | null) => moveQuiz(id, nodeId),
    moveExercise: (id: string, nodeId: string | null) => moveExercise(id, nodeId),
    renameQuiz: (...args: unknown[]) => renameQuiz(...(args as [number, string])),
    deleteQuiz: (id: string) => deleteQuiz(id),
    renameExercise: (...args: unknown[]) => renameExercise(...(args as [number, string])),
    deleteExercise: (id: string) => deleteExercise(id),
    deallocateMaterial: (...args: unknown[]) => deallocateMaterial(...(args as [number, number])),
    deallocateNodeFolder: (...args: unknown[]) =>
      deallocateNodeFolder(...(args as [number, number])),
    uploadMaterial: (...args: unknown[]) => uploadMaterial(...(args as [])),
    allocateMaterial: (...args: unknown[]) => allocateMaterial(...(args as [number, number])),
    allocateNodeFolder: (...args: unknown[]) =>
      allocateNodeFolder(...(args as [number, number])),
    mirrorFolder: (...args: unknown[]) => mirrorFolder(...(args as [number, number])),
    getUnassignedMaterials: (...args: unknown[]) =>
      getUnassignedMaterials(...(args as [number])),
    getPlacementSuggestions: (...args: unknown[]) =>
      getPlacementSuggestions(...(args as [number, number[]])),
    listFolders: (...args: unknown[]) => listFolders(...(args as [number?])),
    browseSource: (...args: unknown[]) =>
      browseSource(...(args as [number, string])),
    ingestSourceFile: (...args: unknown[]) =>
      ingestSourceFile(...(args as [number, string])),
    createFolder: (...args: unknown[]) => createFolder(...(args as [string, number | null, number])),
    createTextMaterial: (...args: unknown[]) => createTextMaterial(...(args as [])),
    updateTextMaterial: (...args: unknown[]) => updateTextMaterial(...(args as [])),
    previewAiContext: (courseId: string, spec: unknown) => previewAiContext(courseId, spec),
    composeMaterialAsync: (body: unknown) => composeMaterialAsync(body),
    getJob: (jobId: string) => getJob(jobId),
    listCourseTasks: (courseId: string) => listCourseTasks(courseId),
    assignCourseTask: (...args: unknown[]) =>
      assignCourseTask(...(args as [number, string, number | null, number | null])),
    listCourseTaskDefaults: (courseId: string) => listCourseTaskDefaults(courseId),
    assignCourseTaskDefault: (...args: unknown[]) =>
      assignCourseTaskDefault(
        ...(args as [number, string, number | null, number | null])
      ),
    listModels: () => listModels(),
    deriveMaterials: (...args: unknown[]) =>
      deriveMaterialsMock(...(args as [number[]])),
  }
})

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return {
    ...actual,
    useNavigate: () => navigateMock,
  }
})

export const TREE = [
  {
    id: '1',
    title: 'Calculus I',
    summary: null,
    objectives: [],
    order_idx: 0,
    depth: 0,
    is_root: true,
    children: [
      {
        id: '5',
        title: 'Derivatives',
        summary: null,
        objectives: [],
        order_idx: 0,
        depth: 1,
        is_root: false,
        children: [
          {
            id: '11',
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

export const ROOT_WS = {
  node: {
    id: '1',
    course_id: '3',
    course_title: 'Calculus I',
    title: 'Calculus I',
    summary: 'The course root',
    objectives: [],
    depth: 0,
    is_root: true,
    parent_id: null,
    breadcrumb: [{ id: '1', title: 'Calculus I', depth: 0 }],
  },
  children: [
    { id: '5', title: 'Derivatives', depth: 1, order_idx: 0, objectives: [], summary: null },
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

export const NODE_WS = {
  node: {
    id: '5',
    course_id: '3',
    course_title: 'Calculus I',
    title: 'Derivatives',
    summary: 'Rates of change',
    objectives: ['Compute derivatives'],
    depth: 1,
    is_root: false,
    parent_id: '1',
    breadcrumb: [
      { id: '1', title: 'Calculus I', depth: 0 },
      { id: '5', title: 'Derivatives', depth: 1 },
    ],
  },
  children: [
    {
      id: '11',
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
      material_id: '7',
      title: 'chain-rule.pdf',
      kind: 'pdf',
      status: 'ready',
      read_status: 'reading',
      progress: 0.5,
      rationale: null,
      auto_assigned: false,
      confidence: null,
      reextract_modes: ['auto', 'text', 'ocr'],
      has_extraction: true,
      via_folder_id: null,
      via_folder_name: null,
    },
  ],
  child_materials: {
    11: [
      {
        material_id: '8',
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
    { id: '71', name: 'chain rule', direct: true, node_ids: ['5'] },
    { id: '72', name: 'limits', direct: false, node_ids: ['11'] },
  ],
}

export const DRAFT = {
  chapters: [
    {
      title: 'Limits',
      summary: 'Approaching values',
      sections: [
        { title: 'Continuity', objectives: [], material_ids: ['4'], rationale: null, confidence: 0.9 },
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

export function renderWorkspace(initialUrl: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = buildRouter(initialUrl)
  routerHolder.current = router
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}

export function primeDefaults() {
  nodeWorkspace.mockImplementation((id: string) =>
    Promise.resolve(id === '1' ? ROOT_WS : NODE_WS)
  )
  courseTree.mockResolvedValue(TREE)
  listFolders.mockResolvedValue([])
  browseSource.mockResolvedValue({
    source_id: '77',
    label: 'Source',
    path: '/src',
    subdir: '',
    missing_target: false,
    enabled: true,
    scan_interval_sec: null,
    last_scan_error: null,
    last_scanned_at: null,
    subdirs: [],
    materials: [],
    uningested: [],
  })
  ingestSourceFile.mockResolvedValue({ material_id: '1', job_id: null, deduped: false })
  createFolder.mockImplementation(async (name: string, parentId: string | null) => ({
    id: String(900 + createFolder.mock.calls.length),
    name,
    path: name,
    course_id: '3',
    parent_id: parentId,
    source_id: null,
    created_at: '2026-08-21T00:00:00Z',
  }))
  listCourses.mockResolvedValue([
    {
      id: '3',
      title: 'Calculus I',
      subject: null,
      level: null,
      description: null,
      color: '#3366cc',
      archived_at: null,
      material_count: 1,
    },
  ])
  getCourse.mockResolvedValue({
    id: '3',
    title: 'Calculus I',
    subject: null,
    level: null,
    description: null,
    color: '#3366cc',
    archived_at: null,
    material_count: 1,
    origin: 'manual',
    hidden: false,
  })
  listNotes.mockResolvedValue({ items: [], next_cursor: null })
  getUnassignedMaterials.mockResolvedValue({ count: 0, materials: [] })
  getPlacementSuggestions.mockResolvedValue({ suggestions: [] })
  getNodeArtifacts.mockResolvedValue({ cheat_sheet: null, reviews: [] })
  listNoteTags.mockResolvedValue([])
  getNote.mockImplementation((id: string) =>
    Promise.resolve({
      id,
      title: `Note detail ${id}`,
      course_id: '3',
      node_id: '5',
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
  getMaterial.mockImplementation((id: string) =>
    Promise.resolve({
      material: {
        id,
        title: 'chain-rule.pdf',
        kind: 'pdf',
        status: 'ready',
        course_id: '3',
        folder_id: null,
        created_at: '2026-08-19T00:00:00Z',
        provenance: null,
      },
    })
  )
  getMaterialLinks.mockResolvedValue([
    {
      node_id: '5',
      owner_title: 'Derivatives',
      rationale: null,
      breadcrumb: [
        { id: '1', title: 'Calculus I' },
        { id: '5', title: 'Derivatives' },
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
  similarExercise.mockResolvedValue({ id: '61', title: 'Similar', step_count: 3 })
  drillPatterns.mockResolvedValue([])
  previewAiContext.mockResolvedValue({
    stats: { materials: [], chunks: [], notes: [], concepts: [], hints: 0 },
    rendered: '',
  })
  composeMaterialAsync.mockResolvedValue({ job_id: '3' })
  getJob.mockResolvedValue({
    id: '3',
    type: 'compose',
    status: 'done',
    progress: 100,
    stage: 'done',
    error: null,
    material_id: '99',
    retriable: false,
    stale: false,
    label: 'compose',
    created_at: null,
    started_at: null,
    finished_at: null,
  })
  useChatStore.setState({ open: false, session: null })
}

afterEach(() => {
  clearWindowDropTarget()
})

