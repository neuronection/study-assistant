import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { AssignToNodeDialog } from './AssignToNodeDialog'

const courseTree = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    courseTree: (...args: unknown[]) => courseTree(...(args as [number])),
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
        id: 2,
        title: 'Limits',
        summary: null,
        objectives: [],
        order_idx: 0,
        depth: 1,
        is_root: false,
        children: [],
        materials: [],
      },
      {
        id: 3,
        title: 'Derivatives',
        summary: null,
        objectives: [],
        order_idx: 1,
        depth: 1,
        is_root: false,
        children: [],
        materials: [],
      },
    ],
    materials: [],
  },
]

function renderDialog(onDone: (nodeId: number) => Promise<void> = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <AssignToNodeDialog
        courseId={3}
        title="Assign to node"
        countText="2 materials"
        confirmLabel="Assign"
        onDone={onDone}
        onClose={() => undefined}
      />
    </QueryClientProvider>
  )
}

afterEach(() => {
  vi.clearAllMocks()
})

describe('AssignToNodeDialog', () => {
  test('renders the flattened tree with depth indentation and course level', async () => {
    courseTree.mockResolvedValue(TREE)
    renderDialog()
    expect(await screen.findByRole('treeitem', { name: /Limits/ })).toBeInTheDocument()
    expect(screen.getByRole('treeitem', { name: /Derivatives/ })).toBeInTheDocument()
    expect(screen.getByText('course level')).toBeInTheDocument()
    expect(screen.getByText('2 materials')).toBeInTheDocument()
  })

  test('assign is disabled until a node is picked, then confirms with the node id', async () => {
    courseTree.mockResolvedValue(TREE)
    const onDone = vi.fn().mockResolvedValue(undefined)
    renderDialog(onDone)

    const assign = await screen.findByRole('button', { name: 'Assign' })
    expect(assign).toBeDisabled()
    fireEvent.click(await screen.findByRole('treeitem', { name: /Limits/ }))
    expect(await screen.findByRole('button', { name: 'Assign' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'Assign' }))

    await waitFor(() => expect(onDone).toHaveBeenCalledWith(2))
  })

  test('empty tree shows the empty state', async () => {
    courseTree.mockResolvedValue([])
    renderDialog()
    expect(await screen.findByText('No nodes yet')).toBeInTheDocument()
  })
})
