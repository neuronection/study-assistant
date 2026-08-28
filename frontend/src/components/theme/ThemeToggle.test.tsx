import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { ThemeToggle } from './ThemeToggle'

describe('ThemeToggle', () => {
  beforeEach(() => {
    localStorage.removeItem('ca.theme')
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false })))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  test('cycles theme on consecutive clicks', () => {
    render(<ThemeToggle />)
    const button = screen.getByRole('button')

    expect(button).toHaveTextContent('System')

    fireEvent.click(button)
    expect(localStorage.getItem('ca.theme')).toBe('light')
    expect(button).toHaveTextContent('Light')
    expect(document.documentElement).not.toHaveClass('dark')

    fireEvent.click(button)
    expect(localStorage.getItem('ca.theme')).toBe('dark')
    expect(button).toHaveTextContent('Dark')
    expect(document.documentElement).toHaveClass('dark')

    fireEvent.click(button)
    expect(localStorage.getItem('ca.theme')).toBe('system')
    expect(button).toHaveTextContent('System')
    expect(document.documentElement).not.toHaveClass('dark')
  })

  test('second consecutive click applies a different theme', () => {
    render(<ThemeToggle />)
    const button = screen.getByRole('button')

    fireEvent.click(button)
    const first = localStorage.getItem('ca.theme')
    fireEvent.click(button)

    expect(localStorage.getItem('ca.theme')).not.toBe(first)
    expect(button).not.toHaveTextContent('System')
  })

  test('honors a stored theme on mount', () => {
    localStorage.setItem('ca.theme', 'dark')
    render(<ThemeToggle />)

    expect(screen.getByRole('button')).toHaveTextContent('Dark')
    expect(document.documentElement).toHaveClass('dark')
  })

  test('system theme follows the OS preference', () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true })))
    localStorage.setItem('ca.theme', 'system')
    render(<ThemeToggle />)

    expect(document.documentElement).toHaveClass('dark')
  })

  test('announces the next theme', () => {
    render(<ThemeToggle />)
    expect(screen.getByRole('button', { name: /light/i })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button'))
    expect(screen.getByRole('button', { name: /dark/i })).toBeInTheDocument()

    cleanup()
    localStorage.setItem('ca.theme', 'dark')
    render(<ThemeToggle />)
    expect(screen.getByRole('button', { name: /system/i })).toBeInTheDocument()
  })
})
