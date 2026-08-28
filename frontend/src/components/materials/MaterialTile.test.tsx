import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { MaterialList } from './MaterialList'
import { MaterialTile } from './MaterialTile'

describe('MaterialTile', () => {
  test('renders title, status and fires click', () => {
    const onClick = vi.fn()
    render(
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
    const { rerender } = render(
      <MaterialTile material={{ id: 7, title, kind: 'pdf' }} selectionState="none" />
    )
    expect(screen.getByText(title).className).toContain('line-clamp-3')
    expect(screen.getByText(title).className).not.toContain('line-clamp-4')

    rerender(
      <MaterialTile material={{ id: 7, title, kind: 'pdf' }} selectionState="selected" />
    )
    expect(screen.getByText(title).className).toContain('line-clamp-4')
  })
})

describe('MaterialList', () => {
  test('renders children in a grid or list layout', () => {
    const { container, rerender } = render(
      <MaterialList layout="grid">
        <span>item</span>
      </MaterialList>
    )
    const list = container.firstElementChild as HTMLElement
    expect(list.className).toContain('grid')
    rerender(
      <MaterialList layout="list">
        <span>item</span>
      </MaterialList>
    )
    expect(list.className).toContain('flex-col')
  })
})
