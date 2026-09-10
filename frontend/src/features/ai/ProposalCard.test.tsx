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

import { ProposalCard, type GenerateRequest } from './ProposalCard'

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
  onOpenGenerate?: (request: GenerateRequest) => void,
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
    createRoute({
      getParentRoute: () => rootRoute,
      path: '/library/$materialId',
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
        params: {
          topic: 'chain rule',
          count: 5,
          steps: null,
          difficulty: null,
          materialIds: undefined,
          noteIds: undefined,
          instructions: null,
          questionTypes: undefined,
          shuffle: undefined,
        },
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

  test('edit_note renders the formatted diff review and approves (plan 66-B)', async () => {
    approveChatProposal.mockResolvedValue({
      ...PROPOSAL,
      action: 'edit_note',
      status: 'executed',
      result: { note_id: 42 },
    })
    renderCard({
      ...PROPOSAL,
      action: 'edit_note',
      payload: {
        note_id: 42,
        new_body_md: '# Note\n\nFixed: the derivative is $-2x$.',
        original_md: '# Note\n\nThe derivative is $2x$.',
        reason: 'sign error',
      },
    })
    expect(await screen.findByText('Edit note')).toBeInTheDocument()
    const formatted = document.querySelector(
      '[data-as="markdown-diff-view"]',
    ) as HTMLElement
    expect(formatted).not.toBeNull()
    expect(formatted.textContent).toContain('The derivative is')
    expect(formatted.textContent).toContain('Fixed: the derivative is')
    await waitFor(() =>
      expect(formatted.querySelectorAll('.katex').length).toBeGreaterThan(0),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Raw' }))
    const raw = document.querySelector(
      '[data-as="text-diff-view"]',
    ) as HTMLElement
    expect(raw).not.toBeNull()
    expect(raw.textContent).toContain('# Note')
    expect(raw.textContent).toContain('$2x$')
    expect(
      document.querySelector('[data-as="markdown-diff-view"]'),
    ).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /approve/i }))
    await waitFor(() => expect(approveChatProposal).toHaveBeenCalledWith(7))
  })

  test('append_note previews the merged result (plan 66-B)', async () => {
    renderCard({
      ...PROPOSAL,
      action: 'append_note',
      payload: {
        note_id: 42,
        markdown: 'Extra worked example.',
        heading: 'Worked example',
        original_md: '# Note\n\nBase body.',
      },
    })
    expect(await screen.findByText(/Append to note/)).toBeInTheDocument()
    const diffView = document.querySelector(
      '[data-as="markdown-diff-view"]',
    ) as HTMLElement
    expect(diffView).not.toBeNull()
    expect(diffView.textContent).toContain('Base body.')
    expect(diffView.textContent).toContain('Worked example')
    expect(diffView.textContent).not.toContain('## Worked example')
    expect(diffView.textContent).toContain('Extra worked example.')
  })

  test('edit_note without a snapshot renders a plain card (plan 66-B)', async () => {
    renderCard({
      ...PROPOSAL,
      action: 'edit_note',
      payload: { note_id: 42, new_body_md: 'Rewritten body.' },
    })
    expect(await screen.findByText(/Edit note/)).toBeInTheDocument()
    expect(
      document.querySelector('[data-as="markdown-diff-view"]'),
    ).toBeNull()
    expect(
      document.querySelector('[data-as="text-diff-view"]'),
    ).toBeNull()
    expect(screen.getByRole('button', { name: /approve/i })).toBeInTheDocument()
  })

  test('edit_material renders the diff review (plan 66-C)', async () => {
    renderCard({
      ...PROPOSAL,
      action: 'edit_material',
      payload: {
        material_id: 12,
        new_markdown: '# Chain rule\n\nCorrected statement.',
        original_md: '# Chain rule\n\nBroken statement.',
      },
    })
    expect(await screen.findByText('Edit material')).toBeInTheDocument()
    const diffView = document.querySelector(
      '[data-as="markdown-diff-view"]',
    ) as HTMLElement
    expect(diffView).not.toBeNull()
    expect(diffView.textContent).toContain('Broken statement.')
    expect(diffView.textContent).toContain('Corrected statement.')
  })

  test('append_material previews the merged result (plan 66-C)', async () => {
    renderCard({
      ...PROPOSAL,
      action: 'append_material',
      payload: {
        material_id: 12,
        markdown: 'A new section body.',
        heading: 'Extra practice',
        original_md: '# Chain rule\n\nBody.',
      },
    })
    expect(await screen.findByText(/Append to material/)).toBeInTheDocument()
    const diffView = document.querySelector(
      '[data-as="markdown-diff-view"]',
    ) as HTMLElement
    expect(diffView.textContent).toContain('Extra practice')
    expect(diffView.textContent).not.toContain('## Extra practice')
    expect(diffView.textContent).toContain('A new section body.')
  })

  test('append_material shows the target row with the node path', async () => {
    renderCard({
      ...PROPOSAL,
      action: 'append_material',
      payload: {
        material_id: 12,
        markdown: 'A new section body.',
        heading: 'Extra practice',
        original_md: '# Chain rule\n\nBody.',
        target_kind: 'material',
        target_name: 'integral-tricks.md',
        target_node_id: 3,
        target_node_path: ['Analysis I', 'Chapter 3'],
      },
    })
    expect(await screen.findByText('Material')).toBeInTheDocument()
    expect(screen.getByText('integral-tricks.md')).toBeInTheDocument()
    expect(
      screen.getByText('· Analysis I › Chapter 3'),
    ).toBeInTheDocument()
  })

  test('executed material card links to the created material', async () => {
    renderCard({
      ...PROPOSAL,
      action: 'create_material',
      payload: { title: 'Chain rule summary', body_md: 'Body.' },
      status: 'executed',
      result: { material_id: 12 },
    })
    const link = await screen.findByRole('link', { name: /open the material/i })
    expect(link).toHaveAttribute('href', '/library/12?from=%2F')
  })
  test('approved generate card passes context fields (plan 66-D)', async () => {
    const onOpenGenerate = vi.fn()
    approveChatProposal.mockResolvedValue({
      ...PROPOSAL,
      action: 'generate_quiz',
      payload: {
        topic: 'chain rule',
        count: 5,
        material_ids: [12],
        note_ids: [4],
        instructions: 'Focus on the sign rule',
        question_types: ['single'],
        shuffle: true,
      },
      status: 'approved',
      result: {
        open_dialog: {
          topic: 'chain rule',
          count: 5,
          material_ids: [12],
          note_ids: [4],
          instructions: 'Focus on the sign rule',
          question_types: ['single'],
          shuffle: true,
        },
      },
    })
    renderCard(
      {
        ...PROPOSAL,
        action: 'generate_quiz',
        payload: {
          topic: 'chain rule',
          count: 5,
          material_ids: [12],
          note_ids: [4],
          instructions: 'Focus on the sign rule',
          question_types: ['single'],
          shuffle: true,
        },
      },
      onOpenGenerate,
    )
    fireEvent.click(await screen.findByRole('button', { name: /approve/i }))
    await waitFor(() =>
      expect(onOpenGenerate).toHaveBeenCalledWith({
        task: 'quiz',
        params: {
          topic: 'chain rule',
          count: 5,
          steps: null,
          difficulty: null,
          materialIds: [12],
          noteIds: [4],
          instructions: 'Focus on the sign rule',
          questionTypes: ['single'],
          shuffle: true,
        },
      }),
    )
  })

  test('approved flashcards card passes the source context (plan 66-E)', async () => {
    const onOpenGenerate = vi.fn()
    approveChatProposal.mockResolvedValue({
      ...PROPOSAL,
      action: 'generate_flashcards',
      payload: { material_id: 12, count: 12 },
      status: 'approved',
      result: {
        open_dialog: { material_id: 12, count: 12 },
      },
    })
    renderCard(
      {
        ...PROPOSAL,
        action: 'generate_flashcards',
        payload: { material_id: 12, count: 12 },
      },
      onOpenGenerate,
    )
    fireEvent.click(await screen.findByRole('button', { name: /approve/i }))
    await waitFor(() =>
      expect(onOpenGenerate).toHaveBeenCalledWith({
        task: 'flashcards',
        params: expect.objectContaining({
          count: 12,
          flashcards: { source: 'material', materialId: 12, noteId: null },
        }),
      }),
    )
  })

  test('create_material previews the markdown body (plan 66-E)', async () => {
    renderCard({
      ...PROPOSAL,
      action: 'create_material',
      payload: {
        title: 'Chain rule summary',
        body_md: '# Chain rule\n\nIf $f$ and $g$ are differentiable…',
      },
    })
    expect(await screen.findByText(/Chain rule summary/)).toBeInTheDocument()
    expect(document.querySelector('[data-as="chat-markdown"]')).not.toBeNull()
  })
})
