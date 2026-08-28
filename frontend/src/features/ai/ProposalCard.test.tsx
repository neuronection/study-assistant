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

import { ProposalCard } from './ProposalCard'

const approveChatProposal = vi.fn()
const dismissChatProposal = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    approveChatProposal: (id: number) => approveChatProposal(id),
    dismissChatProposal: (id: number) => dismissChatProposal(id),
  }
})

import type { ChatProposal } from '@/lib/api'

const PROPOSAL: ChatProposal = {
  id: 7,
  action: 'create_note',
  payload: {
    title: 'Chain rule summary',
    body_md: 'The chain rule: $(f \\circ g)\' = f\'g \\cdot g\'$.',
  },
  status: 'proposed',
  result: null,
}

function renderCard(
  proposal: ChatProposal,
  onOpenGenerate?: (request: {
    task: 'quiz' | 'exercise'
    params: {
      topic?: string | null
      count?: number | null
      steps?: number | null
      difficulty?: number | null
    }
  }) => void,
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const rootRoute = createRootRoute()
  const show = () => (
    <QueryClientProvider client={client}>
      <ProposalCard proposal={proposal} onOpenGenerate={onOpenGenerate} />
    </QueryClientProvider>
  )
  const routes = [
    createRoute({ getParentRoute: () => rootRoute, path: '/', component: show }),
    createRoute({
      getParentRoute: () => rootRoute,
      path: '/note/$noteId',
      component: () => null,
    }),
  ]
  const router = createRouter({
    routeTree: rootRoute.addChildren(routes),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  })
  return render(<RouterProvider router={router} />)
}

describe('ProposalCard', () => {
  test('renders a proposed card with approve and dismiss', async () => {
    renderCard(PROPOSAL)
    expect(await screen.findByText(/Chain rule summary/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /approve/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /dismiss/i })).toBeInTheDocument()
    expect(screen.getByText('Proposed')).toBeInTheDocument()
  })

  test('expands the payload preview', async () => {
    renderCard(PROPOSAL)
    fireEvent.click(await screen.findByRole('button', { name: /preview/i }))
    expect(await screen.findByText(/The chain rule:/)).toBeInTheDocument()
  })

  test('approve calls the API', async () => {
    approveChatProposal.mockResolvedValue({ ...PROPOSAL, status: 'executed' })
    renderCard(PROPOSAL)
    fireEvent.click(await screen.findByRole('button', { name: /approve/i }))
    await waitFor(() => expect(approveChatProposal).toHaveBeenCalledWith(7))
  })

  test('dismiss calls the API', async () => {
    dismissChatProposal.mockResolvedValue({ ...PROPOSAL, status: 'dismissed' })
    renderCard(PROPOSAL)
    fireEvent.click(await screen.findByRole('button', { name: /dismiss/i }))
    await waitFor(() => expect(dismissChatProposal).toHaveBeenCalledWith(7))
  })

  test('executed card links to the created note and has no actions', async () => {
    renderCard({
      ...PROPOSAL,
      status: 'executed',
      result: { note_id: 42 },
    })
    const link = await screen.findByRole('link', { name: /open the note/i })
    expect(link).toHaveAttribute('href', '/note/42?from=%2F')
    expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument()
    expect(screen.getByText('Created')).toBeInTheDocument()
  })

  test('approved generate card offers opening the generator prefilled', async () => {
    const onOpenGenerate = vi.fn()
    approveChatProposal.mockResolvedValue({
      ...PROPOSAL,
      action: 'generate_quiz',
      payload: { topic: 'chain rule', count: 5 },
      status: 'approved',
      result: { open_dialog: { topic: 'chain rule', count: 5 } },
    })
    renderCard(
      {
        ...PROPOSAL,
        action: 'generate_quiz',
        payload: { topic: 'chain rule', count: 5 },
      },
      onOpenGenerate,
    )
    fireEvent.click(await screen.findByRole('button', { name: /approve/i }))
    await waitFor(() =>
      expect(onOpenGenerate).toHaveBeenCalledWith({
        task: 'quiz',
        params: { topic: 'chain rule', count: 5, steps: null, difficulty: null },
      }),
    )
    const openButton = await screen.findByRole('button', {
      name: /open generator/i,
    })
    fireEvent.click(openButton)
    expect(onOpenGenerate).toHaveBeenCalledTimes(2)
    expect(screen.getByText('Approved')).toBeInTheDocument()
  })

  test('stale card shows the explanation and no actions', async () => {
    renderCard({
      ...PROPOSAL,
      status: 'stale',
      result: { error: 'target node 12 no longer exists in this course' },
    })
    expect(
      await screen.findByText(/target node 12 no longer exists/i),
    ).toBeInTheDocument()
    expect(screen.getByText('Out of date')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument()
  })
})
