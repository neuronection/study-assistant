import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { MaterialHoverCard } from './MaterialHoverCard'

const getMaterialMock = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getMaterial: (id: number) => getMaterialMock(id),
  }
})

function renderCard(openDelay = 0) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MaterialHoverCard materialId={9} openDelay={openDelay}>
        <button type="button">chain-rule.pdf</button>
      </MaterialHoverCard>
    </QueryClientProvider>,
  )
}

function detailWith(indexCard: Record<string, unknown> | null) {
  return {
    material: { id: 9, title: 'chain-rule.pdf' },
    extraction: null,
    index_card: indexCard,
    drawings: [],
    images: [],
  }
}

afterEach(() => {
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

describe('MaterialHoverCard', () => {
  test('fetches on open and shows summary, topics and meta', async () => {
    getMaterialMock.mockResolvedValue(
      detailWith({
        summary: 'Worked summary of the chain rule.',
        topics: ['derivatives', 'calculus', 'rules', 'a', 'b', 'c', 'd'],
        key_terms: [],
        reading_minutes: 4,
        difficulty: 2,
      }),
    )
    const user = userEvent.setup()
    renderCard()
    await user.hover(screen.getByRole('button', { name: 'chain-rule.pdf' }))
    expect(await screen.findByText('Worked summary of the chain rule.')).toBeInTheDocument()
    expect(screen.getByText('derivatives')).toBeInTheDocument()
    expect(screen.getByText('4 min read · difficulty 2')).toBeInTheDocument()
    expect(getMaterialMock).toHaveBeenCalledWith(9)
  })

  test('shows an honest empty state when no index card exists', async () => {
    getMaterialMock.mockResolvedValue(detailWith(null))
    const user = userEvent.setup()
    renderCard()
    await user.hover(screen.getByRole('button', { name: 'chain-rule.pdf' }))
    expect(
      await screen.findByText('No AI summary yet — open the material for details.'),
    ).toBeInTheDocument()
  })

  test('does not fetch when never hovered', () => {
    renderCard()
    expect(getMaterialMock).not.toHaveBeenCalled()
  })

  test('is suppressed on coarse pointers (children render bare)', async () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockReturnValue({
        matches: true,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    )
    getMaterialMock.mockResolvedValue(detailWith(null))
    const user = userEvent.setup()
    renderCard()
    await user.hover(screen.getByRole('button', { name: 'chain-rule.pdf' }))
    await waitFor(() => {
      expect(screen.queryByText('No AI summary yet — open the material for details.')).toBeNull()
    })
    expect(document.querySelector('[data-as="hover-card"]')).toBeNull()
    expect(getMaterialMock).not.toHaveBeenCalled()
  })
})
