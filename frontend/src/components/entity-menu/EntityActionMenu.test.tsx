import { fireEvent, render, screen } from '@testing-library/react'
import { ListChecks, Trash2 } from 'lucide-react'
import { describe, expect, test, vi } from 'vitest'

import { EntityActionMenu } from './EntityActionMenu'

describe('EntityActionMenu', () => {
  test('renders the selected title, groups, and fires the action', () => {
    const onSelect = vi.fn()
    const onRemove = vi.fn()
    render(
      <EntityActionMenu
        title="L'Hopital's rule"
        groups={[
          {
            label: 'Generate',
            actions: [{ key: 'quiz', icon: ListChecks, label: 'Quiz', onSelect }],
          },
          {
            label: 'Edit mindmap',
            actions: [{ key: 'remove', icon: Trash2, label: 'Delete', danger: true, onSelect: onRemove }],
          },
        ]}
        onClose={() => undefined}
      />
    )
    expect(screen.getByText("L'Hopital's rule")).toBeInTheDocument()
    expect(screen.getByText('Generate')).toBeInTheDocument()
    expect(screen.getByText('Edit mindmap')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Quiz'))
    expect(onSelect).toHaveBeenCalled()

    fireEvent.click(screen.getByText('Delete'))
    expect(onRemove).toHaveBeenCalled()
  })
})
