import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, beforeEach, expect, test, vi } from 'vitest'

import { GenerateDialog } from './GenerateDialog'

const generateQuiz = vi.fn()
const generateExercise = vi.fn()
const generateFlashcards = vi.fn()
const composeMaterialAsync = vi.fn()
const getJob = vi.fn()
const cancelJob = vi.fn()
const getMaterial = vi.fn()
const previewAiContext = vi.fn()
const listMaterials = vi.fn()
const listNotes = vi.fn()
const nodeWorkspace = vi.fn()
const conceptGraph = vi.fn()
const listCourses = vi.fn()
const getNodeArtifacts = vi.fn()
const getUnassignedMaterials = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    generateQuiz: (body: unknown) => generateQuiz(body),
    generateExercise: (body: unknown) => generateExercise(body),
    generateFlashcards: (body: unknown) => generateFlashcards(body),
    composeMaterialAsync: (body: unknown) => composeMaterialAsync(body),
    getJob: (jobId: number) => getJob(jobId),
    cancelJob: (jobId: number) => cancelJob(jobId),
    getMaterial: (id: number) => getMaterial(id),
    previewAiContext: (courseId: number, spec: unknown) => previewAiContext(courseId, spec),
    listMaterials: (...args: unknown[]) => listMaterials(...args),
    listNotes: (...args: unknown[]) => listNotes(...args),
    nodeWorkspace: (nodeId: number) => nodeWorkspace(nodeId),
    conceptGraph: (courseId: number) => conceptGraph(courseId),
    listCourses: () => listCourses(),
    getNodeArtifacts: (id: number, kind?: string) => getNodeArtifacts(id, kind),
    getUnassignedMaterials: (courseId: number) => getUnassignedMaterials(courseId),
  }
})

const testHooks = vi.hoisted(() => ({
  materialIds: [7],
  noteEntries: [{ id: 11, title: 'My note' }],
}))

vi.mock('@/features/courses/MaterialPickerDialog', () => ({
  MaterialPickerDialog: (props: { onSelect?: (ids: number[]) => void }) => (
    <button type="button" onClick={() => props.onSelect?.(testHooks.materialIds)}>
      confirm-pick
    </button>
  ),
}))

vi.mock('@/features/notes/NotePickerDialog', () => ({
  NotePickerDialog: (props: {
    onSelect?: (entries: Array<{ id: number; title: string }>) => void
  }) => (
    <button type="button" onClick={() => props.onSelect?.(testHooks.noteEntries)}>
      confirm-notes
    </button>
  ),
}))

const PREVIEW = {
  stats: {
    materials: [
      { id: 1, title: 'Lecture 1' },
      { id: 2, title: 'Lecture 2' },
    ],
    chunks: [{ material_id: 1, title: 'Lecture 1' }],
    notes: [],
    concepts: [],
    hints: 1,
    approx_chars: 800,
    retrieval_query: null,
  },
  rendered: 'Sources from the course material:\n[1] (Lecture 1) derivative rules',
}

const WORKSPACE = {
  node: {
    id: 5,
    course_id: 3,
    course_title: 'Calculus',
    title: 'Ch',
    summary: null,
    objectives: [],
    ai_hint: 'node hint',
    depth: 1,
    is_root: false,
    parent_id: 1,
    breadcrumb: [],
  },
  children: [],
  materials: [{ material_id: 1, title: 'Lecture 1', kind: 'doc', status: 'ready', read_status: 'unread', progress: 0 }],
  child_materials: {
    6: [{ material_id: 2, title: 'Lecture 2', kind: 'doc', status: 'ready', read_status: 'unread', progress: 0 }],
  },
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

function renderDialog(props: {
  task: 'quiz' | 'exercise' | 'flashcards' | 'compose' | 'practice'
  courseId?: number | null
  scopeNodeId?: number
  rootNodeId?: number
  onSuccess?: (result: unknown) => void
}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <GenerateDialog
        task={props.task}
        courseId={props.courseId ?? 3}
        scopeNodeId={props.scopeNodeId}
        rootNodeId={props.rootNodeId}
        onClose={() => undefined}
        onSuccess={props.onSuccess ?? (() => undefined)}
      />
    </QueryClientProvider>
  )
}

describe('GenerateDialog', () => {
  beforeEach(() => {
    generateQuiz.mockReset().mockResolvedValue({ id: 9, question_count: 8 })
    generateExercise.mockReset().mockResolvedValue({ id: 21, step_count: 3 })
    generateFlashcards.mockReset().mockResolvedValue([])
    composeMaterialAsync.mockReset().mockResolvedValue({ job_id: 5 })
    getJob.mockReset().mockResolvedValue({
      id: 5,
      type: 'compose',
      status: 'done',
      progress: 100,
      stage: 'done',
      error: null,
      material_id: 77,
      retriable: false,
      stale: false,
      label: 'compose',
      created_at: null,
      started_at: null,
      finished_at: null,
    })
    cancelJob.mockReset().mockResolvedValue({})
    getMaterial.mockReset().mockResolvedValue({
      material: { id: 77, title: 'Guide', provenance: { source: 'ai-composed' } },
      extraction: null,
      index_card: null,
      drawings: [],
    })
    previewAiContext.mockReset().mockResolvedValue(PREVIEW)
    listMaterials.mockReset().mockResolvedValue([
      { id: 1, title: 'Lecture 1' },
      { id: 2, title: 'Lecture 2' },
      { id: 7, title: 'Unlinked' },
    ])
    listNotes.mockReset().mockResolvedValue({
      items: [{ id: 11, title: 'My note' }],
      next_cursor: null,
    })
    nodeWorkspace.mockReset().mockResolvedValue(WORKSPACE)
    conceptGraph.mockReset().mockResolvedValue({
      concepts: [{ id: 31, name: 'chain rule', description: null, aliases: [], nodes: [] }],
      links: [],
    })
    listCourses.mockReset().mockResolvedValue([])
    getNodeArtifacts.mockReset().mockResolvedValue({
      cheat_sheet: null,
      reviews: [],
      artifact: null,
    })
    getUnassignedMaterials.mockReset().mockResolvedValue({ count: 0, materials: [] })
    testHooks.materialIds = [7]
    testHooks.noteEntries = [{ id: 11, title: 'My note' }]
  })

  test('compose preset sends kind, title, instructions and scope context', async () => {
    renderDialog({ task: 'compose', scopeNodeId: 5, rootNodeId: 1 })
    const kindSelect = await screen.findByLabelText('Document kind')
    fireEvent.change(kindSelect, { target: { value: 'summary_sheet' } })
    const titleInput = screen.getByPlaceholderText('Title (optional)')
    fireEvent.change(titleInput, { target: { value: 'Limits cheat sheet' } })
    const instructions = screen.getByPlaceholderText('Instructions for the AI (optional)...')
    fireEvent.change(instructions, { target: { value: 'compact formulas only' } })
    const submit = screen.getByRole('button', { name: /compose/i })
    fireEvent.click(submit)
    await waitFor(() => expect(composeMaterialAsync).toHaveBeenCalled())
    expect(composeMaterialAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        course_id: 3,
        kind: 'summary_sheet',
        title: 'Limits cheat sheet',
        instructions: 'compact formulas only',
        node_id: 5,
      })
    )
  })

  test('compose with an existing artifact shows the banner and regenerates', async () => {
    getNodeArtifacts.mockResolvedValue({
      cheat_sheet: null,
      reviews: [],
      artifact: { material_id: 77, title: 'Derivatives — study guide' },
    })
    renderDialog({ task: 'compose', scopeNodeId: 5, rootNodeId: 1 })
    expect(
      await screen.findByText(/Derivatives — study guide/)
    ).toBeInTheDocument()
    const openLink = screen.getByRole('link', { name: /open existing/i })
    expect(openLink).toHaveAttribute('href', '/library/77')

    const submit = screen.getByRole('button', { name: /regenerate/i })
    fireEvent.click(submit)
    await waitFor(() => expect(composeMaterialAsync).toHaveBeenCalled())
    expect(composeMaterialAsync).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'study_guide', regenerate: true })
    )
  })

  test('compose result names a coverage shortfall before closing', async () => {
    const onSuccess = vi.fn()
    getMaterial.mockResolvedValue({
      material: {
        id: 77,
        title: 'Guide',
        provenance: {
          source: 'ai-composed',
          coverage: { total: 14, covered: 8, missing_ids: [1, 2, 3] },
        },
      },
      extraction: null,
      index_card: null,
      drawings: [],
    })
    renderDialog({ task: 'compose', scopeNodeId: 5, rootNodeId: 1, onSuccess })
    fireEvent.click(await screen.findByRole('button', { name: /compose/i }))
    expect(
      await screen.findByTestId('coverage-note')
    ).toHaveTextContent("Built from 8 of 14 materials — 6 weren't retrieved.")
    expect(screen.queryByTestId('needs-review-warning')).not.toBeInTheDocument()
    expect(onSuccess).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /close/i }))
    await waitFor(() => expect(onSuccess).toHaveBeenCalled())
    expect(onSuccess.mock.calls[0][0]).toMatchObject({ id: 77 })
  })

  test('compose result stays silent when every material was retrieved', async () => {
    getMaterial.mockResolvedValue({
      material: {
        id: 77,
        title: 'Guide',
        provenance: {
          source: 'ai-composed',
          coverage: { total: 14, covered: 14, missing_ids: [] },
        },
      },
      extraction: null,
      index_card: null,
      drawings: [],
    })
    renderDialog({ task: 'compose', scopeNodeId: 5, rootNodeId: 1 })
    fireEvent.click(await screen.findByRole('button', { name: /compose/i }))
    await screen.findByText(/"Guide" is ready\./)
    expect(screen.queryByTestId('coverage-note')).not.toBeInTheDocument()
    expect(screen.queryByTestId('needs-review-warning')).not.toBeInTheDocument()
  })

  test('compose result flags needs_review from provenance', async () => {
    getMaterial.mockResolvedValue({
      material: {
        id: 77,
        title: 'Formulas',
        provenance: { source: 'ai-composed', needs_review: true },
      },
      extraction: null,
      index_card: null,
      drawings: [],
    })
    renderDialog({ task: 'compose', scopeNodeId: 5, rootNodeId: 1 })
    fireEvent.click(await screen.findByRole('button', { name: /compose/i }))
    expect(await screen.findByTestId('needs-review-warning')).toBeInTheDocument()
    expect(screen.queryByTestId('coverage-note')).not.toBeInTheDocument()
  })

  test('compose runs as a job with live progress before the result', async () => {
    let polls = 0
    getJob.mockImplementation(async () => {
      polls += 1
      if (polls <= 2) {
        return {
          id: 5,
          type: 'compose',
          status: 'running',
          progress: 42,
          stage: 'compose',
          error: null,
          material_id: null,
          retriable: false,
          stale: false,
          label: 'compose',
          created_at: null,
          started_at: null,
          finished_at: null,
        }
      }
      return {
        id: 5,
        type: 'compose',
        status: 'done',
        progress: 100,
        stage: 'done',
        error: null,
        material_id: 77,
        retriable: false,
        stale: false,
        label: 'compose',
        created_at: null,
        started_at: null,
        finished_at: null,
      }
    })
    renderDialog({ task: 'compose', scopeNodeId: 5, rootNodeId: 1 })
    fireEvent.click(await screen.findByRole('button', { name: /compose/i }))
    expect(await screen.findByTestId('compose-progress')).toHaveTextContent('42%')
    const cancelButtons = screen.getAllByRole('button', { name: /cancel/i })
    expect(cancelButtons[cancelButtons.length - 1]).toBeInTheDocument()
    expect(await screen.findByText(/"Guide" is ready\./)).toBeInTheDocument()
    expect(screen.queryByTestId('compose-progress')).not.toBeInTheDocument()
    expect(composeMaterialAsync).toHaveBeenCalledWith(
      expect.objectContaining({ course_id: 3, kind: 'study_guide' })
    )
  })

  test('compose can be cancelled while queued and reports it honestly', async () => {
    let cancelled = false
    cancelJob.mockImplementation(async () => {
      cancelled = true
      return { id: 5, status: 'cancelled' }
    })
    getJob.mockImplementation(async () => ({
      id: 5,
      type: 'compose',
      status: cancelled ? 'cancelled' : 'queued',
      progress: 0,
      stage: null,
      error: cancelled ? 'cancelled by user' : null,
      material_id: null,
      retriable: false,
      stale: false,
      label: 'compose',
      created_at: null,
      started_at: null,
      finished_at: null,
    }))
    renderDialog({ task: 'compose', scopeNodeId: 5, rootNodeId: 1 })
    fireEvent.click(await screen.findByRole('button', { name: /compose/i }))
    await screen.findByTestId('compose-progress')
    const cancelButtons = screen.getAllByRole('button', { name: /cancel/i })
    fireEvent.click(cancelButtons[cancelButtons.length - 1])
    expect(cancelJob).toHaveBeenCalledWith(5)
    expect(await screen.findByText(/Composition cancelled\./)).toBeInTheDocument()
  })

  test('unassigned materials notice stays opt-in and forwards the flag', async () => {
    getUnassignedMaterials.mockResolvedValue({
      count: 3,
      materials: [{ id: 41, title: 'Orphan' }],
    })
    getMaterial.mockResolvedValue({
      material: { id: 77, title: 'Guide', provenance: { source: 'ai-composed' } },
      extraction: null,
      index_card: null,
      drawings: [],
    })
    renderDialog({ task: 'compose', scopeNodeId: 5, rootNodeId: 1 })
    expect(
      await screen.findByText(/3 materials in this course are not placed/i)
    ).toBeInTheDocument()
    const link = screen.getByRole('link', { name: /place them first/i })
    expect(link).toHaveAttribute('href', '/courses/3?tab=materials')

    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: /compose/i }))
    await waitFor(() => expect(composeMaterialAsync).toHaveBeenCalled())
    expect(composeMaterialAsync).toHaveBeenCalledWith(
      expect.objectContaining({ include_unassigned: true })
    )
  })

  test('unassigned notice defaults off and hides at course scope', async () => {
    getUnassignedMaterials.mockResolvedValue({
      count: 3,
      materials: [{ id: 41, title: 'Orphan' }],
    })
    getMaterial.mockResolvedValue({
      material: { id: 77, title: 'Guide', provenance: { source: 'ai-composed' } },
      extraction: null,
      index_card: null,
      drawings: [],
    })
    renderDialog({ task: 'compose', scopeNodeId: 5, rootNodeId: 1 })
    expect(
      await screen.findByText(/3 materials in this course are not placed/i)
    ).toBeInTheDocument()
    expect(screen.getByRole('checkbox')).not.toBeChecked()

    fireEvent.change(screen.getByLabelText('Scope'), {
      target: { value: 'course' },
    })
    await waitFor(() =>
      expect(
        screen.queryByText(/not placed at any topic/i)
      ).not.toBeInTheDocument()
    )

    fireEvent.change(screen.getByLabelText('Scope'), {
      target: { value: 'subtree' },
    })
    expect(
      await screen.findByText(/3 materials in this course are not placed/i)
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /compose/i }))
    await waitFor(() => expect(composeMaterialAsync).toHaveBeenCalled())
    expect(composeMaterialAsync).toHaveBeenCalledWith(
      expect.not.objectContaining({ include_unassigned: true })
    )
  })

  test('quiz preset at a node: scope, preview, and excluded materials flow to the request', async () => {
    renderDialog({ task: 'quiz', scopeNodeId: 5, rootNodeId: 1 })
    expect(await screen.findByLabelText('Scope')).toBeInTheDocument()

    await waitFor(() =>
      expect(previewAiContext).toHaveBeenCalledWith(
        3,
        expect.objectContaining({ node_id: 5, scope: 'subtree' })
      )
    )
    expect(
      screen.getByText(/Materials: 2 · Excerpts: 1 · Notes: 0 · Concepts: 0 · Instructions: 1/)
    ).toBeInTheDocument()
    expect(
      screen.getByText(/all 2 materials in this scope are included/i)
    ).toBeInTheDocument()

    testHooks.materialIds = [1]
    fireEvent.click(screen.getByRole('button', { name: /exclude from context/i }))
    fireEvent.click(await screen.findByRole('button', { name: /confirm-pick/i }))
    expect(
      screen.getByRole('button', { name: /re-include lecture 1/i })
    ).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Scope'), { target: { value: 'course' } })
    fireEvent.click(screen.getByRole('button', { name: /generate quiz/i }))
    await waitFor(() => expect(generateQuiz).toHaveBeenCalled())
    expect(generateQuiz).toHaveBeenCalledWith(
      expect.objectContaining({
        course_id: 3,
        node_id: 1,
        scope: 'course',
        exclude_material_ids: [1],
      })
    )
  })

  test('opting into an out-of-scope material sends include_material_ids', async () => {
    renderDialog({ task: 'exercise', scopeNodeId: 5, rootNodeId: 1 })
    await screen.findByLabelText('Scope')
    fireEvent.click(screen.getByRole('button', { name: /add material/i }))
    fireEvent.click(await screen.findByRole('button', { name: /confirm-pick/i }))
    fireEvent.click(screen.getByRole('button', { name: /generate exercise/i }))
    await waitFor(() => expect(generateExercise).toHaveBeenCalled())
    expect(generateExercise).toHaveBeenCalledWith(
      expect.objectContaining({
        node_id: 5,
        scope: 'subtree',
        include_material_ids: [7],
      })
    )
  })

  test('notes and one-time hint are attached as context', async () => {
    renderDialog({ task: 'quiz', scopeNodeId: 5, rootNodeId: 1 })
    await screen.findByLabelText('Scope')
    fireEvent.click(screen.getByRole('button', { name: /add note/i }))
    fireEvent.click(await screen.findByRole('button', { name: /confirm-notes/i }))
    expect(screen.getByRole('button', { name: /remove my note/i })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/one-time instructions/i), {
      target: { value: 'prefer numeric answers' },
    })
    fireEvent.click(screen.getByRole('button', { name: /generate quiz/i }))
    await waitFor(() => expect(generateQuiz).toHaveBeenCalled())
    expect(generateQuiz).toHaveBeenCalledWith(
      expect.objectContaining({
        note_ids: [11],
        context_hint: 'prefer numeric answers',
      })
    )
  })

  test('at the root there is no scope picker and course scope is used', async () => {
    renderDialog({ task: 'quiz', scopeNodeId: 1, rootNodeId: 1 })
    expect(await screen.findByPlaceholderText(/topic/i)).toBeInTheDocument()
    expect(screen.queryByLabelText('Scope')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /generate quiz/i }))
    await waitFor(() => expect(generateQuiz).toHaveBeenCalled())
    expect(generateQuiz).toHaveBeenCalledWith(
      expect.objectContaining({ node_id: 1, scope: 'course' })
    )
  })

  test('flashcards preset shows sources and sends the hint', async () => {
    renderDialog({ task: 'flashcards' })
    const sourceSelect = await screen.findByLabelText(/source/i)
    expect(sourceSelect).toBeInTheDocument()
    expect(screen.queryByLabelText('Scope')).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/one-time instructions/i), {
      target: { value: 'keep them short' },
    })
    fireEvent.click(screen.getByRole('button', { name: /generate cards/i }))
    await waitFor(() => expect(generateFlashcards).toHaveBeenCalled())
    expect(generateFlashcards).toHaveBeenCalledWith(
      expect.objectContaining({
        source: 'mistakes',
        course_id: 3,
        context_hint: 'keep them short',
      })
    )
  })

  test('preview errors are tolerated', async () => {
    previewAiContext.mockRejectedValue(new Error('boom'))
    renderDialog({ task: 'quiz', scopeNodeId: 5, rootNodeId: 1 })
    expect(await screen.findByLabelText('Scope')).toBeInTheDocument()
    expect(await screen.findByText(/nothing will be sent/i)).toBeInTheDocument()
  })

  test('practice mode generates a quiz with selected question types and shuffle', async () => {
    renderDialog({ task: 'practice', scopeNodeId: 5, rootNodeId: 1 })
    fireEvent.click(await screen.findByRole('button', { name: /single choice/i }))
    fireEvent.click(screen.getByRole('button', { name: /shuffle/i }))
    fireEvent.click(screen.getByRole('button', { name: /generate practice/i }))
    await waitFor(() => expect(generateQuiz).toHaveBeenCalled())
    expect(generateQuiz).toHaveBeenCalledWith(
      expect.objectContaining({
        question_types: ['multi', 'truefalse', 'text', 'numeric', 'equation', 'numberline', 'table_fill', 'composite', 'graph_read', 'code'],
        shuffle: true,
        course_id: 3,
      })
    )
    expect(generateExercise).not.toHaveBeenCalled()
  })

  test('practice mode mixes quiz types and exercise kinds', async () => {
    renderDialog({ task: 'practice', scopeNodeId: 5, rootNodeId: 1 })
    fireEvent.click(await screen.findByRole('button', { name: /^matching pairs$/i }))
    fireEvent.click(screen.getByRole('button', { name: /generate practice/i }))
    await waitFor(() => expect(generateQuiz).toHaveBeenCalled())
    await waitFor(() => expect(generateExercise).toHaveBeenCalled())
    expect(generateExercise).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'matching', course_id: 3 })
    )
  })

  test('practice mode disables generate when nothing is selected', async () => {
    renderDialog({ task: 'practice', scopeNodeId: 5, rootNodeId: 1 })
    const allTypes = await screen.findAllByRole('button', { name: /single choice|multiple select|true \/ false|typed answer|numeric|equation|number line|table fill|multi-part|graph|code/i })
    for (const chip of allTypes) {
      fireEvent.click(chip)
    }
    const generate = screen.getByRole('button', { name: /generate practice/i })
    expect(generate).toBeDisabled()
  })

  test('practice mode sends quiz when no exercise kinds chosen and vice versa', async () => {
    renderDialog({ task: 'practice', scopeNodeId: 5, rootNodeId: 1 })
    const allTypes = await screen.findAllByRole('button', { name: /single choice|multiple select|true \/ false|typed answer|numeric|equation|number line|table fill|multi-part|graph|code/i })
    for (const chip of allTypes) {
      fireEvent.click(chip)
    }
    fireEvent.click(screen.getByRole('button', { name: /^matching pairs$/i }))
    fireEvent.click(screen.getByRole('button', { name: /generate practice/i }))
    await waitFor(() => expect(generateExercise).toHaveBeenCalled())
    expect(generateQuiz).not.toHaveBeenCalled()
  })

  test('practice mode chip info buttons open a details popover', async () => {
    renderDialog({ task: 'practice', scopeNodeId: 5, rootNodeId: 1 })
    const infos = await screen.findAllByRole('button', { name: 'Details' })
    expect(infos.length).toBeGreaterThan(6)
    fireEvent.click(infos[0])
    expect(screen.getByRole('dialog', { name: 'Details' })).toBeInTheDocument()
  })

  test('practice mode field info buttons explain each control', async () => {
    renderDialog({ task: 'practice', scopeNodeId: 5, rootNodeId: 1 })
    fireEvent.click(await screen.findByRole('button', { name: /shuffle/i }))
    const labels = screen.getAllByText('Shuffle')
    const group = labels[labels.length - 1].closest('.group') as HTMLElement
    const info = group.querySelector('button[aria-label="Details"]') as HTMLButtonElement
    expect(info).not.toBeNull()
    fireEvent.click(info)
    expect(screen.getByRole('dialog', { name: 'Details' })).toBeInTheDocument()
  })

  test('an added material chip can be removed again', async () => {
    renderDialog({ task: 'exercise', scopeNodeId: 5, rootNodeId: 1 })
    await screen.findByLabelText('Scope')
    fireEvent.click(screen.getByRole('button', { name: /add material/i }))
    fireEvent.click(await screen.findByRole('button', { name: /confirm-pick/i }))
    const chip = screen.getByRole('button', { name: /remove unlinked/i })
    expect(chip).toBeInTheDocument()
    fireEvent.click(chip)
    fireEvent.click(screen.getByRole('button', { name: /generate exercise/i }))
    await waitFor(() => expect(generateExercise).toHaveBeenCalled())
    expect(generateExercise).toHaveBeenCalledWith(
      expect.not.objectContaining({ include_material_ids: expect.anything() })
    )
  })

  test('an excluded material chip can be re-included', async () => {
    renderDialog({ task: 'quiz', scopeNodeId: 5, rootNodeId: 1 })
    await screen.findByLabelText('Scope')
    testHooks.materialIds = [1]
    fireEvent.click(
      await screen.findByRole('button', { name: /exclude from context/i })
    )
    fireEvent.click(await screen.findByRole('button', { name: /confirm-pick/i }))
    const chip = screen.getByRole('button', { name: /re-include lecture 1/i })
    fireEvent.click(chip)
    fireEvent.click(screen.getByRole('button', { name: /generate quiz/i }))
    await waitFor(() => expect(generateQuiz).toHaveBeenCalled())
    expect(generateQuiz).toHaveBeenCalledWith(
      expect.not.objectContaining({ exclude_material_ids: expect.anything() })
    )
  })

  test('a note chip can be removed from the context', async () => {
    renderDialog({ task: 'quiz', scopeNodeId: 5, rootNodeId: 1 })
    await screen.findByLabelText('Scope')
    fireEvent.click(screen.getByRole('button', { name: /add note/i }))
    fireEvent.click(await screen.findByRole('button', { name: /confirm-notes/i }))
    fireEvent.click(screen.getByRole('button', { name: /remove my note/i }))
    expect(screen.queryByRole('button', { name: /remove my note/i })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /generate quiz/i }))
    await waitFor(() => expect(generateQuiz).toHaveBeenCalled())
    expect(generateQuiz).toHaveBeenCalledWith(
      expect.not.objectContaining({ note_ids: expect.anything() })
    )
  })
})
