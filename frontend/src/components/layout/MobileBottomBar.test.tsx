import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { MobileBottomBar } from './MobileBottomBar'

describe('MobileBottomBar', () => {
  test('renders the five primary actions and the due badge', () => {
    render(
      <MobileBottomBar
        activePath="/review"
        dueCount={7}
        onNavigate={vi.fn()}
        onCapture={vi.fn()}
        onSearch={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: /Home/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Courses/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Review/ })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(screen.getByText('7')).toBeInTheDocument()
    expect(screen.getByText('Capture')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /More/ })).toBeInTheDocument()
  })

  test('closes the More sheet on Escape, outside pointerdown and route change', () => {
    const props = {
      dueCount: 0,
      onNavigate: vi.fn(),
      onCapture: vi.fn(),
      onSearch: vi.fn(),
    }
    const { rerender } = render(<MobileBottomBar activePath="/" {...props} />)
    const more = screen.getByRole('button', { name: /More/ })

    fireEvent.click(more)
    expect(screen.getByRole('menu', { name: 'More' })).toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('menu', { name: 'More' })).not.toBeInTheDocument()

    fireEvent.click(more)
    expect(screen.getByRole('menu', { name: 'More' })).toBeInTheDocument()
    fireEvent.pointerDown(document.body)
    expect(screen.queryByRole('menu', { name: 'More' })).not.toBeInTheDocument()

    fireEvent.click(more)
    expect(screen.getByRole('menu', { name: 'More' })).toBeInTheDocument()
    rerender(<MobileBottomBar activePath="/courses" {...props} />)
    expect(screen.queryByRole('menu', { name: 'More' })).not.toBeInTheDocument()
  })

  test('navigates and opens the More sheet', () => {
    const onNavigate = vi.fn()
    const onSearch = vi.fn()
    render(
      <MobileBottomBar
        activePath="/"
        dueCount={0}
        onNavigate={onNavigate}
        onCapture={vi.fn()}
        onSearch={onSearch}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /Courses/ }))
    expect(onNavigate).toHaveBeenCalledWith('/courses')

    fireEvent.click(screen.getByRole('button', { name: /More/ }))
    expect(screen.getByRole('menu', { name: 'More' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem', { name: /Settings/ }))
    expect(onNavigate).toHaveBeenCalledWith('/settings')

    fireEvent.click(screen.getByRole('button', { name: /More/ }))
    fireEvent.click(screen.getByRole('menuitem', { name: /Search/ }))
    expect(onSearch).toHaveBeenCalled()
  })
})
