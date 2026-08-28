import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { BranchTreeButton } from './BranchTreePanel'

const getChatBranchTree = vi.fn()
const selectChatVariant = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getChatBranchTree: (...args: unknown[]) =>
      getChatBranchTree(...(args as [number])),
    selectChatVariant: (...args: unknown[]) =>
      selectChatVariant(...(args as [number])),
  }
})

vi.mock('@/lib/ws-client', () => ({
  getWsClient: () => ({
    subscribe: vi.fn(() => () => undefined),
  }),
}))

const TREE = {
  active_root_id: 1,
  nodes: [
    {
      id: 1,
      role: 'user',
      excerpt: 'first question',
      parent_id: null,
      children: [2, 3],
      active_child_id: 2,
    },
    {
      id: 2,
      role: 'assistant',
      excerpt: 'Answer one',
      parent_id: 1,
      children: [],
      active_child_id: null,
    },
    {
      id: 3,
      role: 'assistant',
      excerpt: 'Answer two',
      parent_id: 1,
      children: [],
      active_child_id: null,
    },
  ],
}

describe('BranchTreePanel (plan 41)', () => {
  test('renders the branch graph with the active path highlighted', async () => {
    getChatBranchTree.mockResolvedValue(TREE)
    selectChatVariant.mockResolvedValue([])
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <BranchTreeButton sessionId={4} />
      </QueryClientProvider>,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Conversation branches' }))
    const q1 = await screen.findByRole('treeitem', { name: /first question/ })
    expect(q1).toHaveAttribute('aria-current', 'true')
    expect(screen.getByRole('treeitem', { name: /Answer one/ })).toHaveAttribute(
      'aria-current',
      'true',
    )
    expect(screen.getByRole('treeitem', { name: /Answer two/ })).not.toHaveAttribute(
      'aria-current',
    )
  })

  test('clicking a hidden variant selects it', async () => {
    getChatBranchTree.mockResolvedValue(TREE)
    selectChatVariant.mockResolvedValue([])
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <BranchTreeButton sessionId={4} />
      </QueryClientProvider>,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Conversation branches' }))
    fireEvent.click(await screen.findByRole('treeitem', { name: /Answer two/ }))
    await waitFor(() => expect(selectChatVariant).toHaveBeenCalledWith(3))
  })
})
