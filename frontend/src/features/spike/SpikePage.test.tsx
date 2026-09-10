import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import { CanvasCard } from './SpikePage'

describe('SpikePage canvas card', () => {
  test('renders the shared DrawCanvas (toolbar + canvas) instead of the broken spike canvas', () => {
    render(<CanvasCard />)
    expect(screen.getByRole('toolbar', { name: 'Drawing tools' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Pen' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Eraser' })).toBeInTheDocument()
    expect(screen.getByLabelText('Handwriting canvas')).toBeInTheDocument()
  })
})