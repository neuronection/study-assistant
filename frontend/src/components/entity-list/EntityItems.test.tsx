import { fireEvent, render, screen } from '@testing-library/react'
import { FileText } from 'lucide-react'
import { describe, expect, test, vi } from 'vitest'

import {
  EntityItems,
  type EntityItemEntry,
} from '@/components/entity-list/EntityItems'

interface Item extends EntityItemEntry {
  itemId: number
}

const ITEMS: Item[] = [
  { key: 'a', itemId: 1, title: 'Alpha', icon: FileText, meta: '2 pages' },
  { key: 'b', itemId: 2, title: 'Beta', icon: FileText, meta: null },
]

function menu(item: Item) {
  return [
    { key: 'open', label: 'Open', onSelect: () => item.itemId },
    { key: 'delete', label: 'Delete', danger: true, onSelect: vi.fn() },
  ]
}

describe('EntityItems', () => {
  test('renders list rows with titles and meta', () => {
    render(<EntityItems items={ITEMS} layout="list" menuItems={menu} />)
    expect(screen.getByText('Alpha')).toBeInTheDocument()
    expect(screen.getByText('2 pages')).toBeInTheDocument()
    expect(screen.getByText('Beta')).toBeInTheDocument()
  })

  test('kebab opens the context menu with the item actions', () => {
    render(<EntityItems items={ITEMS} layout="list" menuItems={menu} />)
    fireEvent.click(screen.getAllByRole('button', { name: 'Actions' })[0])
    expect(screen.getByRole('menu')).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Delete' })).toBeInTheDocument()
  })

  test('right-click on a grid tile opens the context menu', () => {
    render(<EntityItems items={ITEMS} layout="grid" menuItems={menu} />)
    fireEvent.contextMenu(screen.getByText('Alpha'))
    expect(screen.getByRole('menu')).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Open' })).toBeInTheDocument()
  })

  test('without a selection grammar a single click fires onClick', () => {
    const onClick = vi.fn()
    render(
      <EntityItems
        items={[{ ...ITEMS[0], onClick }]}
        layout="list"
        menuItems={menu}
      />,
    )
    fireEvent.click(screen.getByText('Alpha'))
    expect(onClick).toHaveBeenCalled()
  })

  test('renders the empty label when there are no items', () => {
    render(<EntityItems items={[]} layout="grid" emptyLabel="Nothing here" />)
    expect(screen.getByText('Nothing here')).toBeInTheDocument()
  })

  test('with a selection grammar: single mouse click only selects, double click and keyboard open', () => {
    const onClick = vi.fn()
    const selected = new Set(['a'])
    render(
      <EntityItems
        items={[{ ...ITEMS[0], key: 'a', onClick }]}
        layout="list"
        selection={{
          isSelected: (key) => selected.has(key),
          onPointerDown: (k) => selected.add(k),
        }}
      />,
    )
    const row = screen.getByText('Alpha').closest('[data-selectable-id]')
    expect(row).not.toBeNull()
    expect(row?.getAttribute('data-selectable-id')).toBe('a')
    expect(row?.className).toContain('bg-primary/10')

    fireEvent.click(screen.getByText('Alpha'), { detail: 1 })
    expect(onClick).not.toHaveBeenCalled()

    fireEvent.doubleClick(screen.getByText('Alpha'))
    expect(onClick).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByText('Alpha'), { detail: 0 })
    expect(onClick).toHaveBeenCalledTimes(2)
  })

  test('grid items follow the same activation grammar', () => {
    const onClick = vi.fn()
    render(
      <EntityItems
        items={[{ ...ITEMS[0], key: 'a', onClick }]}
        layout="grid"
        selection={{
          isSelected: () => false,
          onPointerDown: () => undefined,
        }}
      />,
    )
    fireEvent.click(screen.getByText('Alpha'), { detail: 1 })
    expect(onClick).not.toHaveBeenCalled()
    fireEvent.doubleClick(screen.getByText('Alpha'))
    expect(onClick).toHaveBeenCalledTimes(1)
    fireEvent.keyDown(screen.getByText('Alpha'), { key: 'Enter' })
    expect(onClick).toHaveBeenCalledTimes(2)
  })

  test('rows are draggable and forward drag start when onDragStart is provided', () => {
    const onDragStart = vi.fn()
    const dataTransfer = { setData: vi.fn(), effectAllowed: '' }
    render(
      <EntityItems
        items={ITEMS}
        layout="list"
        selection={{
          isSelected: () => false,
          onPointerDown: () => undefined,
        }}
        onDragStart={onDragStart}
      />,
    )
    const row = screen.getByText('Alpha').closest('[data-selectable-id]')
    expect(row?.getAttribute('draggable')).toBe('true')
    fireEvent.dragStart(row as Element, { dataTransfer })
    expect(onDragStart).toHaveBeenCalledWith(expect.anything(), ITEMS[0])
  })

  test('grid tiles are draggable and forward the item', () => {
    const onDragStart = vi.fn()
    render(
      <EntityItems
        items={ITEMS}
        layout="grid"
        selection={{
          isSelected: () => false,
          onPointerDown: () => undefined,
        }}
        onDragStart={onDragStart}
      />,
    )
    const tile = screen.getByText('Alpha').closest('[data-selectable-id]')
    expect(tile?.getAttribute('draggable')).toBe('true')
    fireEvent.dragStart(tile as Element, { dataTransfer: { setData: vi.fn() } })
    expect(onDragStart).toHaveBeenCalledWith(expect.anything(), ITEMS[0])
  })

  test('rows stay non-draggable without onDragStart', () => {
    render(
      <EntityItems
        items={ITEMS}
        layout="list"
        selection={{
          isSelected: () => false,
          onPointerDown: () => undefined,
        }}
      />,
    )
    const row = screen.getByText('Alpha').closest('[data-selectable-id]')
    expect(row?.getAttribute('draggable')).toBe('false')
  })

  test('an item with info renders an info button that opens a popover', () => {
    render(
      <EntityItems
        items={[
          {
            ...ITEMS[0],
            info: 'Stored in the course library.',
            infoTitle: 'Alpha details',
          },
        ]}
        layout="list"
      />,
    )
    const button = screen.getByRole('button', { name: 'Details' })
    expect(button).toBeInTheDocument()
    fireEvent.click(button)
    expect(screen.getByRole('dialog', { name: 'Details' })).toBeInTheDocument()
    expect(screen.getByText('Alpha details')).toBeInTheDocument()
    expect(screen.getByText('Stored in the course library.')).toBeInTheDocument()
  })

  test('info button click does not open the item', () => {
    const onClick = vi.fn()
    render(
      <EntityItems
        items={[{ ...ITEMS[0], onClick, info: 'Extra details' }]}
        layout="list"
        menuItems={menu}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Details' }))
    expect(onClick).not.toHaveBeenCalled()
    expect(screen.getByRole('dialog', { name: 'Details' })).toBeInTheDocument()
  })

  test('info button renders in grid layout and opens on click', () => {
    render(
      <EntityItems
        items={[{ ...ITEMS[0], info: 'Extra details' }]}
        layout="grid"
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Details' }))
    expect(screen.getByRole('dialog', { name: 'Details' })).toBeInTheDocument()
    expect(screen.getByText('Extra details')).toBeInTheDocument()
  })
})
