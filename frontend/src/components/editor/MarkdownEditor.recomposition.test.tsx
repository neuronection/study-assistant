import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { MarkdownEditor } from './MarkdownEditor'

vi.mock('mermaid', () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn(async (_id: string, code: string) => ({
      svg: `<svg data-testid="mermaid-svg" data-code="${code}"></svg>`,
    })),
  },
}))

function proseRoot(): HTMLElement {
  const node = document.querySelector('.ProseMirror')
  if (node === null) {
    throw new Error('prosemirror root not mounted')
  }
  return node as HTMLElement
}

describe('MarkdownEditor recomposition', () => {
  test('composes on the library primitive: toolbar, h2+h3 toggles, prose-notes content class', async () => {
    render(<MarkdownEditor value="body" onChange={vi.fn()} ariaLabel="Note body" />)
    await waitFor(() => expect(proseRoot().textContent).toContain('body'))
    expect(screen.getByRole('toolbar', { name: 'Formatting' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Heading' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Subheading' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Heading 3' })).toBeNull()
    expect(proseRoot().className).toContain('prose-notes')
    expect(proseRoot().className).toContain('min-h-56')
    expect(proseRoot().closest('[data-as="rich-text-editor"]')).not.toBeNull()
    expect(screen.getByRole('button', { name: 'Dictate' })).toBeInTheDocument()
  })

  test('math hint lives in a toolbar help popover; the permanent paragraph is gone (plan 62-C)', async () => {
    render(<MarkdownEditor value="body" onChange={vi.fn()} ariaLabel="Note body" />)
    await waitFor(() => expect(proseRoot().textContent).toContain('body'))
    expect(screen.queryByText(/Math and Mermaid diagrams render live/)).not.toBeInTheDocument()

    const chrome = screen.getByTestId('editor-chrome')
    expect(chrome.querySelector('[role="toolbar"]')).not.toBeNull()
    expect(chrome.className).toContain('group/editor')
    expect(chrome.className).toContain('flex-1')
    expect(chrome.className).toContain(
      '[&_[data-as=rich-text-editor]>div:not([role=toolbar])]:overflow-y-auto'
    )

    fireEvent.click(screen.getByRole('button', { name: 'Editor help' }))
    expect(await screen.findByText(/Math and Mermaid diagrams render live/)).toBeInTheDocument()
  })
})
