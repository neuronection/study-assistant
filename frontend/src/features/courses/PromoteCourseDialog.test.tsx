import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { PromoteCourseDialog } from './PromoteCourseDialog'

describe('PromoteCourseDialog', () => {
  test('prefills the title from the node and submits the fields', () => {
    const onConfirm = vi.fn()
    render(
      <PromoteCourseDialog
        nodeTitle="Group theory"
        busy={false}
        error={null}
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />
    )
    expect(screen.getByPlaceholderText('Course name')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Group theory')).toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText('Course name'), {
      target: { value: 'Abstract Algebra' },
    })
    fireEvent.change(screen.getByPlaceholderText('Subject (optional)'), {
      target: { value: 'Mathematics' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create course' }))
    expect(onConfirm).toHaveBeenCalledWith({
      title: 'Abstract Algebra',
      subject: 'Mathematics',
      level: null,
      color: null,
    })
  })

  test('keeps Create disabled without a title and reports errors', () => {
    const onConfirm = vi.fn()
    render(
      <PromoteCourseDialog
        nodeTitle=""
        busy={false}
        error="Could not promote to course"
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />
    )
    expect(screen.getByRole('button', { name: 'Create course' })).toBeDisabled()
    expect(screen.getByRole('alert')).toHaveTextContent('Could not promote to course')
    expect(onConfirm).not.toHaveBeenCalled()
  })
})
