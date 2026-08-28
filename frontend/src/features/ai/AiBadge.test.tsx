import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import { AiBadge } from './AiBadge'

describe('AiBadge', () => {
  test('renders the AI label with its tooltip', () => {
    render(<AiBadge />)
    expect(screen.getByText('AI')).toBeInTheDocument()
    expect(screen.getByTitle('AI-generated content')).toBeInTheDocument()
  })
})
