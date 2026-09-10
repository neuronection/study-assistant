import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { DrawingBlock } from './DrawingBlock'
import type { DrawingMeta } from './DrawingImage'
import { DrawingDiffContext, type DrawingDiffStore } from './drawingDiffContext'

function renderWithDiff(
  store: DrawingDiffStore | null,
  meta: DrawingMeta,
  onAction: () => void = () => undefined
) {
  return render(
    <DrawingDiffContext.Provider value={store}>
      <DrawingBlock drawingId={3} meta={meta} onAction={onAction} />
    </DrawingDiffContext.Provider>
  )
}

describe('DrawingBlock', () => {
  test('shows a transcribing placeholder while the OCR job is pending', () => {
    const meta: DrawingMeta = {
      id: 3,
      png_sha: 'abc',
      ocr_markdown: null,
      ocr_job_id: 42,
    }
    render(<DrawingBlock drawingId={3} meta={meta} onAction={() => undefined} />)
    expect(screen.getByText('Transcribing…')).toBeInTheDocument()
    expect(screen.queryByText('OCR text')).not.toBeInTheDocument()
  })

  test('shows the transcript once OCR text exists', () => {
    const meta: DrawingMeta = {
      id: 3,
      png_sha: 'abc',
      ocr_markdown: '$2x$',
      ocr_job_id: null,
    }
    render(<DrawingBlock drawingId={3} meta={meta} onAction={() => undefined} />)
    expect(screen.queryByText('Transcribing…')).not.toBeInTheDocument()
    expect(screen.getByText('OCR text')).toBeInTheDocument()
  })

  test('shows neither pending nor transcript without OCR', () => {
    const meta: DrawingMeta = { id: 3, png_sha: 'abc', ocr_markdown: null }
    render(<DrawingBlock drawingId={3} meta={meta} onAction={() => undefined} />)
    expect(screen.queryByText('Transcribing…')).not.toBeInTheDocument()
    expect(screen.queryByText('OCR text')).not.toBeInTheDocument()
  })

  test('shows the old-vs-new diff while a re-OCR diff is pending review', () => {
    const meta: DrawingMeta = {
      id: 3,
      png_sha: 'abc',
      ocr_markdown: 'new transcript',
      ocr_job_id: null,
    }
    const store: DrawingDiffStore = {
      diffs: new Map([[3, { before: 'old transcript', after: 'new transcript' }]]),
      dismiss: vi.fn(),
    }
    const { container } = renderWithDiff(store, meta)
    expect(screen.getByText('changed')).toBeInTheDocument()
    expect(container.textContent).toContain('old transcript')
    expect(container.textContent).toContain('new transcript')
    fireEvent.click(screen.getByRole('button', { name: 'Show plain' }))
    expect(store.dismiss).toHaveBeenCalledWith(3)
  })

  test('dismissed diffs fall back to the plain transcript', () => {
    const meta: DrawingMeta = {
      id: 3,
      png_sha: 'abc',
      ocr_markdown: 'plain transcript',
      ocr_job_id: null,
    }
    const { container } = renderWithDiff(null, meta)
    expect(screen.queryByText('changed')).not.toBeInTheDocument()
    expect(container.textContent).toContain('plain transcript')
  })
})
