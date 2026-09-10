import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import { AiGeneratedBadge } from './AiGeneratedBadge'

describe('AiGeneratedBadge', () => {
  test('renders the AI label with its tooltip', () => {
    render(<AiGeneratedBadge />)
    expect(screen.getByText('AI')).toBeInTheDocument()
    expect(screen.getByTitle('AI-generated content')).toBeInTheDocument()
  })
})
