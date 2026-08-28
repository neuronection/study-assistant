import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { ExpandableSearch } from './ExpandableSearch'

describe('ExpandableSearch', () => {
  test('renders collapsed as an icon-only button and expands on click', () => {
    render(<ExpandableSearch value="" onChange={() => {}} placeholder="Search…" ariaLabel="Search items" />)
    const toggle = screen.getByRole('button', { name: 'Search' })
    expect(screen.queryByRole('textbox', { name: 'Search items' })).not.toBeInTheDocument()
    fireEvent.click(toggle)
    const input = screen.getByRole('textbox', { name: 'Search items' })
    expect(input).toHaveAttribute('placeholder', 'Search…')
  })

  test('starts expanded when the value is non-empty', () => {
    render(
      <ExpandableSearch value="calc" onChange={() => {}} placeholder="Search…" ariaLabel="Search items" />
    )
    expect(screen.getByRole('textbox', { name: 'Search items' })).toHaveValue('calc')
  })

  test('onSubmit receives the current value on form submit', () => {
    const onSubmit = vi.fn()
    render(
      <ExpandableSearch
        value="limits"
        onChange={() => {}}
        onSubmit={onSubmit}
        placeholder="Search…"
        ariaLabel="Search items"
      />
    )
    fireEvent.submit(screen.getByRole('textbox', { name: 'Search items' }).closest('form')!)
    expect(onSubmit).toHaveBeenCalledWith('limits')
  })

  test('clear button resets the value and fires onClear', () => {
    const onChange = vi.fn()
    const onClear = vi.fn()
    render(
      <ExpandableSearch
        value="limits"
        onChange={onChange}
        onClear={onClear}
        placeholder="Search…"
        ariaLabel="Search items"
        clearLabel="Clear search"
      />
    )
    fireEvent.click(screen.getByRole('button', { name: 'Clear search' }))
    expect(onChange).toHaveBeenCalledWith('')
    expect(onClear).toHaveBeenCalledTimes(1)
  })

  test('Escape clears a non-empty query', () => {
    const onChange = vi.fn()
    render(
      <ExpandableSearch value="limits" onChange={onChange} placeholder="Search…" ariaLabel="Search items" />
    )
    fireEvent.keyDown(screen.getByRole('textbox', { name: 'Search items' }), { key: 'Escape' })
    expect(onChange).toHaveBeenCalledWith('')
  })

  test('Escape collapses an empty expanded search', () => {
    render(<ExpandableSearch value="" onChange={() => {}} placeholder="Search…" ariaLabel="Search items" />)
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))
    fireEvent.keyDown(screen.getByRole('textbox', { name: 'Search items' }), { key: 'Escape' })
    expect(screen.queryByRole('textbox', { name: 'Search items' })).not.toBeInTheDocument()
  })

  test('blurring an empty expanded search collapses it', () => {
    render(<ExpandableSearch value="" onChange={() => {}} placeholder="Search…" ariaLabel="Search items" />)
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))
    fireEvent.blur(screen.getByRole('textbox', { name: 'Search items' }))
    expect(screen.queryByRole('textbox', { name: 'Search items' })).not.toBeInTheDocument()
  })
})
