import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { ScanPages } from './ScanPages'
import type { CaptureStaging } from '@/lib/api'

function page(id: string, name: string): CaptureStaging {
  return {
    id,
    source_kind: 'camera',
    status: 'staged',
    filename: name,
    mime: 'image/png',
    blob_sha: 'a'.repeat(64),
    byte_size: 1024,
    group_id: null,
    created_at: '2026-11-10T10:00:00Z',
    expires_at: '2026-11-17T10:00:00Z',
    material_id: null,
  }
}

describe('ScanPages', () => {
  test('combines pages in the displayed order with rotations and a title', async () => {
    const onAssemble = vi.fn().mockResolvedValue(undefined)
    render(
      <ScanPages
        items={[page('a', 'one.png'), page('b', 'two.png')]}
        busy={false}
        onAssemble={onAssemble}
        onDiscard={vi.fn()}
      />,
    )
    fireEvent.click(screen.getAllByRole('button', { name: 'Move page down' })[0])
    fireEvent.click(screen.getAllByRole('button', { name: 'Rotate page' })[0])
    fireEvent.change(screen.getByLabelText('Scan title'), {
      target: { value: 'Problem set' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Combine 2 into PDF/ }))
    expect(onAssemble).toHaveBeenCalledWith(
      [
        { captureId: 'b', rotation: 90 },
        { captureId: 'a', rotation: 0 },
      ],
      'Problem set'
    )
  })

  test('removes a page', () => {
    const onDiscard = vi.fn().mockResolvedValue(undefined)
    render(
      <ScanPages
        items={[page('a', 'one.png'), page('b', 'two.png')]}
        busy={false}
        onAssemble={vi.fn()}
        onDiscard={onDiscard}
      />,
    )
    fireEvent.click(screen.getAllByRole('button', { name: 'Remove page' })[0])
    expect(onDiscard).toHaveBeenCalledWith('a')
  })
})
