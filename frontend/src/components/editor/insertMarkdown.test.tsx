import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, test, vi } from 'vitest'

import type { MarkdownEditorApi } from './MarkdownEditor'
import { MarkdownEditor } from './MarkdownEditor'

vi.mock('mermaid', () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn(async (_id: string, code: string) => ({
      svg: `<svg data-testid="mermaid-svg" data-code="${code}"></svg>`,
    })),
  },
}))

vi.mock('@/components/canvas/DrawCanvas', () => ({
  DrawCanvas: ({ onChange }: { strokes: unknown[]; onChange: (s: unknown[]) => void }) => (
    <div>
      <button type="button" onClick={() => onChange([{ points: [[0, 0]], color: '#000', width: 2 }])}>
        stub-stroke
      </button>
    </div>
  ),
  strokesToPng: () => 'data:image/png;base64,AAA',
  exportDrawing: () => ({
    dataUrl: 'data:image/png;base64,AAA',
    view: { x: -4, y: -4, width: 8, height: 8 },
  }),
  strokeBounds: () => null,
}))

function proseRoot(): HTMLElement {
  const node = document.querySelector('.ProseMirror')
  if (node === null) {
    throw new Error('prosemirror root not mounted')
  }
  return node as HTMLElement
}

function placeCaretAtStart(): void {
  const root = proseRoot()
  const node = root.firstChild as Node | null
  if (node === null) {
    return
  }
  const selection = window.getSelection()
  const range = document.createRange()
  range.setStart(node, 0)
  range.setEnd(node, 0)
  selection?.removeAllRanges()
  selection?.addRange(range)
  document.dispatchEvent(new Event('selectionchange'))
}

function selectAll(): void {
  const selection = window.getSelection()
  const range = document.createRange()
  const textNode = proseRoot().querySelector('p')?.firstChild as Node | null
  if (textNode === null) {
    return
  }
  range.setStart(textNode, 0)
  range.setEnd(textNode, textNode.textContent?.length ?? 0)
  selection?.removeAllRanges()
  selection?.addRange(range)
  document.dispatchEvent(new Event('selectionchange'))
}

function selectionIntact(): boolean {
  const selection = window.getSelection()
  return (
    selection !== null &&
    !selection.isCollapsed &&
    selection.anchorNode !== null &&
    proseRoot().contains(selection.anchorNode)
  )
}

function mount(value: string, onChange: (markdown: string) => void) {
  const api: { current: MarkdownEditorApi | null } = { current: null }
  const view = render(
    <MarkdownEditor value={value} onChange={onChange} ariaLabel="Note body" apiRef={api} />
  )
  return { api, view }
}

async function ready(api: { current: MarkdownEditorApi | null }, text: string) {
  await waitFor(() => expect(proseRoot().textContent).toContain(text))
  await waitFor(() => expect(api.current).not.toBeNull())
}

describe('insertMarkdown', () => {
  test('inserts block content at the cursor and round-trips display math', async () => {
    const onChange = vi.fn()
    const { api } = mount('first line', onChange)
    await ready(api, 'first line')
    placeCaretAtStart()
    await act(async () => {
      api.current?.insertMarkdown('$$E = mc^2$$', 'at-cursor')
    })
    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith(
        expect.stringContaining('E = mc^2')
      )
    )
  })

  test('replace-selection swaps the selected text', async () => {
    const onChange = vi.fn()
    const { api } = mount('old words here', onChange)
    await ready(api, 'old words here')
    selectAll()
    await act(async () => {
      api.current?.insertMarkdown('replacement text', 'replace-selection')
    })
    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith(
        expect.stringContaining('replacement text')
      )
    )
    const latest = onChange.mock.calls.at(-1)?.[0] as string
    expect(latest).not.toContain('old words')
  })

  test('after-block inserts a new block below the current one', async () => {
    const onChange = vi.fn()
    const { api } = mount('first block', onChange)
    await ready(api, 'first block')
    placeCaretAtStart()
    await act(async () => {
      api.current?.insertMarkdown('second block', 'after-block')
    })
    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith(
        expect.stringContaining('second block')
      )
    )
    const latest = onChange.mock.calls.at(-1)?.[0] as string
    expect(latest).toContain('first block')
  })

  test('insertion is undoable', async () => {
    function Harness() {
      const [value, setValue] = useState('hello')
      return (
        <MarkdownEditor value={value} onChange={setValue} ariaLabel="Note body" apiRef={api} />
      )
    }
    const api: { current: MarkdownEditorApi | null } = { current: null }
    render(<Harness />)
    await ready(api, 'hello')
    placeCaretAtStart()
    await act(async () => {
      api.current?.insertMarkdown('inserted bit', 'at-cursor')
    })
    await waitFor(() => expect(proseRoot().textContent).toContain('inserted bit'))
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
    await waitFor(() => expect(proseRoot().textContent).not.toContain('inserted bit'))
  })

  test('a text selection survives opening the AI popover and clicking inside it', async () => {
    render(
      <MarkdownEditor
        value="hello world here"
        onChange={vi.fn()}
        ariaLabel="Note body"
        aiHelper={{ courseId: 1, nodeId: 2, title: 'Note' }}
      />
    )
    await waitFor(() => expect(proseRoot().textContent).toContain('hello world here'))
    selectAll()
    fireEvent.click(screen.getByRole('button', { name: 'AI helper' }))
    await screen.findByRole('dialog', { name: 'AI helper' })
    expect(selectionIntact()).toBe(true)
    fireEvent.click(screen.getByText('Context'))
    expect(selectionIntact()).toBe(true)
  })
})