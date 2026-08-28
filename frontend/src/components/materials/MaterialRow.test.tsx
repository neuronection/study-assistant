import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { MaterialRow } from './MaterialRow'

describe('MaterialRow', () => {
  test('renders a check indicator and title; toggling fires onToggle', () => {
    const onToggle = vi.fn()
    render(
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
    render(<MaterialRow material={{ id: 7, title: 'Lecture 1' }} onOpen={onOpen} />)
    fireEvent.click(screen.getByRole('button', { name: 'Lecture 1' }))
    expect(onOpen).toHaveBeenCalled()
  })

  test('title truncates by default and wraps to 2 lines when selected', () => {
    const { rerender } = render(
      <MaterialRow material={{ id: 7, title: 'Lecture 1' }} selectionState="none" />
    )
    expect(screen.getByText('Lecture 1').className).toContain('truncate')

    rerender(
      <MaterialRow material={{ id: 7, title: 'Lecture 1' }} selectionState="selected" />
    )
    expect(screen.getByText('Lecture 1').className).toContain('line-clamp-2')
  })

  test('renders an action node on the right', () => {
    render(<MaterialRow material={{ id: 7, title: 'Lecture 1' }} action={<span>added</span>} />)
    expect(screen.getByText('added')).toBeInTheDocument()
  })

  test('locked rows are inert and show the locked label', () => {
    const onToggle = vi.fn()
    render(
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
    render(
      <MaterialRow
        material={{ id: 7, title: 'Lecture 1', status: 'ready', readStatus: 'studied' }}
      />
    )
    expect(screen.getByText('ready')).toBeInTheDocument()
    expect(screen.getByText('Studied')).toBeInTheDocument()
  })

  test('exposes drag attributes and container title', () => {
    const onDragStart = vi.fn()
    render(
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
