import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'
import { FileDown, Trash2 } from 'lucide-react'

import { PopoverMenu, type PopoverMenuItem } from './popover-menu'

describe('PopoverMenu', () => {
  test('renders items, fires onSelect and closes after picking', () => {
    const onSelect = vi.fn()
    const items: PopoverMenuItem[] = [
      { key: 'export', label: 'Export', icon: FileDown, onSelect },
    ]
    render(<PopoverMenu label="Actions" trigger={<span>open</span>} items={items} />)

    fireEvent.click(screen.getByRole('button', { name: 'Actions' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Export' }))
    expect(onSelect).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  test('danger styling and disabled items', () => {
    const blocked = vi.fn()
    const items: PopoverMenuItem[] = [
      { key: 'del', label: 'Delete', icon: Trash2, danger: true, onSelect: () => blocked() },
      { key: 'busy', label: 'Working', disabled: true, onSelect: () => blocked() },
    ]
    render(<PopoverMenu label="Actions" trigger={<span>open</span>} items={items} />)
    fireEvent.click(screen.getByRole('button', { name: 'Actions' }))

    const danger = screen.getByRole('menuitem', { name: 'Delete' })
    expect(danger.className).toContain('text-danger')
    expect(screen.getByRole('menuitem', { name: 'Working' })).toBeDisabled()

    fireEvent.click(screen.getByRole('menuitem', { name: 'Working' }))
    expect(blocked).not.toHaveBeenCalled()
  })

  test('pending items show a spinner and stay disabled', () => {
    const onSelect = vi.fn()
    render(
      <PopoverMenu
        label="Actions"
        trigger={<span>open</span>}
        items={[{ key: 'run', label: 'Running', pending: true, onSelect }]}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: 'Actions' }))
    const item = screen.getByRole('menuitem', { name: 'Running' })
    expect(item).toBeDisabled()
    expect(item.querySelector('.animate-spin')).not.toBeNull()
  })
})
