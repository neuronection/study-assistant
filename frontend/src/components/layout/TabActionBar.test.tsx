import { fireEvent, render, screen } from '@testing-library/react'
import { BookOpen, ScrollText, Sparkles } from 'lucide-react'
import { describe, expect, test, vi } from 'vitest'

import { TabActionBar } from './TabActionBar'

describe('TabActionBar', () => {
  test('renders actions with outline buttons and calls back on click', () => {
    const onSecondary = vi.fn()
    render(
      <TabActionBar
        actions={[
          { label: 'Extract concepts', icon: Sparkles, onAction: () => {} },
          { label: 'Draft notes', icon: BookOpen, onAction: onSecondary },
        ]}
      />
    )
    const extract = screen.getByRole('button', { name: /extract concepts/i })
    expect(extract).toBeInTheDocument()
    const draft = screen.getByRole('button', { name: /draft notes/i })
    expect(draft).toBeInTheDocument()
    expect(extract.className).toContain('border')
    expect(draft.className).toContain('border')
    fireEvent.click(draft)
    expect(onSecondary).toHaveBeenCalledTimes(1)
  })

  test('primary action renders first with the default variant', () => {
    render(
      <TabActionBar
        actions={[
          { label: 'Import', onAction: () => {} },
          { label: 'Generate quiz', icon: Sparkles, onAction: () => {}, primary: true },
        ]}
      />
    )
    const buttons = screen.getAllByRole('button')
    expect(buttons[0]).toHaveTextContent('Generate quiz')
    expect(buttons[1]).toHaveTextContent('Import')
    expect(buttons[0].className).not.toContain('border')
    expect(buttons[1].className).toContain('border')
  })

  test('pending action shows a spinner and is disabled', () => {
    const onAction = vi.fn()
    render(
      <TabActionBar
        actions={[
          {
            label: 'Generate',
            icon: Sparkles,
            onAction,
            pending: true,
          },
        ]}
      />
    )
    const button = screen.getByRole('button', { name: /generate/i })
    expect(button).toBeDisabled()
    expect(button.querySelector('svg')).toHaveClass('animate-spin')
    fireEvent.click(button)
    expect(onAction).not.toHaveBeenCalled()
  })

  test('disabled actions do not fire', () => {
    const onAction = vi.fn()
    render(
      <TabActionBar actions={[{ label: 'Ask', onAction, disabled: true }]} />
    )
    const button = screen.getByRole('button', { name: /ask/i })
    expect(button).toBeDisabled()
    fireEvent.click(button)
    expect(onAction).not.toHaveBeenCalled()
  })

  test('renders the info slot after the actions', () => {
    render(
      <TabActionBar
        actions={[{ label: 'Extract', onAction: () => {} }]}
        info={<span>3 concepts · 2 links</span>}
      />
    )
    expect(screen.getByText('3 concepts · 2 links')).toBeInTheDocument()
    const bar = screen.getByText('3 concepts · 2 links').closest('div.ml-auto')
    expect(bar).not.toBeNull()
  })

  test('icons render at the button default size without per-call-site overrides', () => {
    render(
      <TabActionBar actions={[{ label: 'Import', icon: Sparkles, onAction: () => {} }]} />
    )
    const icon = screen.getByRole('button', { name: /import/i }).querySelector('svg')
    expect(icon?.getAttribute('class')).not.toContain('size-3.5')
  })

  test('menu actions render a dropdown whose items fire on select', () => {
    const onOpen = vi.fn()
    const onRegenerate = vi.fn()
    render(
      <TabActionBar
        actions={[
          {
            label: 'Cheat sheet',
            icon: ScrollText,
            menu: [
              { key: 'open', label: 'Open existing', onSelect: onOpen },
              { key: 'regenerate', label: 'Regenerate cheat sheet', onSelect: onRegenerate },
            ],
          },
        ]}
      />
    )
    const trigger = screen.getByRole('button', { name: /cheat sheet/i })
    expect(trigger).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /open existing/i })).not.toBeInTheDocument()
    fireEvent.click(trigger)
    expect(screen.getByRole('menuitem', { name: /open existing/i })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /regenerate cheat sheet/i })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem', { name: /regenerate cheat sheet/i }))
    expect(onRegenerate).toHaveBeenCalledTimes(1)
    expect(onOpen).not.toHaveBeenCalled()
  })
})
