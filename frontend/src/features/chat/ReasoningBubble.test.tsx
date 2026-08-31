import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, test } from 'vitest'

import { ReasoningBubble } from './ReasoningBubble'
import { storageKeys } from '@/lib/constants'

describe('ReasoningBubble', () => {
  afterEach(() => {
    window.localStorage.clear()
  })

  test('shows the thinking text and toggles it off', () => {
    render(<ReasoningBubble text="I should apply the power rule." />)
    const button = screen.getByRole('button', { name: 'Show or hide the thinking process' })
    expect(button).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('I should apply the power rule.')).toBeInTheDocument()
    fireEvent.click(button)
    expect(button).toHaveAttribute('aria-expanded', 'false')
  })

  test('respects a persisted collapsed preference', () => {
    window.localStorage.setItem(storageKeys.chatReasoningOpen, '0')
    render(<ReasoningBubble text="hidden by preference" />)
    expect(screen.queryByText('hidden by preference')).not.toBeInTheDocument()
  })
})
