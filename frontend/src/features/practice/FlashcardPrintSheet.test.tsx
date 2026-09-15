import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, test, vi } from 'vitest'

vi.mock('@/lib/api', () => ({
  dueFlashcards: vi.fn(async () => [
    {
      id: 1,
      front: [{ type: 'math', latex: 'x^2', display: true }],
      back: [{ type: 'text', md: 'two' }],
    },
  ]),
}))

import { FlashcardPrintSheet } from './FlashcardPrintSheet'

function renderSheet() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <FlashcardPrintSheet autoPrint={false} />
    </QueryClientProvider>
  )
}

describe('FlashcardPrintSheet', () => {
  test('renders cards without copy menus (plan 63-C)', async () => {
    renderSheet()
    expect(await screen.findByText('two')).toBeInTheDocument()
    expect(document.querySelector('.katex-display')).not.toBeNull()
    expect(screen.queryByRole('button', { name: 'Copy options' })).toBeNull()
  })
})
