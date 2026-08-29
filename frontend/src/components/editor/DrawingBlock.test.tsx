import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import { DrawingBlock } from './DrawingBlock'
import type { DrawingMeta } from './DrawingImage'

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
})
