import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { ShortcutsDialog } from './ShortcutsDialog'
import { isTypingTarget } from '@/lib/shortcuts'

describe('ShortcutsDialog', () => {
  test('renders every group and keycap', () => {
    render(<ShortcutsDialog onClose={() => {}} />)
    expect(screen.getByText('Keyboard shortcuts')).toBeInTheDocument()
    for (const heading of ['General', 'Review', 'Library', 'Reading & study']) {
      expect(screen.getByRole('heading', { name: heading })).toBeInTheDocument()
    }
    for (const keys of ['Ctrl+K', 'Ctrl+Shift+K', '?', 'Space', '1–4', 'Enter', 'Ctrl+X', 'Del', 'Esc']) {
      expect(screen.getByText(keys)).toBeInTheDocument()
    }
  })

  test('closes on Escape', () => {
    const onClose = vi.fn()
    render(<ShortcutsDialog onClose={onClose} />)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  test('closes on backdrop click', () => {
    const onClose = vi.fn()
    const { container } = render(<ShortcutsDialog onClose={onClose} />)
    fireEvent.click(container.firstElementChild as HTMLElement)
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})

describe('isTypingTarget', () => {
  test('flags inputs, textareas, selects and contenteditable only', () => {
    const element = (html: string) => {
      const parent = document.createElement('div')
      parent.innerHTML = html
      return parent.firstElementChild
    }
    const editable = element('<div></div>') as HTMLElement
    Object.defineProperty(editable, 'isContentEditable', { value: true })
    expect(isTypingTarget(element('<input></input>'))).toBe(true)
    expect(isTypingTarget(element('<textarea></textarea>'))).toBe(true)
    expect(isTypingTarget(element('<select></select>'))).toBe(true)
    expect(isTypingTarget(editable)).toBe(true)
    expect(isTypingTarget(element('<div></div>'))).toBe(false)
    expect(isTypingTarget(window)).toBe(false)
  })
})
