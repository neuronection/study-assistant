import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'
import { useState } from 'react'

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
  DrawCanvas: ({
    onChange,
    focus,
  }: {
    strokes: unknown[]
    onChange: (strokes: unknown[]) => void
    focus?: unknown
  }) => (
    <div>
      <span
        aria-label="Handwriting canvas"
        data-testid="canvas-focus"
        data-focus={focus === undefined || focus === null ? 'none' : JSON.stringify(focus)}
      />
      <button
        type="button"
        onClick={() => onChange([{ points: [[0, 0]], color: '#1a1a1a', width: 2 }])}
      >
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

function pointAt(element: Element | null): void {
  Object.defineProperty(document, 'elementFromPoint', {
    configurable: true,
    value: () => element ?? document.body,
  })
}

function clickElement(element: HTMLElement): void {
  pointAt(element)
  fireEvent.mouseDown(element, { clientX: 50, clientY: 10 })
  fireEvent.mouseUp(element, { clientX: 50, clientY: 10 })
}

function placeCaret(element: HTMLElement): void {
  const selection = window.getSelection()
  const range = document.createRange()
  range.setStart(element.firstChild as Node, 0)
  range.setEnd(element.firstChild as Node, 0)
  selection?.removeAllRanges()
  selection?.addRange(range)
  document.dispatchEvent(new Event('selectionchange'))
}

describe('MarkdownEditor', () => {
  test('external value sync never emits onChange back to the parent', async () => {
    const onChange = vi.fn()
    const { rerender } = render(
      <MarkdownEditor value="first content" onChange={onChange} ariaLabel="Note body" />
    )
    await waitFor(() => expect(proseRoot().textContent).toContain('first content'))

    rerender(<MarkdownEditor value="" onChange={onChange} ariaLabel="Note body" />)
    await waitFor(() => expect(proseRoot().textContent).toBe(''))
    expect(onChange).not.toHaveBeenCalled()

    rerender(
      <MarkdownEditor value="first content" onChange={onChange} ariaLabel="Note body" />
    )
    await waitFor(() => expect(proseRoot().textContent).toContain('first content'))
    expect(onChange).not.toHaveBeenCalled()
  })

  test('multiline notes keep their blank lines through emit and re-receive', async () => {
    const initial = 'para one\n\n\n\npara two'
    let emitted = initial
    const api: { current: MarkdownEditorApi | null } = { current: null }
    const track = (next: string) => {
      emitted = next
    }
    const { rerender } = render(
      <MarkdownEditor
        value={initial}
        onChange={track}
        ariaLabel="Note body"
        apiRef={api}
      />
    )
    await waitFor(() => expect(proseRoot().textContent).toContain('para two'))
    await waitFor(() => expect(api.current).not.toBeNull())

    api.current?.insertQuote('middle', null)
    await waitFor(() => expect(emitted).toContain('> middle'))
    expect(emitted).toContain('para one\n\n\n\npara two')

    const paragraphBefore = proseRoot().firstElementChild
    rerender(
      <MarkdownEditor
        value={emitted}
        onChange={track}
        ariaLabel="Note body"
        apiRef={api}
      />
    )
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(proseRoot().firstElementChild).toBe(paragraphBefore)
  })

  test('typed empty paragraphs survive emit; leading ones are trimmed', async () => {
    let emitted = ''
    const api: { current: MarkdownEditorApi | null } = { current: null }
    function Harness() {
      const [value, setValue] = useState('a\n\n\nb')
      return (
        <MarkdownEditor
          value={value}
          onChange={(next) => {
            emitted = next
            setValue(next)
          }}
          ariaLabel="Note body"
          apiRef={api}
          drawings={[{ id: 7, png_sha: 'abc', ocr_markdown: null }]}
        />
      )
    }
    render(<Harness />)
    await waitFor(() => expect(proseRoot().textContent).toContain('b'))
    await waitFor(() => expect(api.current).not.toBeNull())

    api.current?.insertDrawing(7)
    await waitFor(() => expect(emitted).toContain('ca-drawing://7'))
    expect(emitted).toContain('a\n\n\nb')
    expect(emitted).not.toContain('&nbsp;')
    expect(emitted).not.toContain('\u00A0')
  })

  test('empty paragraphs typed between blocks are kept in the emitted markdown', async () => {
    let emitted = ''
    const api: { current: MarkdownEditorApi | null } = { current: null }
    render(
      <MarkdownEditor
        value={'one\n\ntwo'}
        onChange={(next) => {
          emitted = next
        }}
        ariaLabel="Note body"
        apiRef={api}
      />
    )
    await waitFor(() => expect(proseRoot().textContent).toContain('two'))
    await waitFor(() => expect(api.current).not.toBeNull())

    api.current?.insertQuote('q', null)
    await waitFor(() => expect(emitted).toContain('> q'))

    proseRoot().focus()
    fireEvent.keyDown(proseRoot(), { key: 'Enter' })
    fireEvent.keyDown(proseRoot(), { key: 'Enter' })
    await waitFor(() => expect(emitted).toBe('> q\n\n\n\none\n\ntwo'))
  })

  test('blank lines load as truly empty paragraphs with no space characters', async () => {
    let emitted = ''
    const { rerender } = render(
      <MarkdownEditor
        value={'a\n\n\n\nb'}
        onChange={(next) => {
          emitted = next
        }}
        ariaLabel="Note body"
      />
    )
    await waitFor(() => expect(proseRoot().textContent).toContain('b'))
    expect(proseRoot().textContent).not.toContain('\u00A0')
    const paragraphs = Array.from(proseRoot().querySelectorAll('p'))
    expect(paragraphs).toHaveLength(4)
    expect(paragraphs[1]?.textContent).toBe('')
    expect(paragraphs[2]?.textContent).toBe('')

    rerender(
      <MarkdownEditor
        value={'x\n\n\ny\n\n\n\nz'}
        onChange={(next) => {
          emitted = next
        }}
        ariaLabel="Note body"
      />
    )
    await waitFor(() => expect(proseRoot().textContent).toContain('z'))
    expect(proseRoot().textContent).not.toContain('\u00A0')
    const emptyCount = Array.from(proseRoot().querySelectorAll('p')).filter(
      (p) => p.textContent === ''
    ).length
    expect(emptyCount).toBe(3)
    expect(emitted).toBe('')
  })

  test('empty paragraphs typed before the first text are trimmed from the emit', async () => {
    let emitted = ''
    render(
      <MarkdownEditor
        value={'one\n\ntwo'}
        onChange={(next) => {
          emitted = next
        }}
        ariaLabel="Note body"
      />
    )
    await waitFor(() => expect(proseRoot().textContent).toContain('two'))

    proseRoot().focus()
    fireEvent.keyDown(proseRoot(), { key: 'Enter' })
    fireEvent.keyDown(proseRoot(), { key: 'Enter' })
    await waitFor(() => expect(emitted).toBe('one\n\ntwo'))
    expect(proseRoot().firstElementChild?.textContent).toBe('')
    expect(proseRoot().children[2]?.textContent).toBe('one')
  })

  test('receiving the emitted value back does not replace the document', async () => {
    const onChange = vi.fn()
    let emitted = ''
    const api: { current: MarkdownEditorApi | null } = { current: null }
    const track = (next: string) => {
      emitted = next
      onChange(next)
    }
    const { rerender } = render(
      <MarkdownEditor value="hello" onChange={track} ariaLabel="Note body" apiRef={api} />
    )
    await waitFor(() => expect(proseRoot().textContent).toContain('hello'))
    await waitFor(() => expect(api.current).not.toBeNull())

    api.current?.insertDrawing(7)
    await waitFor(() => expect(emitted).toContain('ca-drawing://7'))
    const paragraphBefore = proseRoot().firstElementChild
    onChange.mockClear()

    rerender(
      <MarkdownEditor value={emitted} onChange={track} ariaLabel="Note body" apiRef={api} />
    )
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(proseRoot().firstElementChild).toBe(paragraphBefore)
    expect(onChange).not.toHaveBeenCalled()
  })

  test('drawing references round-trip through markdown', async () => {
    const onChange = vi.fn()
    render(
      <MarkdownEditor
        value={'before\n\n![drawing](ca-drawing://3)\n\nafter'}
        onChange={onChange}
        ariaLabel="Note body"
        drawings={[{ id: 3, png_sha: 'abc', ocr_markdown: '$2x$' }]}
      />
    )
    await waitFor(() =>
      expect(proseRoot().querySelector('img[src="/api/v1/blobs/abc"]')).not.toBeNull()
    )
  })

  test('inline drawing menu appears on click and triggers edit and reocr', async () => {
    const adapter = {
      create: vi.fn(async () => null),
      update: vi.fn(async () => undefined),
      reocr: vi.fn(async () => undefined),
      remove: vi.fn(async () => undefined),
    }
    render(
      <MarkdownEditor
        value={'text\n\n![drawing](ca-drawing://3)\n\nmore text'}
        onChange={vi.fn()}
        ariaLabel="Note body"
        drawings={[{ id: 3, png_sha: 'abc', ocr_markdown: '$2x$' }]}
        drawingAdapter={adapter}
      />
    )
    const image = await waitFor(() => {
      const node = proseRoot().querySelector('img[src="/api/v1/blobs/abc"]')
      expect(node).not.toBeNull()
      return node as HTMLElement
    })

    expect(screen.queryByRole('button', { name: 'Drawing options' })).toBeNull()
    const handle = image.closest('[data-drag-handle]') as HTMLElement
    expect(handle).not.toBeNull()

    clickElement(handle)
    const menuButton = await screen.findByRole('button', { name: 'Drawing options' })
    expect(handle.className).toContain('ring-2')

    fireEvent.click(menuButton)
    expect(await screen.findByRole('menu')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Run OCR again' }))
    await waitFor(() => expect(adapter.reocr).toHaveBeenCalledWith(3))

    fireEvent.click(screen.getByRole('button', { name: 'Drawing options' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Edit drawing' }))
    await screen.findByRole('dialog', { name: 'Handwriting canvas' })
  })

  test('inline drawing menu delete removes the node and calls the adapter', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    let emitted = ''
    const adapter = {
      create: vi.fn(async () => null),
      update: vi.fn(async () => undefined),
      reocr: vi.fn(async () => undefined),
      remove: vi.fn(async () => undefined),
    }
    render(
      <MarkdownEditor
        value={'text\n\n![drawing](ca-drawing://3)\n\nmore text'}
        onChange={(next) => {
          emitted = next
        }}
        ariaLabel="Note body"
        drawings={[{ id: 3, png_sha: 'abc', ocr_markdown: '$2x$' }]}
        drawingAdapter={adapter}
      />
    )
    const image = await waitFor(() => {
      const node = proseRoot().querySelector('img[src="/api/v1/blobs/abc"]')
      expect(node).not.toBeNull()
      return node as HTMLElement
    })

    clickElement(image.closest('[data-drag-handle]') as HTMLElement)
    fireEvent.click(await screen.findByRole('button', { name: 'Drawing options' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Delete drawing' }))
    await waitFor(() => expect(adapter.remove).toHaveBeenCalledWith(3))
    await waitFor(() =>
      expect(proseRoot().querySelector('img[src="/api/v1/blobs/abc"]')).toBeNull()
    )
    await waitFor(() => expect(emitted).not.toContain('ca-drawing://3'))
    confirm.mockRestore()
  })

  test('unreferenced drawing menu delete calls the adapter', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const adapter = {
      create: vi.fn(async () => null),
      update: vi.fn(async () => undefined),
      reocr: vi.fn(async () => undefined),
      remove: vi.fn(async () => undefined),
    }
    render(
      <MarkdownEditor
        value={'text\n\n![drawing](ca-drawing://4)\n\nafter'}
        onChange={vi.fn()}
        ariaLabel="Note body"
        drawings={[
          { id: 4, png_sha: 'abc', ocr_markdown: null, strokes: [] },
          { id: 7, png_sha: 'orphan', ocr_markdown: null, strokes: [] },
        ]}
        drawingAdapter={adapter}
      />
    )
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'More drawing actions' })
      ).toBeInTheDocument()
    )
    fireEvent.click(screen.getByRole('button', { name: 'More drawing actions' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Delete drawing' }))
    await waitFor(() => expect(adapter.remove).toHaveBeenCalledWith(7))
    confirm.mockRestore()
  })

  test('drawing delete asks for confirmation before removing', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const adapter = {
      create: vi.fn(async () => null),
      update: vi.fn(async () => undefined),
      reocr: vi.fn(async () => undefined),
      remove: vi.fn(async () => undefined),
    }
    render(
      <MarkdownEditor
        value={'text\n\n![drawing](ca-drawing://3)\n\nmore text'}
        onChange={vi.fn()}
        ariaLabel="Note body"
        drawings={[{ id: 3, png_sha: 'abc', ocr_markdown: null }]}
        drawingAdapter={adapter}
      />
    )
    const image = await waitFor(() => {
      const node = proseRoot().querySelector('img[src="/api/v1/blobs/abc"]')
      expect(node).not.toBeNull()
      return node as HTMLElement
    })
    clickElement(image.closest('[data-drag-handle]') as HTMLElement)
    fireEvent.click(await screen.findByRole('button', { name: 'Drawing options' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Delete drawing' }))
    await waitFor(() => expect(confirm).toHaveBeenCalled())
    expect(adapter.remove).not.toHaveBeenCalled()
    await waitFor(() =>
      expect(proseRoot().querySelector('img[src="/api/v1/blobs/abc"]')).not.toBeNull()
    )
    confirm.mockRestore()
  })

  test('clicking away deselects the drawing and hides its menu', async () => {
    render(
      <MarkdownEditor
        value={'text before\n\n![drawing](ca-drawing://3)\n\ntext after'}
        onChange={vi.fn()}
        ariaLabel="Note body"
        drawings={[{ id: 3, png_sha: 'abc', ocr_markdown: null }]}
      />
    )
    const image = await waitFor(() => {
      const node = proseRoot().querySelector('img[src="/api/v1/blobs/abc"]')
      expect(node).not.toBeNull()
      return node as HTMLElement
    })

    const handle = image.closest('[data-drag-handle]') as HTMLElement
    clickElement(handle)
    await screen.findByRole('button', { name: 'Drawing options' })

    const paragraph = Array.from(proseRoot().querySelectorAll('p')).find((p) =>
      p.textContent?.includes('text after')
    ) as HTMLElement
    placeCaret(paragraph)
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Drawing options' })).toBeNull()
    )
  })

  test('drawing node is marked draggable with a drag handle on the image', async () => {
    render(
      <MarkdownEditor
        value={'one\n\n![drawing](ca-drawing://3)\n\ntwo'}
        onChange={vi.fn()}
        ariaLabel="Note body"
        drawings={[{ id: 3, png_sha: 'abc', ocr_markdown: null }]}
      />
    )
    const image = await waitFor(() => {
      const node = proseRoot().querySelector('img[src="/api/v1/blobs/abc"]')
      expect(node).not.toBeNull()
      return node as HTMLElement
    })

    const handle = image.closest('[data-drag-handle]') as HTMLElement
    expect(handle).not.toBeNull()
    expect(handle.className).toContain('cursor-grab')
    expect(handle.closest('[draggable="true"]')).not.toBeNull()
    expect(image.getAttribute('draggable')).toBe('false')
  })

  test('inline drawing refreshes its OCR text when the drawing prop changes', async () => {
    const { rerender } = render(
      <MarkdownEditor
        value={'![drawing](ca-drawing://3)'}
        onChange={vi.fn()}
        ariaLabel="Note body"
        drawings={[{ id: 3, png_sha: 'abc', ocr_markdown: 'first text' }]}
      />
    )
    await waitFor(() => expect(proseRoot().textContent).toContain('first text'))

    rerender(
      <MarkdownEditor
        value={'![drawing](ca-drawing://3)'}
        onChange={vi.fn()}
        ariaLabel="Note body"
        drawings={[{ id: 3, png_sha: 'abc', ocr_markdown: 'second text' }]}
      />
    )
    await waitFor(() => expect(proseRoot().textContent).toContain('second text'))
    expect(proseRoot().textContent).not.toContain('first text')
  })

  test('insertDrawing api inserts a drawing image at the cursor', async () => {
    const onChange = vi.fn()
    const api: { current: MarkdownEditorApi | null } = { current: null }
    render(
      <MarkdownEditor value="hello" onChange={onChange} ariaLabel="Note body" apiRef={api} />
    )
    await waitFor(() => expect(proseRoot().textContent).toContain('hello'))
    await waitFor(() => expect(api.current).not.toBeNull())

    api.current?.insertDrawing(7)
    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith(
        expect.stringContaining('ca-drawing://7')
      )
    )
  })

  test('editor body scrolls under a pinned toolbar', async () => {
    render(<MarkdownEditor value="pinned" onChange={vi.fn()} ariaLabel="Note body" />)
    const root = await waitFor(() => {
      const node = proseRoot()
      expect(node.textContent).toContain('pinned')
      return node
    })
    const scrollArea = root.closest('[class*="overflow-y-auto"]')
    expect(scrollArea).not.toBeNull()
    expect(scrollArea!.className).toContain('overflow-y-auto')
    const toolbar = screen.getByRole('toolbar')
    expect(scrollArea!.contains(toolbar)).toBe(false)
  })

  test('undo and redo buttons revert and restore an insert', async () => {
    const api: { current: MarkdownEditorApi | null } = { current: null }
    function Harness() {
      const [value, setValue] = useState('hello')
      return (
        <MarkdownEditor
          value={value}
          onChange={setValue}
          ariaLabel="Note body"
          apiRef={api}
          drawings={[{ id: 7, png_sha: 'abc', ocr_markdown: null }]}
        />
      )
    }
    render(<Harness />)
    await waitFor(() => expect(proseRoot().textContent).toContain('hello'))
    await waitFor(() => expect(api.current).not.toBeNull())

    const undo = screen.getByRole('button', { name: 'Undo' })
    const redo = screen.getByRole('button', { name: 'Redo' })
    expect(undo).toBeDisabled()
    expect(redo).toBeDisabled()

    await act(async () => {
      api.current?.insertDrawing(7)
    })
    await waitFor(() => expect(proseRoot().querySelector('img')).not.toBeNull())

    fireEvent.click(undo)
    await waitFor(() => expect(proseRoot().querySelector('img')).toBeNull())
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Redo' })).not.toBeDisabled()
    )

    fireEvent.click(screen.getByRole('button', { name: 'Redo' }))
    await waitFor(() => expect(proseRoot().querySelector('img')).not.toBeNull())
  })

  test('insertQuote emits a markdown blockquote with a source link', async () => {
    const onChange = vi.fn()
    const api: { current: MarkdownEditorApi | null } = { current: null }
    render(
      <MarkdownEditor value="intro" onChange={onChange} ariaLabel="Note body" apiRef={api} />
    )
    await waitFor(() => expect(proseRoot().textContent).toContain('intro'))
    await waitFor(() => expect(api.current).not.toBeNull())

    api.current?.insertQuote('line one\nline two', {
      title: 'Worksheet',
      materialId: 5,
    })
    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith(
        expect.stringContaining('> line one')
      )
    )
    const markdown = onChange.mock.calls[0][0] as string
    expect(markdown).toContain('> line two')
    expect(markdown).toContain('[Worksheet](ca-material://5)')
  })

  test('extraction markdown round-trips byte-identically', async () => {
    const corpus = [
      '## Limits\n\n- definition\n- properties\n\n> quote line\n\nplain para',
      '| a | b |\n| --- | --- |\n| 1 | 2 |',
      '| h | k |\n| --- | --- |\n| **bold** | $x^2$ |',
      'inline $\\frac{1}{2}$ and $\\alpha$ values',
      '$$\\int_0^1 f(x)\\,dx = F(1) - F(0)$$',
      '$$\n\\begin{aligned}\na &= b \\\\\nc &= d\n\\end{aligned}\n$$',
      'see [@M1](mention:M1 "Lecture 1") and [Worksheet](ca-material://5)',
      '```mermaid\ngraph TD\n  A-->B\n```',
      'text with `code $x$ span` intact',
      'mixed | pipe | outside math stays',
    ]
    for (const markdown of corpus) {
      const onChange = vi.fn()
      const api: { current: MarkdownEditorApi | null } = { current: null }
      const anchored = `anchor\n\n${markdown}`
      const { unmount } = render(
        <MarkdownEditor value={anchored} onChange={onChange} ariaLabel="Note body" apiRef={api} />
      )
      await waitFor(() => expect(api.current).not.toBeNull())
      await act(async () => {
        api.current?.insertQuote('probe', null)
      })
      await waitFor(() => expect(onChange).toHaveBeenCalled())
      expect(onChange).toHaveBeenLastCalledWith(`> probe\n\n${anchored}`)
      unmount()
    }
  }, 20000)

  test('a saved ca-material link survives reopening the editor', async () => {
    let emitted = ''
    const api: { current: MarkdownEditorApi | null } = { current: null }
    const { rerender } = render(
      <MarkdownEditor
        value={'quote from [Worksheet](ca-material://5) here'}
        onChange={(next) => {
          emitted = next
        }}
        ariaLabel="Note body"
        apiRef={api}
      />
    )
    await waitFor(() => expect(api.current).not.toBeNull())
    await act(async () => {
      api.current?.insertQuote('probe', null)
    })
    await waitFor(() => expect(emitted).toContain('ca-material://5'))
    expect(emitted).toBe('> probe\n\nquote from [Worksheet](ca-material://5) here')
    rerender(
      <MarkdownEditor
        value={emitted}
        onChange={(next) => {
          emitted = next
        }}
        ariaLabel="Note body"
        apiRef={api}
      />
    )
    await act(async () => {
      api.current?.insertQuote('again', null)
    })
    await waitFor(() => expect(emitted).toContain('> again'))
    expect(emitted).toContain('[Worksheet](ca-material://5)')
  })

  test('inline math renders with KaTeX instead of raw latex source', async () => {
    render(
      <MarkdownEditor
        value={'the map $f(x,y)=e^{x/y}$ is continuous'}
        onChange={vi.fn()}
        ariaLabel="Note body"
      />
    )
    await waitFor(() =>
      expect(document.querySelector('.ca-math .katex')).not.toBeNull()
    )
    expect(proseRoot().textContent).not.toContain('$f(x,y)')
  })

  test('display math renders in display mode', async () => {
    render(
      <MarkdownEditor
        value={'$$\\int_0^1 f(x)\\,dx$$'}
        onChange={vi.fn()}
        ariaLabel="Note body"
      />
    )
    await waitFor(() =>
      expect(document.querySelector('.ca-math .katex-display')).not.toBeNull()
    )
  })

  test('double-click opens the equation editor and updates the math node', async () => {
    let emitted = ''
    render(
      <MarkdownEditor
        value={'anchor $f(x,y)=e^{x/y}$ tail'}
        onChange={(next) => {
          emitted = next
        }}
        ariaLabel="Note body"
      />
    )
    const mathChip = await waitFor(() => {
      const node = document.querySelector('[data-ca-math-view]') as HTMLElement
      expect(node).not.toBeNull()
      return node
    })

    fireEvent.doubleClick(mathChip)
    const field = await waitFor(() => {
      const element = document.querySelector('math-field')
      expect(element).not.toBeNull()
      return element as HTMLElement & { value: string }
    })

    field.value = 'g(x)'
    field.dispatchEvent(new Event('input', { bubbles: true }))
    await waitFor(() => expect(emitted).toContain('$g(x)$'))
    expect(emitted).not.toContain('e^{')

    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    await waitFor(() =>
      expect(document.querySelector('math-field')).toBeNull()
    )
    expect(emitted).toBe('anchor $g(x)$ tail')
  })

  test('math inside table cells keeps the cell content through a round-trip', async () => {
    let emitted = ''
    const api: { current: MarkdownEditorApi | null } = { current: null }
    const anchored = 'anchor\n\n| h | k |\n| --- | --- |\n| $x^2$ | plain |'
    render(
      <MarkdownEditor
        value={anchored}
        onChange={(next) => {
          emitted = next
        }}
        ariaLabel="Note body"
        apiRef={api}
      />
    )
    await waitFor(() =>
      expect(document.querySelector('.ca-math .katex')).not.toBeNull()
    )
    await waitFor(() => expect(api.current).not.toBeNull())
    await act(async () => {
      api.current?.insertQuote('probe', null)
    })
    await waitFor(() => expect(emitted).toContain('probe'))
    expect(emitted).toBe(`> probe\n\n${anchored}`)
  })

  test('escaped pipes inside math in table cells canonicalize to plain pipes', async () => {
    let emitted = ''
    const api: { current: MarkdownEditorApi | null } = { current: null }
    render(
      <MarkdownEditor
        value={'anchor\n\n| m |\n| --- |\n| $a\\|b$ |'}
        onChange={(next) => {
          emitted = next
        }}
        ariaLabel="Note body"
        apiRef={api}
      />
    )
    await waitFor(() => expect(api.current).not.toBeNull())
    await act(async () => {
      api.current?.insertQuote('probe', null)
    })
    await waitFor(() => expect(emitted).toContain('probe'))
    expect(emitted).toBe('> probe\n\nanchor\n\n| m |\n| --- |\n| $a|b$ |')
  })

  test('mermaid fences render as diagrams and round-trip through the node', async () => {
    let emitted = ''
    const api: { current: MarkdownEditorApi | null } = { current: null }
    const anchored = 'anchor\n\n```mermaid\ngraph TD\n  A-->B\n```'
    render(
      <MarkdownEditor
        value={anchored}
        onChange={(next) => {
          emitted = next
        }}
        ariaLabel="Note body"
        apiRef={api}
      />
    )
    expect(await screen.findByTestId('mermaid-svg')).toBeInTheDocument()
    await waitFor(() => expect(api.current).not.toBeNull())
    await act(async () => {
      api.current?.insertQuote('probe', null)
    })
    await waitFor(() => expect(emitted).toContain('probe'))
    expect(emitted).toBe(`> probe\n\n${anchored}`)
  })

  test('double-click a diagram opens the source editor with a close button', async () => {
    let emitted = ''
    render(
      <MarkdownEditor
        value={'anchor\n\n```mermaid\ngraph TD\n  A-->B\n```'}
        onChange={(next) => {
          emitted = next
        }}
        ariaLabel="Note body"
      />
    )
    const chip = await waitFor(() => {
      const node = document.querySelector('[data-ca-mermaid-view]') as HTMLElement
      expect(node).not.toBeNull()
      return node
    })

    fireEvent.doubleClick(chip)
    await screen.findByRole('dialog', { name: 'Edit diagram' })
    const source = screen.getByLabelText('Diagram source') as HTMLTextAreaElement
    expect(source.value).toBe('graph TD\n  A-->B')

    fireEvent.change(source, { target: { value: 'graph TD\n  A-->C' } })
    await waitFor(() => expect(emitted).toContain('A-->C'))

    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'Edit diagram' })).toBeNull()
    )
    expect(emitted).toBe('anchor\n\n```mermaid\ngraph TD\n  A-->C\n```')
  })

  test('the equation editor popover has a working close button', async () => {
    render(
      <MarkdownEditor
        value={'anchor $x^2$ tail'}
        onChange={vi.fn()}
        ariaLabel="Note body"
      />
    )
    const mathChip = await waitFor(() => {
      const node = document.querySelector('[data-ca-math-view]') as HTMLElement
      expect(node).not.toBeNull()
      return node
    })

    fireEvent.doubleClick(mathChip)
    await waitFor(() =>
      expect(screen.getByRole('dialog', { name: 'Edit equation' })).toBeInTheDocument()
    )
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'Edit equation' })).toBeNull()
    )
  })

  test('toolbar math button inserts an equation and opens the editor', async () => {
    let emitted = ''
    render(
      <MarkdownEditor
        value="hello"
        onChange={(next) => {
          emitted = next
        }}
        ariaLabel="Note body"
      />
    )
    await waitFor(() => expect(proseRoot().textContent).toContain('hello'))

    fireEvent.click(screen.getByRole('button', { name: 'Insert math equation' }))
    await waitFor(() =>
      expect(screen.getByRole('dialog', { name: 'Edit equation' })).toBeInTheDocument()
    )
    expect(document.querySelector('[data-ca-math-view]')).not.toBeNull()

    const field = document.querySelector('math-field') as HTMLElement & {
      value: string
    }
    field.value = 'a^2'
    field.dispatchEvent(new Event('input', { bubbles: true }))
    await waitFor(() => expect(emitted).toContain('$a^2$'))

    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'Edit equation' })).toBeNull()
    )
  })

  test('toolbar diagram button inserts a mermaid skeleton and opens the source editor', async () => {
    let emitted = ''
    render(
      <MarkdownEditor
        value="hello"
        onChange={(next) => {
          emitted = next
        }}
        ariaLabel="Note body"
      />
    )
    await waitFor(() => expect(proseRoot().textContent).toContain('hello'))

    fireEvent.click(screen.getByRole('button', { name: 'Insert diagram' }))
    const source = (await screen.findByLabelText(
      'Diagram source'
    )) as HTMLTextAreaElement
    expect(source.value).toBe('flowchart TD\n  A --> B')
    expect(await screen.findByTestId('mermaid-svg')).toBeInTheDocument()

    fireEvent.change(source, { target: { value: 'flowchart TD\n  X-->Y' } })
    await waitFor(() => expect(emitted).toContain('X-->Y'))
    expect(emitted).toContain('```mermaid')

    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'Edit diagram' })).toBeNull()
    )
  })

  test('pen button opens the canvas; saving calls create and inserts the ref', async () => {
    let emitted = ''
    const adapter = {
      create: vi.fn(async () => 11),
      update: vi.fn(async () => undefined),
      reocr: vi.fn(async () => undefined),
      remove: vi.fn(async () => undefined),
    }
    render(
      <MarkdownEditor
        value="plain"
        onChange={(next) => {
          emitted = next
        }}
        ariaLabel="Note body"
        drawings={[]}
        drawingAdapter={adapter}
      />
    )
    await waitFor(() => expect(proseRoot().textContent).toContain('plain'))

    fireEvent.click(screen.getByRole('button', { name: 'Insert drawing' }))
    await screen.findByRole('dialog', { name: 'Handwriting canvas' })
    expect(screen.getByRole('button', { name: 'Save drawing' })).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: 'stub-stroke' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save drawing' }))
    await waitFor(() =>
      expect(adapter.create).toHaveBeenCalledWith(
        [{ points: [[0, 0]], color: '#1a1a1a', width: 2 }],
        'AAA',
        true,
        { x: -4, y: -4, width: 8, height: 8 }
      )
    )
    await waitFor(() => expect(emitted).toContain('ca-drawing://11'))
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'Handwriting canvas' })).toBeNull()
    )
  })

  test('turning the OCR toggle off saves the drawing without extraction', async () => {
    const adapter = {
      create: vi.fn(async () => 12),
      update: vi.fn(async () => undefined),
      reocr: vi.fn(async () => undefined),
      remove: vi.fn(async () => undefined),
    }
    render(
      <MarkdownEditor
        value="plain"
        onChange={vi.fn()}
        ariaLabel="Note body"
        drawingAdapter={adapter}
      />
    )
    await waitFor(() => expect(proseRoot().textContent).toContain('plain'))

    fireEvent.click(screen.getByRole('button', { name: 'Insert drawing' }))
    await screen.findByRole('dialog', { name: 'Handwriting canvas' })
    fireEvent.click(screen.getByRole('button', { name: 'stub-stroke' }))
    fireEvent.click(screen.getByRole('checkbox', { name: /run OCR/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Save drawing' }))
    await waitFor(() =>
      expect(adapter.create).toHaveBeenCalledWith(expect.anything(), 'AAA', false, expect.anything())
    )
  })

  test('edit drawing loads its strokes and PUTs via the adapter', async () => {
    const adapter = {
      create: vi.fn(async () => null),
      update: vi.fn(async () => undefined),
      reocr: vi.fn(async () => undefined),
      remove: vi.fn(async () => undefined),
    }
    render(
      <MarkdownEditor
        value={'plain\n\n![drawing](ca-drawing://3)\n\nmore text'}
        onChange={vi.fn()}
        ariaLabel="Note body"
        drawings={[
          {
            id: 3,
            png_sha: 'abc',
            ocr_markdown: 'old',
            strokes: [{ points: [[1, 1]], color: '#1a1a1a', width: 2 }],
          },
        ]}
        drawingAdapter={adapter}
      />
    )
    const image = await waitFor(() => {
      const node = proseRoot().querySelector('img[src="/api/v1/blobs/abc"]')
      expect(node).not.toBeNull()
      return node as HTMLElement
    })

    clickElement(image.closest('[data-drag-handle]') as HTMLElement)
    fireEvent.click(await screen.findByRole('button', { name: 'Drawing options' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Edit drawing' }))
    expect(await screen.findByText(/editing an existing drawing/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'stub-stroke' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save drawing' }))
    await waitFor(() =>
      expect(adapter.update).toHaveBeenCalledWith(
        3,
        [{ points: [[0, 0]], color: '#1a1a1a', width: 2 }],
        'AAA',
        true,
        { x: -4, y: -4, width: 8, height: 8 }
      )
    )
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'Handwriting canvas' })).toBeNull()
    )
  })

  test('editing a drawing restores its saved view as the canvas focus', async () => {
    const adapter = {
      create: vi.fn(async () => null),
      update: vi.fn(async () => undefined),
      reocr: vi.fn(async () => undefined),
      remove: vi.fn(async () => undefined),
    }
    render(
      <MarkdownEditor
        value={'text\n\n![drawing](ca-drawing://3)\n\nmore text'}
        onChange={vi.fn()}
        ariaLabel="Note body"
        drawings={[
          {
            id: 3,
            png_sha: 'abc',
            ocr_markdown: null,
            strokes: [{ points: [[1, 1]], color: '#1a1a1a', width: 2 }],
            view: { x: 10, y: 20, width: 300, height: 200 },
          },
        ]}
        drawingAdapter={adapter}
      />
    )
    const image = await waitFor(() => {
      const node = proseRoot().querySelector('img[src="/api/v1/blobs/abc"]')
      expect(node).not.toBeNull()
      return node as HTMLElement
    })
    clickElement(image.closest('[data-drag-handle]') as HTMLElement)
    fireEvent.click(await screen.findByRole('button', { name: 'Drawing options' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Edit drawing' }))
    await screen.findByRole('dialog', { name: 'Handwriting canvas' })
    expect(screen.getByTestId('canvas-focus').dataset.focus).toBe(
      JSON.stringify({ x: 10, y: 20, width: 300, height: 200 })
    )
  })

  test('unreferenced drawings render a card and insert-inline adds the ref', async () => {
    let emitted = ''
    render(
      <MarkdownEditor
        value={'before\n\n![drawing](ca-drawing://4)\n\nafter'}
        onChange={(next) => {
          emitted = next
        }}
        ariaLabel="Note body"
        drawings={[
          { id: 4, png_sha: 'abc123', ocr_markdown: '$2x$', strokes: [] },
          { id: 7, png_sha: 'orphan', ocr_markdown: null, strokes: [] },
        ]}
      />
    )
    await waitFor(() => expect(proseRoot().textContent).toContain('after'))

    expect(screen.getByText('No OCR text yet')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Insert inline' })).toBeInTheDocument()
    expect(screen.getAllByRole('img', { name: /handwritten/i })).toHaveLength(2)

    fireEvent.click(screen.getByRole('button', { name: 'Insert inline' }))
    await waitFor(() => expect(emitted).toContain('ca-drawing://7'))
  })
})
