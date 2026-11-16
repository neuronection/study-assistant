import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { CaptureInboxDialog } from './CaptureInboxDialog'
import type { CaptureInboxState } from './useCaptureInbox'
import type { CaptureJournalOp } from '@/lib/offline/journal'
import type { CaptureStaging } from '@/lib/api'

function item(overrides: Partial<CaptureStaging> = {}): CaptureStaging {
  return {
    id: 'c1',
    source_kind: 'camera',
    status: 'staged',
    filename: 'page-1.jpg',
    mime: 'image/jpeg',
    blob_sha: 'a'.repeat(64),
    byte_size: 2048,
    group_id: null,
    created_at: '2026-11-10T10:00:00Z',
    expires_at: '2026-11-17T10:00:00Z',
    material_id: null,
    ...overrides,
  }
}

function state(overrides: Partial<CaptureInboxState> = {}): CaptureInboxState {
  return {
    items: [item()],
    queued: [],
    durable: true,
    open: true,
    show: vi.fn(),
    busy: false,
    error: null,
    openFiles: vi.fn(),
    commit: vi.fn(),
    assemble: vi.fn(),
    discard: vi.fn(),
    retryQueued: vi.fn(),
    retryAllQueued: vi.fn(),
    removeQueued: vi.fn(),
    close: vi.fn(),
    ...overrides,
  }
}

function queuedOp(overrides: Partial<CaptureJournalOp> = {}): CaptureJournalOp {
  return {
    id: 'op1',
    entity: 'capture',
    createdAt: 1,
    attempts: 0,
    lastError: null,
    failed: false,
    payload: {
      filename: 'offline.jpg',
      mime: 'image/jpeg',
      size: 4096,
      sourceKind: 'camera',
    },
    ...overrides,
  }
}

describe('CaptureInboxDialog', () => {
  test('lists staged captures with size and status', () => {
    render(<CaptureInboxDialog state={state()} courseId="course-1" />)
    expect(screen.getByText('page-1.jpg')).toBeInTheDocument()
    expect(screen.getByText(/2 KB/)).toBeInTheDocument()
    expect(screen.getByText(/staged/)).toBeInTheDocument()
  })

  test('commits and discards a staged item', () => {
    const commit = vi.fn()
    const discard = vi.fn()
    render(
      <CaptureInboxDialog state={state({ commit, discard })} courseId="course-1" />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    expect(commit).toHaveBeenCalledWith('c1')
    fireEvent.click(screen.getByRole('button', { name: 'Discard' }))
    expect(discard).toHaveBeenCalledWith('c1')
  })

  test('add all commits every staged item', () => {
    const commit = vi.fn()
    render(
      <CaptureInboxDialog
        state={state({
          commit,
          items: [
            item({ id: 'c1' }),
            item({ id: 'c2', filename: 'page-2.jpg' }),
          ],
        })}
        courseId="course-1"
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /Add all \(2\)/ }))
    expect(commit.mock.calls.map(([id]) => id)).toEqual(['c1', 'c2'])
  })

  test('shows the committed link and the need-course state', () => {
    render(
      <CaptureInboxDialog
        state={state({
          items: [item({ status: 'committed', material_id: 'm1' })],
        })}
        courseId="course-1"
      />,
    )
    expect(screen.getByRole('link', { name: /Open/ })).toHaveAttribute(
      'href',
      '/library/m1',
    )
  })

  test('disables Add when no course is open and shows the error', () => {
    render(
      <CaptureInboxDialog
        state={state({ error: 'upload failed' })}
        courseId={null}
      />,
    )
    expect(screen.getByRole('button', { name: 'Add' })).toBeDisabled()
    expect(screen.getByText('upload failed')).toBeInTheDocument()
    expect(screen.getByText(/Open a course/)).toBeInTheDocument()
  })
})

describe('CaptureInboxDialog offline queue', () => {
  test('shows waiting captures, where they are saved, and retries', () => {
    const retryQueued = vi.fn()
    const retryAllQueued = vi.fn()
    render(
      <CaptureInboxDialog
        state={state({
          items: [],
          queued: [queuedOp()],
          retryQueued,
          retryAllQueued,
        })}
        courseId="course-1"
      />,
    )
    expect(screen.getByText('1 waiting for connection')).toBeInTheDocument()
    expect(screen.getByText('Saved on this device')).toBeInTheDocument()
    expect(screen.getByText(/offline\.jpg/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(retryQueued).toHaveBeenCalledWith('op1')
    fireEvent.click(screen.getByRole('button', { name: 'Retry all' }))
    expect(retryAllQueued).toHaveBeenCalled()
  })

  test('shows a failed upload with its reason and removes it', () => {
    const removeQueued = vi.fn()
    render(
      <CaptureInboxDialog
        state={state({
          items: [],
          durable: false,
          queued: [
            queuedOp({
              failed: true,
              attempts: 2,
              lastError: 'Unsupported file type',
            }),
          ],
          removeQueued,
        })}
        courseId="course-1"
      />,
    )
    expect(screen.getByText(/Unsupported file type/)).toBeInTheDocument()
    expect(screen.getByText('Kept for this session only')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Remove' }))
    expect(removeQueued).toHaveBeenCalledWith('op1')
  })
})
