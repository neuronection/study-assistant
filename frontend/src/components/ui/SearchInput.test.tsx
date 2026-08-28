import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { SearchInput } from './SearchInput'

function renderInput(props: Partial<Parameters<typeof SearchInput>[0]> = {}) {
  const onChange = vi.fn()
  render(
    <SearchInput
      value=""
      onChange={onChange}
      placeholder="Search…"
      ariaLabel="Search models"
      {...props}
    />
  )
  return { onChange }
}

describe('SearchInput', () => {
  test('renders placeholder and reports changes', () => {
    const { onChange } = renderInput({ value: 'flash' })
    const input = screen.getByRole('textbox', { name: /search models/i })
    expect(input).toHaveValue('flash')
    expect(input).toHaveAttribute('placeholder', 'Search…')
    fireEvent.change(input, { target: { value: 'pro' } })
    expect(onChange).toHaveBeenCalledWith('pro')
  })

  test('clear button appears only with a value and resets it', () => {
    const { onChange } = renderInput({ value: 'abc' })
    expect(screen.getByRole('button', { name: /clear search/i })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /clear search/i }))
    expect(onChange).toHaveBeenCalledWith('')

    cleanup()
    renderInput({ value: '' })
    expect(screen.queryByRole('button', { name: /clear search/i })).not.toBeInTheDocument()
  })

  test('honors a custom clear label', () => {
    renderInput({ value: 'x', clearLabel: 'Reset filter' })
    expect(screen.getByRole('button', { name: /reset filter/i })).toBeInTheDocument()
  })
})
