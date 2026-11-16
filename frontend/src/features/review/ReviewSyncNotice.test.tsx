import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { PendingSyncNotice } from './ReviewSyncNotice'

describe('PendingSyncNotice', () => {
  test('shows the queued count and syncs', () => {
    const onSync = vi.fn()
    render(<PendingSyncNotice count={2} busy={false} onSync={onSync} />)
    expect(screen.getByText('2 ratings saved offline')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Sync now/ }))
    expect(onSync).toHaveBeenCalled()
  })

  test('renders nothing when the queue is empty', () => {
    const { container } = render(
      <PendingSyncNotice count={0} busy={false} onSync={vi.fn()} />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})
