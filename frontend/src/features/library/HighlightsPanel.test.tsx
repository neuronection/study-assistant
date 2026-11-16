import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { HighlightsPanel } from './HighlightsPanel'
import type { Anchor } from '@/lib/api'

function anchor(overrides: Partial<Anchor> = {}): Anchor {
  return {
    id: 'a1',
    material_id: 'm1',
    anchor_kind: 'text_range',
    page: null,
    quote: 'the derivative of a composite function',
    payload: { version_id: 'e1', start: 10, end: 50, occurrence: 0 },
    color: 'yellow',
    note_md: null,
    source: 'user',
    created_at: '2026-11-10T10:00:00Z',
    updated_at: '2026-11-10T10:00:00Z',
    orphaned: false,
    ...overrides,
  }
}

describe('HighlightsPanel', () => {
  test('renders an empty state and the highlight quote', () => {
    const { rerender } = render(
      <HighlightsPanel
        anchors={[]}
        busy={false}
        onPatch={vi.fn()}
        onDelete={vi.fn()}
        onJump={vi.fn()}
      />,
    )
    expect(screen.getByText(/Select text in the material/)).toBeInTheDocument()

    rerender(
      <HighlightsPanel
        anchors={[anchor()]}
        busy={false}
        onPatch={vi.fn()}
        onDelete={vi.fn()}
        onJump={vi.fn()}
      />,
    )
    expect(screen.getByText(/the derivative of a composite function/)).toBeInTheDocument()
  })

  test('jumps, recolors and deletes', async () => {
    const onJump = vi.fn()
    const onPatch = vi.fn().mockResolvedValue(undefined)
    const onDelete = vi.fn().mockResolvedValue(undefined)
    render(
      <HighlightsPanel
        anchors={[anchor()]}
        busy={false}
        onPatch={onPatch}
        onDelete={onDelete}
        onJump={onJump}
      />,
    )
    fireEvent.click(screen.getByTitle('Jump to highlight'))
    expect(onJump).toHaveBeenCalledWith('a1')

    fireEvent.click(screen.getByRole('button', { name: 'Green' }))
    expect(onPatch).toHaveBeenCalledWith('a1', { color: 'green' })

    fireEvent.click(screen.getByRole('button', { name: 'Delete highlight' }))
    expect(onDelete).toHaveBeenCalledWith('a1')
  })

  test('edits a note and shows the orphaned warning', async () => {
    const onPatch = vi.fn().mockResolvedValue(undefined)
    render(
      <HighlightsPanel
        anchors={[anchor({ orphaned: true, note_md: 'old note' })]}
        busy={false}
        onPatch={onPatch}
        onDelete={vi.fn()}
        onJump={vi.fn()}
      />,
    )
    expect(screen.getByText(/Source changed/)).toBeInTheDocument()
    fireEvent.click(screen.getByText('old note'))
    const input = screen.getByLabelText('Highlight note') as HTMLTextAreaElement
    expect(input.value).toBe('old note')
    fireEvent.change(input, { target: { value: 'fresh note' } })
    fireEvent.click(screen.getByRole('button', { name: /Save note/ }))
    await waitFor(() =>
      expect(onPatch).toHaveBeenCalledWith('a1', { note_md: 'fresh note' }),
    )
  })
})
