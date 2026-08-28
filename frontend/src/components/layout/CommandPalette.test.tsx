import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { CommandPalette } from './CommandPalette'
import { useWorkspaceStore } from '@/lib/workspace-store'

const listCourses = vi.fn()
const listNotes = vi.fn()
const listQuizzes = vi.fn()
const listExercises = vi.fn()
const createNote = vi.fn()
const courseTree = vi.fn()
const generateQuiz = vi.fn()
const search = vi.fn()
const navigate = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listCourses: () => listCourses(),
    listNotes: (...args: unknown[]) => listNotes(...(args as [])),
    listQuizzes: () => listQuizzes(),
    listExercises: () => listExercises(),
    createNote: (body: unknown) => createNote(body),
    courseTree: (id: number) => courseTree(id),
    generateQuiz: (body: unknown) => generateQuiz(body),
    search: (query: string) => search(query),
  }
})

vi.mock('@tanstack/react-router', () => ({
  useRouterState: ({ select }: { select: (state: unknown) => unknown }) =>
      select({ location: { href: '/', search: {} } }),
  useNavigate: () => navigate,
}))

function renderPalette(open = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <CommandPalette open={open} onClose={() => undefined} />
    </QueryClientProvider>
  )
}

describe('CommandPalette', () => {
  beforeEach(() => {
    listCourses.mockReset()
    listNotes.mockReset()
    listNotes.mockResolvedValue({ items: [], next_cursor: null })
    listQuizzes.mockReset()
    listQuizzes.mockResolvedValue([])
    listExercises.mockReset()
    listExercises.mockResolvedValue([])
    createNote.mockReset()
    courseTree.mockReset()
    generateQuiz.mockReset()
    search.mockReset()
    search.mockResolvedValue({ query: '', hits: [] })
    navigate.mockClear()
    useWorkspaceStore.getState().setCourse(null)
  })

  test('hidden when closed', () => {
    listCourses.mockResolvedValue([])
    renderPalette(false)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  test('lists quick actions and navigation, filtered fuzzily', async () => {
    listCourses.mockResolvedValue([])
    renderPalette()
    expect(await screen.findByText('New note')).toBeInTheDocument()
    expect(screen.getByText('Library')).toBeInTheDocument()
    expect(screen.queryByText('Flashcards')).not.toBeInTheDocument()
    expect(screen.queryByText('Notes')).not.toBeInTheDocument()
    expect(screen.queryByText('Quiz')).not.toBeInTheDocument()
    expect(screen.queryByText('Exercises')).not.toBeInTheDocument()

    const input = screen.getByRole('textbox', { name: /type a command/i })
    fireEvent.change(input, { target: { value: 'libr' } })
    expect(screen.getByText('Library')).toBeInTheDocument()
    expect(screen.queryByText('Scores')).not.toBeInTheDocument()
  })

  test('keyboard navigation selects and runs an action', async () => {
    listCourses.mockResolvedValue([])
    renderPalette()
    await screen.findByText('New note')
    const input = screen.getByRole('textbox', { name: /type a command/i })
    const pane = input.closest('div[class*="rounded-xl"]')!
    fireEvent.keyDown(pane, { key: 'ArrowDown' })
    fireEvent.keyDown(pane, { key: 'ArrowDown' })
    fireEvent.keyDown(pane, { key: 'ArrowDown' })
    fireEvent.keyDown(pane, { key: 'ArrowDown' })
    fireEvent.keyDown(pane, { key: 'Enter' })
    await waitFor(() => expect(navigate).toHaveBeenCalledWith({ to: '/courses' }))
  })

  test('new note action creates a note in the resolved course and navigates', async () => {
    useWorkspaceStore.getState().setCourse(null)
    listCourses.mockResolvedValue([
      {
        id: 3,
        title: 'Calculus I',
        subject: null,
        level: null,
        description: null,
        color: null,
        archived_at: null,
        material_count: 0,
      },
    ])
    createNote.mockResolvedValue({ id: 12, body: [], drawings: [], tags: [] })
    renderPalette()
    await screen.findByText('Go to Calculus I')
    fireEvent.click(screen.getByText('New note'))
    await waitFor(() =>
      expect(createNote).toHaveBeenCalledWith(expect.objectContaining({ course_id: 3 }))
    )
    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith({
        to: '/note/$noteId',
        params: { noteId: '12' },
      })
    )
  })

  test('note search lists matching notes and opens the standalone editor', async () => {
    listCourses.mockResolvedValue([])
    listNotes.mockResolvedValue({
      items: [
        {
          id: 21,
          title: 'Chain rule note',
          course_id: 3,
          node_id: null,
          owner_type: 'standalone',
          owner_id: null,
          tags: [],
          pinned: false,
          updated_at: '2026-08-19T00:00:00Z',
        },
        {
          id: 22,
          title: 'U-substitution walkthrough',
          course_id: 3,
          node_id: null,
          owner_type: 'standalone',
          owner_id: null,
          tags: [],
          pinned: false,
          updated_at: '2026-08-19T00:00:00Z',
        },
      ],
      next_cursor: null,
    })
    renderPalette()
    const input = screen.getByRole('textbox', { name: /type a command/i })
    fireEvent.change(input, { target: { value: 'chain' } })
    fireEvent.click(await screen.findByText('note: Chain rule note'))
    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith({
        to: '/note/$noteId',
        params: { noteId: '21' },
      })
    )
    expect(screen.queryByText('note: U-substitution walkthrough')).not.toBeInTheDocument()
  })

  test('new note action without a resolvable course shows a hint instead of creating', async () => {
    useWorkspaceStore.getState().setCourse(null)
    listCourses.mockResolvedValue([
      {
        id: 3,
        title: 'Calculus I',
        subject: null,
        level: null,
        description: null,
        color: null,
        archived_at: null,
        material_count: 0,
      },
      {
        id: 4,
        title: 'Linear Algebra',
        subject: null,
        level: null,
        description: null,
        color: null,
        archived_at: null,
        material_count: 0,
      },
    ])
    renderPalette()
    await screen.findByText('Go to Calculus I')
    fireEvent.click(screen.getByText('New note'))
    expect(await screen.findByText(/Open a course first/i)).toBeInTheDocument()
    expect(createNote).not.toHaveBeenCalled()
  })

  test('courses appear as actions that switch the workspace', async () => {
    useWorkspaceStore.getState().setCourse(null)
    listCourses.mockResolvedValue([
      {
        id: 3,
        title: 'Calculus I',
        subject: null,
        level: null,
        description: null,
        color: null,
        archived_at: null,
        material_count: 0,
      },
    ])
    renderPalette()
    fireEvent.click(await screen.findByText('Go to Calculus I'))
    await waitFor(() => expect(useWorkspaceStore.getState().courseId).toBe(3))
    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith({
        to: '/courses/$courseId',
        params: { courseId: '3' },
      })
    )
    useWorkspaceStore.getState().setCourse(null)
  })

  test('quiz and exercise search sections navigate to the runner and player', async () => {
    listCourses.mockResolvedValue([])
    listQuizzes.mockResolvedValue([
      {
        id: 50,
        title: 'Derivatives quiz',
        type: 'quiz',
        course_id: 3,
        node_id: null,
        question_count: 8,
      },
      {
        id: 51,
        title: 'Limits quiz',
        type: 'quiz',
        course_id: 3,
        node_id: null,
        question_count: 6,
      },
    ])
    listExercises.mockResolvedValue([
      {
        id: 60,
        title: 'Chain rule drill',
        course_id: 3,
        node_id: null,
        difficulty: 2,
        step_count: 3,
      },
    ])
    renderPalette()
    const input = screen.getByRole('textbox', { name: /type a command/i })
    fireEvent.change(input, { target: { value: 'der' } })
    fireEvent.click(await screen.findByText('quiz: Derivatives quiz'))
    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith({
        to: '/quiz/$activityId',
        params: { activityId: '50' },
        search: { from: '/' },
      })
    )

    fireEvent.change(input, { target: { value: 'chain' } })
    fireEvent.click(await screen.findByText('exercise: Chain rule drill'))
    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith({
        to: '/exercises/$exerciseId',
        params: { exerciseId: '60' },
        search: { from: '/' },
      })
    )
  })

  test('open chat action navigates to the chat page', async () => {
    listCourses.mockResolvedValue([])
    renderPalette()
    fireEvent.click(await screen.findByText('Open tutor chat'))
    expect(navigate).toHaveBeenCalledWith({ to: '/chat' })
  })

  test('node actions quiz and open node workspaces', async () => {
    useWorkspaceStore.getState().setCourse(3)
    listCourses.mockResolvedValue([])
    courseTree.mockResolvedValue([
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
    ])
    generateQuiz.mockResolvedValue({ id: 44, title: 'Derivatives quiz', question_count: 8 })
    renderPalette()
    fireEvent.click(await screen.findByText('Quiz me on Derivatives'))
    await waitFor(() =>
      expect(generateQuiz).toHaveBeenCalledWith({ course_id: 3, node_id: 5, count: 8 })
    )
    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith({
        to: '/quiz/$activityId',
        params: { activityId: '44' },
        search: { from: '/' },
      })
    )
    fireEvent.click(screen.getByText('Open Chain rule'))
    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith({
        to: '/courses/$courseId/n/$nodeId',
        params: { courseId: '3', nodeId: '11' },
      })
    )
    useWorkspaceStore.getState().setCourse(null)
  })
})

describe('CommandPalette content search', () => {
  beforeEach(() => {
    listCourses.mockReset().mockResolvedValue([])
    listNotes.mockReset().mockResolvedValue({ items: [], next_cursor: null })
    listQuizzes.mockReset().mockResolvedValue([])
    listExercises.mockReset().mockResolvedValue([])
    createNote.mockReset()
    courseTree.mockReset()
    generateQuiz.mockReset()
    search.mockReset()
    navigate.mockClear()
    useWorkspaceStore.getState().setCourse(null)
  })

  test('? prefix switches to content mode and lists hits with snippets', async () => {
    search.mockResolvedValue({
      query: 'chain rule',
      hits: [
        {
          material_id: 9,
          title: 'Lecture 3',
          snippet: 'The chain rule states $(fg)\' = f\'g + fg\'$',
          score: 0.9,
        },
      ],
    })
    renderPalette()
    const input = screen.getByRole('textbox', { name: /search/i })
    fireEvent.change(input, { target: { value: '?chain rule' } })
    expect(await screen.findByText(/In "Lecture 3"/)).toBeInTheDocument()
    expect(search).toHaveBeenCalledWith('chain rule')
    expect(screen.queryByRole('button', { name: /new note/i })).not.toBeInTheDocument()
  })

  test('enter on a content hit navigates to the material page', async () => {
    search.mockResolvedValue({
      query: 'limits',
      hits: [
        { material_id: 12, title: 'Limits handout', snippet: 'epsilon-delta', score: 0.8 },
      ],
    })
    renderPalette()
    fireEvent.change(screen.getByRole('textbox', { name: /search/i }), {
      target: { value: '?limits' },
    })
    const option = await screen.findByText(/In "Limits handout"/)
    fireEvent.click(option.closest('button')!)
    expect(navigate).toHaveBeenCalledWith(
      expect.objectContaining({
        to: '/library/$materialId',
        params: { materialId: '12' },
      })
    )
  })

  test('content mode with no hits shows the empty state, plain mode shows the hint', async () => {
    search.mockResolvedValue({ query: 'zzz', hits: [] })
    renderPalette()
    fireEvent.change(screen.getByRole('textbox', { name: /search/i }), {
      target: { value: '?zzz' },
    })
    await waitFor(() => expect(search).toHaveBeenCalledWith('zzz'))
    expect(await screen.findByText(/No matching commands/i)).toBeInTheDocument()
    expect(screen.queryByText(/Type \? before your query/i)).not.toBeInTheDocument()

    fireEvent.change(screen.getByRole('textbox', { name: /search/i }), {
      target: { value: '' },
    })
    expect(screen.getByText(/Type \? before your query/i)).toBeInTheDocument()
  })
})
