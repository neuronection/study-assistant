import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from '@tanstack/react-router'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { FocusShell, useFocusContext } from './FocusShell'

const courseTree = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    courseTree: (id: number) => courseTree(id),
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
        children: [],
        materials: [],
      },
    ],
    materials: [],
  },
]

function ContextProbe() {
  const context = useFocusContext(9, 5)
  return <FocusShell title="Chain rule quiz" context={context} meta={<span>meta-body</span>} onClose={() => {}}>
    <p>shell-content</p>
  </FocusShell>
}

function renderInRouter(ui: React.ReactElement) {
  const rootRoute = createRootRoute({ component: () => ui })
  const router = createRouter({
    routeTree: rootRoute,
    history: createMemoryHistory(),
  })
  render(<RouterProvider router={router} />)
  return router
}

function renderApp(initialUrl: string) {
  const rootRoute = createRootRoute()
  const probeRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/probe',
    component: ContextProbe,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([probeRoute]),
    history: createMemoryHistory({ initialEntries: [initialUrl] }),
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}

describe('FocusShell', () => {
  test('page variant renders breadcrumb links, meta behind the details toggle, close', async () => {
    const onClose = vi.fn()
    renderInRouter(
      <QueryClientProvider client={new QueryClient()}>
        <FocusShell
          title="Chain rule quiz"
          context={{ courseId: '9', nodeId: '5', courseTitle: 'Calculus I', nodeTitle: 'Derivatives', isRoot: false }}
          meta={<span>meta-body</span>}
          onClose={onClose}
        >
          <p>shell-content</p>
        </FocusShell>
      </QueryClientProvider>
    )

    const courseLink = await screen.findByRole('link', { name: /Calculus I/ })
    expect(courseLink).toHaveAttribute('href', '/courses/9')
    const nodeLink = screen.getByRole('link', { name: 'Derivatives' })
    expect(nodeLink).toHaveAttribute('href', '/courses/9/n/5')
    expect(screen.getByText('Chain rule quiz')).toBeInTheDocument()

    expect(screen.queryByText('meta-body')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Details' }))
    expect(screen.getByText('meta-body')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  test('overlay variant renders a dialog closed by backdrop, Escape and X', async () => {
    const onClose = vi.fn()
    renderInRouter(
      <FocusShell title="Material" overlay onClose={onClose}>
        <p>overlay-content</p>
      </FocusShell>
    )
    const dialog = await screen.findByRole('dialog')
    expect(screen.getByText('overlay-content')).toBeInTheDocument()

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(onClose).toHaveBeenCalledTimes(2)

    fireEvent.click(dialog.parentElement!)
    expect(onClose).toHaveBeenCalledTimes(3)
  })

  test('overlay variant expands and collapses to full width via the toggle', async () => {
    window.localStorage.clear()
    renderInRouter(
      <FocusShell title="Material" overlay onClose={() => {}}>
        <p>overlay-content</p>
      </FocusShell>
    )
    const dialog = await screen.findByRole('dialog')
    const expand = screen.getByRole('button', { name: 'Expand to full width' })
    expect(dialog.className).toContain('w-[min(760px,100vw-2rem)]')
    expect(expand).toHaveAttribute('aria-pressed', 'false')

    fireEvent.click(expand)
    expect(screen.getByRole('button', { name: 'Collapse to drawer' })).toHaveAttribute(
      'aria-pressed',
      'true'
    )
    expect(dialog.className).toContain('w-full')

    fireEvent.click(screen.getByRole('button', { name: 'Collapse to drawer' }))
    expect(screen.getByRole('button', { name: 'Expand to full width' })).toHaveAttribute(
      'aria-pressed',
      'false'
    )
    expect(dialog.className).toContain('w-[min(760px,100vw-2rem)]')
  })

  test('page variant does not render the full-width toggle', async () => {
    renderInRouter(<FocusShell title="Page" onClose={() => {}}><p>page-content</p></FocusShell>)
    expect(await screen.findByText('page-content')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Expand to full width' })).not.toBeInTheDocument()
  })

  test('useFocusContext resolves course and node titles from the tree', async () => {
    courseTree.mockResolvedValue(TREE)
    renderApp('/probe')
    expect(await screen.findByRole('link', { name: /Calculus I/ })).toHaveAttribute('href', '/courses/9')
    await waitFor(() => expect(screen.getByRole('link', { name: 'Derivatives' })).toHaveAttribute('href', '/courses/9/n/5'))
    expect(courseTree).toHaveBeenCalledWith(9)
  })
})
