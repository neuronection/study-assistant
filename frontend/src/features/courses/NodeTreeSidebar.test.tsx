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

import { NodeTreeSidebar } from './NodeTreeSidebar'

const courseTree = vi.fn()
const addNode = vi.fn()
const renameNode = vi.fn()
const deleteNode = vi.fn()
const moveNode = vi.fn()
const restoreNode = vi.fn()
const allocateMaterial = vi.fn()
const moveNote = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    courseTree: (id: number) => courseTree(id),
    addNode: (...args: unknown[]) => addNode(...(args as [number, number, string])),
    renameNode: (...args: unknown[]) => renameNode(...(args as [number, string])),
    deleteNode: (id: number) => deleteNode(id),
    restoreNode: (token: string) => restoreNode(token),
    moveNode: (...args: unknown[]) => moveNode(...(args as [number, number, number])),
    allocateMaterial: (...args: unknown[]) =>
      allocateMaterial(...(args as [number, number])),
    moveNote: (...args: unknown[]) => moveNote(...(args as [number, number])),
  }
})

interface TestNode {
  id: number
  title: string
  summary: string | null
  objectives: string[]
  order_idx: number
  depth: number
  is_root: boolean
  children: TestNode[]
  counts?: {
    materials: number
    notes: number
    quizzes: number
    exercises: number
    flashcards: number
  }
  materials: unknown[]
}

function makeNode(
  id: number,
  title: string,
  depth: number,
  children: TestNode[] = [],
  counts?: TestNode['counts']
): TestNode {
  return {
    id,
    title,
    summary: null,
    objectives: [],
    order_idx: 0,
    depth,
    is_root: depth === 0,
    children,
    counts,
    materials: [],
  }
}

const TREE = makeNode(1, 'Calculus', 0, [
  makeNode(2, 'Limits', 1, [
    makeNode(3, 'Continuity', 2, [], {
      materials: 2,
      notes: 0,
      quizzes: 1,
      exercises: 0,
      flashcards: 3,
    }),
  ]),
  makeNode(
    4,
    'Derivatives',
    1,
    [],
    { materials: 0, notes: 4, quizzes: 0, exercises: 2, flashcards: 0 }
  ),
])

function chevronFor(title: string) {
  const row = screen
    .getAllByRole('button', { name: /expand or collapse node/i })
    .find((button) => button.closest('div[role="treeitem"]')?.textContent?.includes(title))
  expect(row).toBeDefined()
  return row as HTMLElement
}

function renderSidebar(currentId: number | undefined) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const rootRoute = createRootRoute()
  const courseRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/courses/$courseId',
    component: () => (
      <QueryClientProvider client={client}>
        <NodeTreeSidebar courseId="9" currentId={currentId} />
      </QueryClientProvider>
    ),
  })
  const nodeRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/courses/$courseId/n/$nodeId',
    component: () => null,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([courseRoute, nodeRoute]),
    history: createMemoryHistory({ initialEntries: ['/courses/9'] }),
  })
  return render(<RouterProvider router={router} />)
}

describe('NodeTreeSidebar', () => {
  beforeEach(() => {
    courseTree.mockReset()
    addNode.mockReset()
    renameNode.mockReset()
    deleteNode.mockReset()
    moveNode.mockReset()
    restoreNode.mockReset()
    allocateMaterial.mockReset()
    window.localStorage.clear()
    courseTree.mockResolvedValue([TREE])
    addNode.mockResolvedValue({ id: 99, title: 'New', order_idx: 1000, depth: 1 })
    renameNode.mockResolvedValue(undefined)
    deleteNode.mockResolvedValue('token-1')
    restoreNode.mockResolvedValue({ id: 4 })
    moveNode.mockResolvedValue(undefined)
    allocateMaterial.mockResolvedValue(undefined)
  })

  test('renders root and its children collapsed by default; root navigates to the course', async () => {
    renderSidebar(undefined)
    expect(await screen.findByText('Calculus')).toBeInTheDocument()
    expect(screen.getByText('Limits')).toBeInTheDocument()
    expect(screen.getByText('Derivatives')).toBeInTheDocument()
    expect(screen.queryByText('Continuity')).not.toBeInTheDocument()

    expect(screen.getByRole('link', { name: /calculus/i })).toHaveAttribute(
      'href',
      '/courses/9'
    )
    expect(screen.getByRole('link', { name: /limits/i })).toHaveAttribute(
      'href',
      '/courses/9/n/2'
    )
  })

  test('expands a node via its chevron to reveal deeper children', async () => {
    renderSidebar(undefined)
    await screen.findByText('Limits')

    fireEvent.click(chevronFor('Limits'))
    expect(await screen.findByText('Continuity')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /continuity/i })).toHaveAttribute(
      'href',
      '/courses/9/n/3'
    )

    fireEvent.click(chevronFor('Limits'))
    await waitFor(() => expect(screen.queryByText('Continuity')).not.toBeInTheDocument())
  })

  test('auto-expands ancestors of the current node and highlights it', async () => {
    renderSidebar(3)
    expect(await screen.findByText('Continuity')).toBeInTheDocument()

    const current = screen.getByRole('treeitem', { selected: true })
    expect(current).toHaveTextContent('Continuity')
    const link = screen.getByRole('link', { name: /continuity/i })
    expect(link).toHaveAttribute('aria-current', 'page')
    expect(link.className).toContain('font-medium')
  })

  test('shows only non-zero counts with tooltips', async () => {
    renderSidebar(3)
    const continuity = await screen.findByText('Continuity')
    const row = continuity.closest('div')
    expect(row).not.toBeNull()
    const badges = (row as HTMLElement).textContent
    expect(badges).toContain('2')
    expect(badges).toContain('1')
    expect(screen.getByTitle('0 of 2 materials studied')).toBeInTheDocument()
    expect(screen.getByTitle('4 notes')).toBeInTheDocument()
    expect(screen.getByTitle('2 exercises')).toBeInTheDocument()
  })

  test('expand all / collapse all', async () => {
    renderSidebar(undefined)
    expect(await screen.findByText('Limits'))
    expect(screen.queryByText('Continuity')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /expand all/i }))
    expect(await screen.findByText('Continuity')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /collapse all/i }))
    await waitFor(() => expect(screen.queryByText('Continuity')).not.toBeInTheDocument())
    expect(screen.getByText('Limits')).toBeInTheDocument()
  })

  test('shows node total and an empty hint for a childless course', async () => {
    courseTree.mockResolvedValue([makeNode(1, 'Empty course', 0)])
    renderSidebar(1)
    expect(await screen.findByText('Empty course')).toBeInTheDocument()
    expect(screen.getByText('1 node')).toBeInTheDocument()
    expect(screen.getByText('No child nodes yet.')).toBeInTheDocument()
  })

  test('context menu edits: add child posts against the node', async () => {
    renderSidebar(undefined)
    await screen.findByText('Derivatives')

    fireEvent.contextMenu(screen.getByText('Derivatives'))
    fireEvent.click(screen.getByRole('menuitem', { name: /add child/i }))

    const input = screen.getByPlaceholderText('Node title')
    fireEvent.change(input, { target: { value: 'Chain rule' } })
    fireEvent.submit(input.closest('form') as HTMLFormElement)

    await waitFor(() => expect(addNode).toHaveBeenCalledWith(9, 4, 'Chain rule'))
  })

  test('context menu edits: rename swaps the row for an inline form', async () => {
    renderSidebar(undefined)
    await screen.findByText('Derivatives')

    fireEvent.contextMenu(screen.getByText('Derivatives'))
    fireEvent.click(screen.getByRole('menuitem', { name: /rename node/i }))

    const input = screen.getByDisplayValue('Derivatives')
    fireEvent.change(input, { target: { value: 'Differentiation' } })
    fireEvent.submit(input.closest('form') as HTMLFormElement)

    await waitFor(() => expect(renameNode).toHaveBeenCalledWith(4, 'Differentiation'))
  })

  test('context menu: root offers no rename or delete, other nodes offer delete with confirm', async () => {
    renderSidebar(undefined)
    await screen.findByText('Calculus')

    fireEvent.contextMenu(screen.getByText('Calculus'))
    expect(screen.getByRole('menuitem', { name: /add child/i })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /rename node/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /delete node/i })).not.toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'Escape' })

    fireEvent.contextMenu(screen.getByText('Derivatives'))
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    fireEvent.click(screen.getByRole('menuitem', { name: /delete node/i }))
    await waitFor(() => expect(deleteNode).toHaveBeenCalledWith(4))
    confirmSpy.mockRestore()
  })

  test('context menu on panel background targets the active node', async () => {
    renderSidebar(4)
    await screen.findByText('Derivatives')

    fireEvent.contextMenu(screen.getByRole('tree'))
    expect(screen.getByRole('menuitem', { name: /add child/i })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /rename node/i })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('menuitem', { name: /rename node/i }))
    const input = screen.getByDisplayValue('Derivatives')
    fireEvent.change(input, { target: { value: 'Differentiation' } })
    fireEvent.submit(input.closest('form') as HTMLFormElement)

    await waitFor(() => expect(renameNode).toHaveBeenCalledWith(4, 'Differentiation'))
  })

  test('background context menu delete confirms against the active node', async () => {
    renderSidebar(4)
    await screen.findByText('Derivatives')

    fireEvent.contextMenu(screen.getByRole('tree'))
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    fireEvent.click(screen.getByRole('menuitem', { name: /delete node/i }))
    await waitFor(() => expect(deleteNode).toHaveBeenCalledWith(4))
    confirmSpy.mockRestore()
  })

  test('background context menu falls back to the course root without a current node', async () => {
    renderSidebar(undefined)
    await screen.findByText('Calculus')

    fireEvent.contextMenu(screen.getByRole('tree'))
    expect(screen.queryByRole('menuitem', { name: /rename node/i })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem', { name: /add child/i }))

    const input = screen.getByPlaceholderText('Node title')
    fireEvent.change(input, { target: { value: 'Integrals' } })
    fireEvent.submit(input.closest('form') as HTMLFormElement)

    await waitFor(() => expect(addNode).toHaveBeenCalledWith(9, 1, 'Integrals'))
  })

  test('context menu works across the whole panel chrome, but not inside the filter input', async () => {
    renderSidebar(undefined)
    await screen.findByText('Calculus')

    fireEvent.contextMenu(screen.getByText('Structure'))
    expect(screen.getByRole('menuitem', { name: /add child/i })).toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'Escape' })

    fireEvent.contextMenu(
      screen.getByPlaceholderText('Find a node…').parentElement as HTMLElement
    )
    expect(screen.getByRole('menuitem', { name: /add child/i })).toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'Escape' })

    fireEvent.contextMenu(screen.getByPlaceholderText('Find a node…'))
    expect(screen.queryByRole('menuitem')).not.toBeInTheDocument()
  })

  test('dragging a row onto another row reparents it', async () => {
    renderSidebar(undefined)
    await screen.findByText('Limits')

    const limits = screen.getByText('Limits').closest('div[role="treeitem"]') as HTMLElement
    const derivatives = screen
      .getByText('Derivatives')
      .closest('div[role="treeitem"]') as HTMLElement

    const payload: Record<string, string> = {}
    fireEvent.dragStart(limits, {
      dataTransfer: {
        setData: (mime: string, value: string) => {
          payload[mime] = value
        },
        getData: (mime: string) => payload[mime] ?? '',
        types: ['application/x-ca-node'],
      },
    })
    fireEvent.dragOver(derivatives, {
      dataTransfer: { types: ['application/x-ca-node'] },
    })
    fireEvent.drop(derivatives, {
      dataTransfer: {
        getData: (mime: string) => payload[mime] ?? '',
        types: ['application/x-ca-node'],
      },
      clientY: 0,
    })

    await waitFor(() => expect(moveNode).toHaveBeenCalledWith(2, 4, 0))
  })

  test('dropping a material onto a row assigns it to that node', async () => {
    renderSidebar(undefined)
    await screen.findByText('Derivatives')

    const derivatives = screen
      .getByText('Derivatives')
      .closest('div[role="treeitem"]') as HTMLElement

    fireEvent.dragOver(derivatives, {
      dataTransfer: { types: ['application/x-ca-material'] },
    })
    fireEvent.drop(derivatives, {
      dataTransfer: {
        getData: (mime: string) =>
          mime === 'application/x-ca-material' ? '42' : '',
        types: ['application/x-ca-material'],
      },
    })

    await waitFor(() => expect(allocateMaterial).toHaveBeenCalledWith(4, 42))
  })

  test('dropping a multi-item payload assigns every material', async () => {
    renderSidebar(undefined)
    await screen.findByText('Derivatives')

    const derivatives = screen
      .getByText('Derivatives')
      .closest('div[role="treeitem"]') as HTMLElement
    const payload = JSON.stringify({ folderIds: [], materialIds: [42, 43], noteIds: [] })

    fireEvent.dragOver(derivatives, {
      dataTransfer: { types: ['application/x-ca-item'] },
    })
    fireEvent.drop(derivatives, {
      dataTransfer: {
        getData: (mime: string) => (mime === 'application/x-ca-item' ? payload : ''),
        types: ['application/x-ca-item'],
      },
    })

    await waitFor(() => expect(allocateMaterial).toHaveBeenCalledWith(4, 42))
    await waitFor(() => expect(allocateMaterial).toHaveBeenCalledWith(4, 43))
  })

  test('dropping a note payload moves every note to that node', async () => {
    moveNote.mockResolvedValue(undefined)
    renderSidebar(undefined)
    await screen.findByText('Derivatives')

    const derivatives = screen
      .getByText('Derivatives')
      .closest('div[role="treeitem"]') as HTMLElement
    const payload = JSON.stringify({ folderIds: [], materialIds: [], noteIds: [21, 22] })

    fireEvent.dragOver(derivatives, {
      dataTransfer: { types: ['application/x-ca-item'] },
    })
    fireEvent.drop(derivatives, {
      dataTransfer: {
        getData: (mime: string) => (mime === 'application/x-ca-item' ? payload : ''),
        types: ['application/x-ca-item'],
      },
    })

    await waitFor(() => expect(moveNote).toHaveBeenCalledWith(21, 4))
    await waitFor(() => expect(moveNote).toHaveBeenCalledWith(22, 4))
  })

  test('filter narrows the tree to scored matches and restores on clear', async () => {
    renderSidebar(undefined)
    await screen.findByText('Limits')

    fireEvent.change(screen.getByPlaceholderText('Find a node…'), {
      target: { value: 'contin' },
    })
    expect(await screen.findByText('Continuity')).toBeInTheDocument()
    expect(screen.queryByText('Limits')).not.toBeInTheDocument()
    expect(screen.getByText('1 match')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /clear search/i }))
    await waitFor(() => expect(screen.getByText('Limits')).toBeInTheDocument())
  })

  test('keyboard navigation moves focus, expands, and collapses', async () => {
    renderSidebar(undefined)
    await screen.findByText('Limits')

    const treeEl = screen.getByRole('tree')
    fireEvent.focus(treeEl)
    fireEvent.keyDown(treeEl, { key: 'ArrowDown' })
    expect(treeEl.getAttribute('aria-activedescendant')).toBe('ca-tree-row-2')

    fireEvent.keyDown(treeEl, { key: 'ArrowRight' })
    await screen.findByText('Continuity')

    fireEvent.keyDown(treeEl, { key: 'ArrowDown' })
    expect(treeEl.getAttribute('aria-activedescendant')).toBe('ca-tree-row-3')

    fireEvent.keyDown(treeEl, { key: 'ArrowLeft' })
    expect(treeEl.getAttribute('aria-activedescendant')).toBe('ca-tree-row-2')
    fireEvent.keyDown(treeEl, { key: 'ArrowLeft' })
    await waitFor(() => expect(screen.queryByText('Continuity')).not.toBeInTheDocument())
    expect(treeEl.getAttribute('aria-activedescendant')).toBe('ca-tree-row-2')
  })

  test('delete shows an undo toast that restores the node', async () => {
    renderSidebar(undefined)
    await screen.findByText('Derivatives')

    fireEvent.contextMenu(screen.getByText('Derivatives'))
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    fireEvent.click(screen.getByRole('menuitem', { name: /delete node/i }))
    await waitFor(() => expect(deleteNode).toHaveBeenCalledWith(4))
    confirmSpy.mockRestore()

    expect(await screen.findByText('Node deleted.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /undo/i }))
    await waitFor(() => expect(restoreNode).toHaveBeenCalledWith('token-1'))
  })

  test('expansion state persists to localStorage per course', async () => {
    renderSidebar(undefined)
    await screen.findByText('Limits')

    fireEvent.click(chevronFor('Limits'))
    await screen.findByText('Continuity')
    await waitFor(() =>
      expect(window.localStorage.getItem('ca-tree-expanded-9')).toBe('["1","2"]')
    )
  })

function dropEvent(mime: string, payloadValue: string, clientY?: number) {
  const ev = new Event('drop', { bubbles: true, cancelable: true })
  const payload: Record<string, string> = { [mime]: payloadValue }
  Object.defineProperty(ev, 'dataTransfer', {
    value: {
      getData: (key: string) => payload[key] ?? '',
      types: [mime],
    },
  })
  if (clientY !== undefined) {
    Object.defineProperty(ev, 'clientY', { value: clientY })
  }
  return ev
}

  test('drop edges reorder siblings instead of nesting', async () => {
    renderSidebar(undefined)
    await screen.findByText('Limits')

    const limits = screen.getByText('Limits').closest('div[role="treeitem"]') as HTMLElement
    const derivatives = screen
      .getByText('Derivatives')
      .closest('div[role="treeitem"]') as HTMLElement
    vi.spyOn(derivatives, 'getBoundingClientRect').mockReturnValue({
      ...derivatives.getBoundingClientRect(),
      top: 100,
      height: 28,
    } as DOMRect)

    fireEvent.dragStart(limits, {
      dataTransfer: {
        setData: () => undefined,
        getData: () => '2',
        types: ['application/x-ca-node'],
      },
    })
    derivatives.dispatchEvent(dropEvent('application/x-ca-node', '2', 105))

    await waitFor(() => expect(moveNode).toHaveBeenCalledWith(2, 1, 1))
  })
})
