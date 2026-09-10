import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  redirect,
  RouterProvider,
  useNavigate,
  useParams,
  useSearch,
} from '@tanstack/react-router'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { NoteEditor } from './NoteEditor'
import { NoteEditorDrawer, closeNote, openNote } from './NoteEditorDrawer'

const getNote = vi.fn()
const updateNote = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getNote: (id: number) => getNote(id),
    updateNote: (id: number, body: unknown) => updateNote(id, body),
  }
})

const DETAIL = (id: number) => ({
  id,
  title: `Editor note ${id}`,
  course_id: null,
  node_id: null,
  owner_type: 'standalone',
  owner_id: null,
  tags: [],
  pinned: false,
  updated_at: '2026-08-19T10:00:00',
  body: [],
  drawings: [],
})

function workspaceSearch(search: Record<string, unknown>): { tab?: string; note?: number } {
  return {
    tab: typeof search.tab === 'string' ? search.tab : undefined,
    note: typeof search.note === 'number' ? search.note : undefined,
  }
}

function WorkspacePage() {
  const { courseId } = useParams({ from: '/courses/$courseId' })
  const navigate = useNavigate({ from: '/courses/$courseId' })
  const search = useSearch({ from: '/courses/$courseId' })
  return (
    <div>
      <p>workspace-page</p>
      {search.note !== undefined ? (
        <NoteEditorDrawer
          noteId={search.note}
          onClose={() =>
            void navigate({
              to: '/courses/$courseId',
              params: { courseId },
              search: closeNote,
            })
          }
        />
      ) : null}
    </div>
  )
}

function StandaloneNotePage() {
  const { noteId } = useParams({ from: '/note/$noteId' })
  return (
    <main>
      <NoteEditor noteId={Number(noteId)} />
    </main>
  )
}

function renderApp(initialUrl: string) {
  const rootRoute = createRootRoute()
  const courseRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/courses/$courseId',
    validateSearch: workspaceSearch,
    component: WorkspacePage,
  })
  const noteRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/note/$noteId',
    component: StandaloneNotePage,
  })
  const coursesIndexRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/courses',
    component: () => <p>courses-index</p>,
  })
  const notesRedirectRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/notes',
    beforeLoad: () => {
      throw redirect({ to: '/courses', replace: true })
    },
  })
  const noteRedirectRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/notes/$noteId',
    beforeLoad: ({ params }) => {
      throw redirect({
        to: '/note/$noteId',
        params: { noteId: params.noteId },
        replace: true,
      })
    },
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([
      courseRoute,
      coursesIndexRoute,
      noteRoute,
      notesRedirectRoute,
      noteRedirectRoute,
    ]),
    history: createMemoryHistory({ initialEntries: [initialUrl] }),
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
  return router
}

describe('search helpers', () => {
  test('openNote merges the note id and closeNote strips it', () => {
    expect(openNote(7)({ tab: 'notes' })).toEqual({ tab: 'notes', note: 7 })
    expect(closeNote({ tab: 'notes', note: 7 })).toEqual({ tab: 'notes' })
  })
})

describe('NoteEditorDrawer', () => {
  test('renders over the workspace when the note param is set', async () => {
    getNote.mockResolvedValue(DETAIL(1))
    const router = renderApp('/courses/3?note=1')
    expect(await screen.findByText('workspace-page')).toBeInTheDocument()
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(await screen.findByRole('textbox', { name: 'Note title' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/courses/3')
  })

  test('close X removes the drawer and the search param', async () => {
    getNote.mockResolvedValue(DETAIL(1))
    const router = renderApp('/courses/3?tab=notes&note=1')
    await screen.findByRole('textbox', { name: 'Note title' })
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(screen.getByText('workspace-page')).toBeInTheDocument()
    expect((router.state.location.search as { note?: number }).note).toBeUndefined()
    expect(router.state.location.href).not.toContain('note=')
  })

  test('backdrop click closes the drawer', async () => {
    getNote.mockResolvedValue(DETAIL(1))
    renderApp('/courses/3?note=1')
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(dialog.parentElement!)
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  test('escape closes the drawer', async () => {
    getNote.mockResolvedValue(DETAIL(1))
    renderApp('/courses/3?note=1')
    await screen.findByRole('dialog')
    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })
})

describe('note route redirects', () => {
  test('/notes/$noteId redirects to /note/$noteId', async () => {
    getNote.mockResolvedValue(DETAIL(7))
    const router = renderApp('/notes/7')
    expect(await screen.findByRole('textbox', { name: 'Note title' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/note/7')
  })

  test('/notes redirects to /courses', async () => {
    const router = renderApp('/notes')
    expect(await screen.findByText('courses-index')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/courses')
  })
})

describe('NoteEditorDrawer save behavior', () => {
  test('saving the body keeps the drawer and editor mounted', async () => {
    getNote.mockReset()
    updateNote.mockReset()
    getNote.mockImplementation((id: number) => ({
      ...DETAIL(id),
      body: [{ type: 'text', md: 'original text' }],
    }))
    updateNote.mockImplementation((id: number) => ({ ...DETAIL(id) }))
    renderApp('/courses/3?tab=notes&note=1')
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(await screen.findByRole('textbox', { name: 'Note title' })).toBeInTheDocument()

    const title = screen.getByRole('textbox', { name: 'Note title' })
    fireEvent.change(title, { target: { value: 'Renamed in drawer' } })
    fireEvent.submit(title.closest('form')!)
    await waitFor(() => expect(updateNote).toHaveBeenCalled())
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Note title' })).toBeInTheDocument()
  })
})
