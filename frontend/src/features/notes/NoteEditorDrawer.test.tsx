import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  redirect,
  RouterProvider,
  useParams,
} from '@tanstack/react-router'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { NoteEditor } from './NoteEditor'
import { closeNote, openNote } from './NoteEditorDrawer'

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
      noteRoute,
      coursesIndexRoute,
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

describe('NoteEditor save behavior', () => {
  test('saving the body keeps the editor mounted', async () => {
    getNote.mockReset()
    updateNote.mockReset()
    getNote.mockImplementation((id: number) => ({
      ...DETAIL(id),
      body: [{ type: 'text', md: 'original text' }],
    }))
    updateNote.mockImplementation((id: number) => ({ ...DETAIL(id) }))
    renderApp('/note/1')
    expect(await screen.findByRole('textbox', { name: 'Note title' })).toBeInTheDocument()

    const title = screen.getByRole('textbox', { name: 'Note title' })
    fireEvent.change(title, { target: { value: 'Renamed in editor' } })
    fireEvent.submit(title.closest('form')!)
    await waitFor(() => expect(updateNote).toHaveBeenCalled())
    expect(screen.getByRole('textbox', { name: 'Note title' })).toBeInTheDocument()
  })
})
