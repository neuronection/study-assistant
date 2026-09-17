import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactElement } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { MaterialRow } from './MaterialRow'

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


describe('MaterialRow', () => {
  test('renders a check indicator and title; toggling fires onToggle', () => {
    const onToggle = vi.fn()
    renderWithClient(
      <MaterialRow
        material={{ id: 7, title: 'Lecture 1', kind: 'pdf' }}
        selected
        onToggle={onToggle}
      />
    )
    const checkbox = screen.getByRole('checkbox', { name: 'Lecture 1' })
    expect(checkbox).toBeChecked()
    fireEvent.click(checkbox)
    expect(onToggle).toHaveBeenCalled()
  })

  test('renders a clickable title when onOpen is provided', () => {
    const onOpen = vi.fn()
    renderWithClient(<MaterialRow material={{ id: 7, title: 'Lecture 1' }} onOpen={onOpen} />)
    fireEvent.click(screen.getByRole('button', { name: 'Lecture 1' }))
    expect(onOpen).toHaveBeenCalled()
  })

  test('title truncates by default and wraps to 2 lines when selected', () => {
    const { rerenderWithClient } = renderWithClient(
      <MaterialRow material={{ id: 7, title: 'Lecture 1' }} selectionState="none" />
    )
    expect(screen.getByText('Lecture 1').className).toContain('truncate')

    rerenderWithClient(
      <MaterialRow material={{ id: 7, title: 'Lecture 1' }} selectionState="selected" />
    )
    expect(screen.getByText('Lecture 1').className).toContain('line-clamp-2')
  })

  test('renders an action node on the right', () => {
    renderWithClient(<MaterialRow material={{ id: 7, title: 'Lecture 1' }} action={<span>added</span>} />)
    expect(screen.getByText('added')).toBeInTheDocument()
  })

  test('locked rows are inert and show the locked label', () => {
    const onToggle = vi.fn()
    renderWithClient(
      <MaterialRow
        material={{ id: 7, title: 'Lecture 1', kind: 'pdf' }}
        locked
        lockedLabel="Assigned here"
      />
    )
    expect(screen.getByText('Assigned here')).toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: 'Lecture 1' })).not.toBeInTheDocument()
    expect(onToggle).not.toHaveBeenCalled()
  })

  test('renders status and read-status pills', () => {
    renderWithClient(
      <MaterialRow
        material={{ id: 7, title: 'Lecture 1', status: 'ready', readStatus: 'studied' }}
      />
    )
    expect(screen.getByText('ready')).toBeInTheDocument()
    expect(screen.getByText('Studied')).toBeInTheDocument()
  })

  test('renders the placement badge only when linkCount is positive', () => {
    const { rerenderWithClient } = renderWithClient(
      <MaterialRow material={{ id: 7, title: 'Lecture 1', linkCount: 2 }} />
    )
    expect(screen.getByTitle('2 placements in the course tree')).toBeInTheDocument()

    rerenderWithClient(<MaterialRow material={{ id: 7, title: 'Lecture 1', linkCount: 0 }} />)
    expect(screen.queryByTitle(/placement/)).not.toBeInTheDocument()

    rerenderWithClient(<MaterialRow material={{ id: 7, title: 'Lecture 1' }} />)
    expect(screen.queryByTitle(/placement/)).not.toBeInTheDocument()
  })

  test('exposes drag attributes and container title', () => {
    const onDragStart = vi.fn()
    renderWithClient(
      <MaterialRow
        material={{ id: 7, title: 'Lecture 1' }}
        draggable
        onDragStart={onDragStart}
        title="Drag to a node"
      />
    )
    const container = screen.getByTitle('Drag to a node')
    expect(container).toHaveAttribute('draggable', 'true')
    fireEvent.dragStart(container)
    expect(onDragStart).toHaveBeenCalled()
  })
})
