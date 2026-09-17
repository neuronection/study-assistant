import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { FileDock } from './FileDock'

const courseTree = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    courseTree: (courseId: number) => courseTree(courseId),
  }
})

vi.mock('@/features/library/MaterialDetailDrawer', () => ({
  MaterialDetailDrawer: (props: {
    docked?: boolean
    onClose: () => void
    onTakeNotes?: () => void
    onExpand?: () => void
  }) => (
    <div data-testid="material-stub">
      <span data-testid="material-docked">{String(props.docked)}</span>
      <button onClick={props.onClose}>stub-close</button>
      <button onClick={props.onTakeNotes}>stub-notes</button>
      <button onClick={props.onExpand}>stub-expand</button>
    </div>
  ),
}))

vi.mock('@/features/notes/LazyNoteEditor', () => ({
  LazyNoteEditor: (props: {
    docked?: boolean
    noteId: number
    onClose: () => void
    onStudyAlongside?: () => void
    onExpand?: () => void
  }) => (
    <div data-testid="note-stub">
      <span data-testid="note-docked">{String(props.docked)}</span>
      <span data-testid="note-id">{props.noteId}</span>
      <button onClick={props.onClose}>stub-close</button>
      <button onClick={props.onStudyAlongside}>stub-alongside</button>
      <button onClick={props.onExpand}>stub-expand</button>
    </div>
  ),
}))

vi.mock('@/features/courses/MaterialPickerDialog', () => ({
  MaterialPickerDialog: (props: { onClose: () => void; onSelect?: (ids: number[]) => void }) => (
    <div data-testid="picker-stub">
      <button onClick={props.onClose}>picker-close</button>
      <button onClick={() => props.onSelect?.([9])}>picker-select</button>
    </div>
  ),
}))

function tabSearch(search: Record<string, unknown>): {
  tab?: string
  note?: number
  material?: number
  study?: number | 'new'
  folder?: number
} {
  const rawStudy = search.study
  let study: number | 'new' | undefined
  if (rawStudy === 'new') {
    study = 'new'
  } else if (typeof rawStudy === 'number') {
    study = rawStudy
  }
  return {
    tab: typeof search.tab === 'string' ? search.tab : undefined,
    note: typeof search.note === 'number' ? search.note : undefined,
    material: typeof search.material === 'number' ? search.material : undefined,
    study,
    folder: undefined,
  }
}

function renderDock(initialUrl: string) {
  const rootRoute = createRootRoute()
  const courseRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/courses/$courseId',
    validateSearch: tabSearch,
    component: () => (
      <>
        <p>course-page</p>
        <FileDock />
      </>
    ),
  })
  const nodeRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/courses/$courseId/n/$nodeId',
    validateSearch: tabSearch,
    component: () => (
      <>
        <p>node-page</p>
        <FileDock />
      </>
    ),
  })
  const materialRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/library/$materialId',
    validateSearch: (search: Record<string, unknown>) => ({
      from: typeof search.from === 'string' ? search.from : undefined,
    }),
    component: () => <p>library-detail</p>,
  })
  const noteRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/note/$noteId',
    validateSearch: (search: Record<string, unknown>) => ({
      from: typeof search.from === 'string' ? search.from : undefined,
    }),
    component: () => <p>note-focus</p>,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([courseRoute, nodeRoute, materialRoute, noteRoute]),
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

describe('FileDock', () => {
  test('renders the material docked, non-modal, when ?material= is set', async () => {
    renderDock('/courses/3?material=7')
    expect(await screen.findByText('course-page')).toBeInTheDocument()
    expect(screen.getByTestId('material-stub')).toBeInTheDocument()
    expect(screen.getByTestId('material-docked')).toHaveTextContent('true')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByRole('separator', { name: 'Resize panel width' })).toBeInTheDocument()
  })

  test('close strips the material param on the node route', async () => {
    const router = renderDock('/courses/3/n/5?tab=materials&material=7')
    await screen.findByText('node-page')
    fireEvent.click(screen.getByRole('button', { name: 'stub-close' }))
    await waitFor(() =>
      expect(
        (router.state.location.search as { material?: number }).material
      ).toBeUndefined()
    )
    expect(router.state.location.pathname).toBe('/courses/3/n/5')
    expect(router.state.location.search).toMatchObject({ tab: 'materials' })
    expect(screen.queryByTestId('material-stub')).not.toBeInTheDocument()
  })

  test('take notes adds study=new while keeping the material', async () => {
    const router = renderDock('/courses/3?material=7')
    await screen.findByTestId('material-stub')
    fireEvent.click(screen.getByRole('button', { name: 'stub-notes' }))
    await waitFor(() =>
      expect(router.state.location.search).toMatchObject({ material: 7, study: 'new' })
    )
  })

  test('expand navigates to the material full page carrying the origin', async () => {
    const router = renderDock('/courses/3/n/5?material=7')
    await screen.findByTestId('material-stub')
    fireEvent.click(screen.getByRole('button', { name: 'stub-expand' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/library/7'))
    expect(router.state.location.search).toMatchObject({ from: '/courses/3/n/5?material=7' })
  })

  test('renders the note editor docked when ?note= is set', async () => {
    courseTree.mockResolvedValue([])
    renderDock('/courses/3?note=5')
    expect(await screen.findByTestId('note-stub')).toBeInTheDocument()
    expect(screen.getByTestId('note-docked')).toHaveTextContent('true')
    expect(screen.getByTestId('note-id')).toHaveTextContent('5')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  test('study alongside swaps the note for material+study via the picker', async () => {
    courseTree.mockResolvedValue([])
    const router = renderDock('/courses/3?note=5')
    await screen.findByTestId('note-stub')
    fireEvent.click(screen.getByRole('button', { name: 'stub-alongside' }))
    expect(await screen.findByTestId('picker-stub')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'picker-select' }))
    await waitFor(() =>
      expect(router.state.location.search).toMatchObject({ material: 9, study: 5 })
    )
    expect(
      (router.state.location.search as { note?: number }).note
    ).toBeUndefined()
    expect(screen.queryByTestId('picker-stub')).not.toBeInTheDocument()
  })

  test('expand navigates to the note full page carrying the origin', async () => {
    courseTree.mockResolvedValue([])
    const router = renderDock('/courses/3?note=5')
    await screen.findByTestId('note-stub')
    fireEvent.click(screen.getByRole('button', { name: 'stub-expand' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/note/5'))
    expect(router.state.location.search).toMatchObject({ from: '/courses/3?note=5' })
  })

  test('renders nothing while the split study pane owns the screen', async () => {
    renderDock('/courses/3?material=7&study=77')
    expect(await screen.findByText('course-page')).toBeInTheDocument()
    expect(screen.queryByTestId('material-stub')).not.toBeInTheDocument()
    expect(screen.queryByRole('separator')).not.toBeInTheDocument()
  })
})
