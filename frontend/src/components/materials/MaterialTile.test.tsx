import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactElement } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { MaterialList } from './MaterialList'
import { MaterialTile } from './MaterialTile'

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const utils = render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
  return {
    ...utils,
    rerenderWithClient(next: ReactElement) {
      utils.rerender(<QueryClientProvider client={client}>{next}</QueryClientProvider>)
    },
  }
}


describe('MaterialTile', () => {
  test('renders title, status and fires click', () => {
    const onClick = vi.fn()
    renderWithClient(
      <MaterialTile
        material={{ id: 7, title: 'Lecture 1', kind: 'pdf', status: 'ready' }}
        onClick={onClick}
      />
    )
    expect(screen.getByText('Lecture 1')).toBeInTheDocument()
    expect(screen.getByText('ready')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /lecture 1/i }))
    expect(onClick).toHaveBeenCalled()
  })

  test('clamps to 3 lines by default and 4 when selected', () => {
    const title = 'Lecture 1'
    const { rerenderWithClient } = renderWithClient(
      <MaterialTile material={{ id: 7, title, kind: 'pdf' }} selectionState="none" />
    )
    expect(screen.getByText(title).className).toContain('line-clamp-3')
    expect(screen.getByText(title).className).not.toContain('line-clamp-4')

    rerenderWithClient(
      <MaterialTile material={{ id: 7, title, kind: 'pdf' }} selectionState="selected" />
    )
    expect(screen.getByText(title).className).toContain('line-clamp-4')
  })

  test('renders the placement badge only when linkCount is positive', () => {
    const { rerenderWithClient } = renderWithClient(
      <MaterialTile material={{ id: 7, title: 'Lecture 1', linkCount: 3 }} />
    )
    expect(screen.getByTitle('3 placements in the course tree')).toBeInTheDocument()

    rerenderWithClient(<MaterialTile material={{ id: 7, title: 'Lecture 1', linkCount: 0 }} />)
    expect(screen.queryByTitle(/placement/)).not.toBeInTheDocument()
  })
})

describe('MaterialList', () => {
  test('renders children in a grid or list layout', () => {
    const { container, rerenderWithClient } = renderWithClient(
      <MaterialList layout="grid">
        <span>item</span>
      </MaterialList>
    )
    const list = container.firstElementChild as HTMLElement
    expect(list.className).toContain('grid')
    rerenderWithClient(
      <MaterialList layout="list">
        <span>item</span>
      </MaterialList>
    )
    expect(list.className).toContain('flex-col')
  })
})
