import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, test, vi } from 'vitest'

import { ConceptsPanel } from './ConceptsPanel'
import type { ConceptDraft } from '@/lib/api'

const conceptGraph = vi.fn()
const commitConcepts = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    conceptGraph: (...args: unknown[]) => conceptGraph(...(args as [number])),
    commitConcepts: (...args: unknown[]) => commitConcepts(...(args as [])),
  }
})

const GRAPH = {
  concepts: [
    {
      id: 1,
      name: 'chain rule',
      description: 'Derivative of composites',
      aliases: ['chain-rule'],
      nodes: [{ node_id: 11, node_title: 'Chain rule' }],
    },
    {
      id: 2,
      name: 'limits',
      description: null,
      aliases: [],
      nodes: [],
    },
  ],
  links: [{ from: 'limits', 'to': 'chain rule', relation: 'prereq-of' }],
}

const DRAFT: ConceptDraft = {
  concepts: [
    { name: 'chain rule', description: 'd', aliases: [] },
    { name: 'limits', description: null, aliases: [] },
  ],
  links: [{ from: 'limits', to: 'chain rule', relation: 'prereq-of' }],
  nodes: [],
}

function DraftHarness({ initial }: { initial: ConceptDraft | null }) {
  const [draft, setDraft] = useState(initial)
  return <ConceptsPanel courseId="3" draft={draft} onDraftChange={setDraft} />
}

function renderPanel(draft: ConceptDraft | null = null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <DraftHarness initial={draft} />
    </QueryClientProvider>
  )
}

describe('ConceptsPanel', () => {
  test('renders and edits a reviewable draft passed from the tab', async () => {
    conceptGraph.mockResolvedValue({ concepts: [], links: [] })
    commitConcepts.mockResolvedValue({ concepts: 2, created: 2, links: 1, nodes: 0 })
    renderPanel(DRAFT)
    expect(await screen.findByText('Concept draft')).toBeInTheDocument()
    expect(screen.getByText('chain rule')).toBeInTheDocument()

    fireEvent.click(screen.getAllByTitle('Remove')[1])
    await waitFor(() => expect(screen.queryByText('limits')).toBeNull())

    fireEvent.click(screen.getByRole('button', { name: /commit/i }))
    await waitFor(() =>
      expect(commitConcepts).toHaveBeenCalledWith(3, {
        concepts: [{ name: 'chain rule', description: 'd', aliases: [] }],
        links: [],
        nodes: [],
      })
    )
  })

  test('cancel discards the draft', async () => {
    conceptGraph.mockResolvedValue({ concepts: [], links: [] })
    renderPanel(DRAFT)
    expect(await screen.findByText('Concept draft')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
    await waitFor(() => expect(screen.queryByText('Concept draft')).toBeNull())
  })

  test('renders the graph with relations and section chips', async () => {
    conceptGraph.mockResolvedValue(GRAPH)
    renderPanel(null)
    expect(await screen.findByText('Derivative of composites')).toBeInTheDocument()
    expect(screen.getByText('chain-rule')).toBeInTheDocument()
    expect(screen.getByText('Chain rule')).toBeInTheDocument()
    expect(screen.getAllByText(/requires/).length).toBe(2)
  })
})
