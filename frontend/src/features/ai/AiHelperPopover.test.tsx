import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import type { Editor } from '@tiptap/react'

import { AiHelperPopover, type AiHelperContext } from './AiHelperPopover'
import type { CapturedSelection } from '@/components/editor/selectionCapture'

const insertMarkdown = vi.fn()
const textBetween = vi.fn()

vi.mock('@/components/editor/insertMarkdown', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('@/components/editor/insertMarkdown')
  >()
  return {
    ...actual,
    insertMarkdown: (...args: unknown[]) =>
      insertMarkdown(...(args as [Editor, string, string, unknown])),
    textBetween: (...args: unknown[]) => textBetween(...(args as [Editor, number, number])),
  }
})

const captureSelectionMock = vi.fn<() => CapturedSelection | null>(() => null)

vi.mock('@/components/editor/selectionCapture', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('@/components/editor/selectionCapture')
  >()
  return {
    ...actual,
    captureSelection: () => captureSelectionMock(),
  }
})

vi.mock('mermaid', () => ({
  default: {
    parse: vi.fn(async (code: string) => {
      if (code.includes('BAD')) {
        throw new Error('Parse error on line 2')
      }
      return { diagramType: {} }
    }),
  },
}))

function stubResizeObserver(inlineSize: number): void {
  class Stub implements ResizeObserver {
    private readonly callback: ResizeObserverCallback
    constructor(callback: ResizeObserverCallback) {
      this.callback = callback
    }
    observe(target: Element): void {
      const box = { inlineSize, blockSize: 600 } as ResizeObserverSize
      const entry = { target, borderBoxSize: [box] } as unknown as ResizeObserverEntry
      this.callback([entry], this as unknown as ResizeObserver)
    }
    unobserve(): void {}
    disconnect(): void {}
  }
  vi.stubGlobal('ResizeObserver', Stub)
}

const startEditorTransform = vi.fn()
const getEditorTransformJob = vi.fn()
const cancelEditorTransformJob = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    startEditorTransform: (...args: unknown[]) =>
      startEditorTransform(...(args as [Parameters<typeof import('@/lib/api').startEditorTransform>[0]])),
    getEditorTransformJob: (...args: unknown[]) =>
      getEditorTransformJob(...(args as [number])),
    cancelEditorTransformJob: (...args: unknown[]) =>
      cancelEditorTransformJob(...(args as [number])),
  }
})

let transformHandler: ((payload: unknown) => void) | null = null

vi.mock('@/lib/ws-client', () => ({
  getWsClient: () => ({
    subscribe: vi.fn((topic: string, handler: (payload: unknown) => void) => {
      if (topic.startsWith('ai-editor:')) {
        transformHandler = handler
      }
      return () => {
        if (transformHandler === handler) {
          transformHandler = null
        }
      }
    }),
  }),
}))

const fakeEditor = { getText: () => 'hello world' } as unknown as Editor
const context: AiHelperContext = { courseId: 1, nodeId: 2, title: 'Note' }

function textCapture(from = 1, to = 12, markdown = 'hello world'): CapturedSelection {
  return {
    from,
    to,
    markdown,
    summary: {
      diagrams: 0,
      formulas: 0,
      codeBlocks: 0,
      tables: 0,
      imagesDrawings: 0,
      textBlocks: 1,
      lines: 1,
      preview: markdown,
    },
  }
}

function blockCapture(
  markdown: string,
  summary: Partial<CapturedSelection['summary']>
): CapturedSelection {
  return {
    from: 1,
    to: 40,
    markdown,
    summary: {
      diagrams: 0,
      formulas: 0,
      codeBlocks: 0,
      tables: 0,
      imagesDrawings: 0,
      textBlocks: 0,
      lines: markdown.split('\n').length,
      preview: markdown,
      ...summary,
    },
  }
}

function renderPopover(
  selection: { from: number; to: number } | null,
  capture: CapturedSelection | null = null
) {
  const onInsert = vi.fn()
  captureSelectionMock.mockReturnValue(
    capture ??
      (selection === null ? null : textCapture(selection.from, selection.to))
  )
  render(
    <AiHelperPopover
      editor={fakeEditor}
      context={context}
      selectionRef={{ current: selection }}
      closeSignal={0}
      onInsert={onInsert}
    />
  )
  return { onInsert }
}

function openHelper() {
  fireEvent.click(screen.getByRole('button', { name: 'AI helper' }))
  return screen.getByRole('dialog', { name: 'AI helper' })
}

function emitDelta(text: string) {
  act(() => {
    transformHandler?.({ type: 'editor_delta', text })
  })
}

function emitDone(result: string) {
  act(() => {
    transformHandler?.({ type: 'editor_done', result_md: result })
  })
}

beforeEach(() => {
  textBetween.mockReturnValue('hello world')
  startEditorTransform.mockReset()
  getEditorTransformJob.mockReset()
  cancelEditorTransformJob.mockReset()
  insertMarkdown.mockClear()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function mockRunningJob() {
  startEditorTransform.mockResolvedValue({ job_id: 7 })
  getEditorTransformJob.mockResolvedValue({
    status: 'running',
    result_md: '',
    error: null,
    problems: [],
    rounds: 0,
  })
}

describe('AiHelperPopover', () => {
  test('opens, shows the free-form prompt and keeps presets enabled without a selection', () => {
    renderPopover(null)
    const dialog = openHelper()
    expect(dialog).not.toBeNull()
    expect(screen.getByPlaceholderText(/Ask the AI/)).not.toBeNull()
    expect(screen.getByText('Context')).not.toBeNull()
    expect(screen.getByText('Course material')).not.toBeNull()
    expect(screen.getByRole('button', { name: 'Explain' })).not.toBeDisabled()
    expect(screen.getByText('Transform whole note')).not.toBeNull()
    expect(screen.getByText('Whole note')).not.toBeNull()
    expect(screen.queryByTestId('selection-summary-chip')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Try to fix' })).toBeNull()
    expect(dialog.querySelector('[data-popover-drag-handle]')).not.toBeNull()
    expect(dialog.querySelectorAll('[data-resize-dir]').length).toBe(8)
  })

  test('presets stay disabled when the note is empty and nothing is selected', () => {
    const emptyEditor = { getText: () => '' } as unknown as Editor
    render(
      <AiHelperPopover
        editor={emptyEditor}
        context={context}
        selectionRef={{ current: null }}
        closeSignal={0}
        onInsert={vi.fn()}
      />
    )
    openHelper()
    expect(screen.getByRole('button', { name: 'Explain' })).toBeDisabled()
  })

  test('a selection set after mount is picked up when the popover opens', () => {
    const selectionRef = { current: null as { from: number; to: number } | null }
    render(
      <AiHelperPopover
        editor={fakeEditor}
        context={context}
        selectionRef={selectionRef}
        closeSignal={0}
        onInsert={vi.fn()}
      />
    )
    captureSelectionMock.mockReturnValue(textCapture(1, 12))
    openHelper()
    expect(screen.getByRole('button', { name: 'Explain' })).not.toBeDisabled()
    expect(screen.getByText('Context')).not.toBeNull()
  })

  test('a text selection shows the summary chip and scope label', () => {
    renderPopover({ from: 1, to: 12 })
    openHelper()
    const chip = screen.getByTestId('selection-summary-chip')
    expect(within(chip).getByRole('button', { name: /1 paragraph/ })).not.toBeNull()
    expect(screen.getByText('Selection — 1 paragraph')).not.toBeNull()
  })

  test('a diagram selection upgrades the scope chip and pins a Try to fix entry', () => {
    renderPopover(
      { from: 1, to: 40 },
      blockCapture('```mermaid\nflowchart TD\n  A --> B\n```', { diagrams: 1 })
    )
    openHelper()
    expect(screen.getByText('Selection — 1 diagram')).not.toBeNull()
    expect(screen.getByTestId('selection-summary-chip').textContent).toContain(
      '1 diagram'
    )
    expect(screen.getByRole('button', { name: 'Try to fix' })).not.toBeNull()
  })

  test('a mixed selection lists every kind and the chip expands into a preview disclosure', () => {
    renderPopover(
      { from: 1, to: 40 },
      blockCapture('mixed markdown', { diagrams: 1, formulas: 1, textBlocks: 2 })
    )
    openHelper()
    expect(screen.getByText('Selection — mixed (4 blocks)')).not.toBeNull()
    const chip = screen.getByTestId('selection-summary-chip')
    expect(chip.textContent).toContain('1 diagram · 1 formula · 2 paragraphs')
    const toggle = within(chip).getByRole('button', { name: /1 diagram/ })
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    const previewId = toggle.getAttribute('aria-controls')
    expect(document.getElementById(previewId ?? '')).toBeNull()
    fireEvent.click(toggle)
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
    const preview = document.getElementById(previewId ?? '')
    expect(preview?.textContent).toContain('mixed markdown')
    expect(preview?.textContent).toContain('1 line')
  })

  test('a preset transform streams into review and inserts at the cursor', async () => {
    mockRunningJob()
    renderPopover({ from: 1, to: 12 })
    openHelper()
    fireEvent.click(screen.getByText('Course material'))
    fireEvent.click(screen.getByRole('button', { name: 'Explain' }))
    await waitFor(() =>
      expect(startEditorTransform).toHaveBeenCalledWith(
        expect.objectContaining({
          text: 'hello world',
          preset: 'explain',
          mode: 'transform',
          course_id: 1,
          node_id: 2,
          ground_in_material: true,
        })
      )
    )
    emitDelta('The limit')
    emitDelta(' definition.')
    emitDone('The limit definition.')
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Insert at cursor' })).not.toBeNull()
    )
    fireEvent.click(screen.getByRole('button', { name: 'Insert at cursor' }))
    await waitFor(() =>
      expect(insertMarkdown).toHaveBeenCalledWith(
        fakeEditor,
        'The limit definition.',
        'at-cursor',
        null
      )
    )
  })

  test('the review view defaults to a diff and switches between formatted and raw', async () => {
    mockRunningJob()
    renderPopover({ from: 1, to: 12 })
    openHelper()
    fireEvent.click(screen.getByRole('button', { name: 'Explain' }))
    await waitFor(() => expect(startEditorTransform).toHaveBeenCalled())
    emitDone('## Heading\n\n**bold** and $x^2$')
    await waitFor(() =>
      expect(document.querySelector('[data-as="text-diff-view"]')).not.toBeNull()
    )
    const diffView = document.querySelector('[data-as="text-diff-view"]') as HTMLElement
    expect(diffView.textContent).toContain('hello world')
    expect(screen.getByRole('tab', { name: 'Diff' }).getAttribute('aria-selected')).toBe(
      'true'
    )
    fireEvent.click(screen.getByRole('tab', { name: 'Formatted' }))
    expect(screen.getByRole('heading', { name: 'Heading' })).not.toBeNull()
    expect(screen.getByText('Original')).not.toBeNull()
    fireEvent.click(screen.getByRole('tab', { name: 'Raw' }))
    expect(screen.getByLabelText('AI result')).toHaveValue('## Heading\n\n**bold** and $x^2$')
  })

  test('the source pane is hidden on narrow panels', async () => {
    stubResizeObserver(400)
    mockRunningJob()
    renderPopover({ from: 1, to: 12 })
    openHelper()
    fireEvent.click(screen.getByRole('button', { name: 'Explain' }))
    await waitFor(() => expect(startEditorTransform).toHaveBeenCalled())
    emitDone('new text')
    await waitFor(() => expect(screen.getByRole('tab', { name: 'Diff' })).not.toBeNull())
    fireEvent.click(screen.getByRole('tab', { name: 'Formatted' }))
    expect(screen.queryByText('Original')).toBeNull()
  })

  test('free-form write runs default to the formatted view without a source pane', async () => {
    mockRunningJob()
    renderPopover(null)
    openHelper()
    fireEvent.change(screen.getByLabelText('Prompt'), {
      target: { value: 'write a summary' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Run' }))
    await waitFor(() =>
      expect(startEditorTransform).toHaveBeenCalledWith(
        expect.objectContaining({ mode: 'write' })
      )
    )
    emitDone('written text')
    await waitFor(() =>
      expect(screen.getByRole('tab', { name: 'Formatted' }).getAttribute('aria-selected')).toBe(
        'true'
      )
    )
    expect(screen.queryByText('Original')).toBeNull()
    expect(screen.queryByText('Replace note')).toBeNull()
  })

  test('a free-form ask over a block selection transforms the captured markdown', async () => {
    mockRunningJob()
    renderPopover(
      { from: 1, to: 40 },
      blockCapture('```mermaid\nflowchart TD\n  A --> B\n```', {
        diagrams: 1,
        textBlocks: 2,
      })
    )
    openHelper()
    fireEvent.change(screen.getByLabelText('Prompt'), {
      target: { value: 'explain this selection' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Run' }))
    await waitFor(() =>
      expect(startEditorTransform).toHaveBeenCalledWith(
        expect.objectContaining({
          text: '```mermaid\nflowchart TD\n  A --> B\n```',
          mode: 'transform',
        })
      )
    )
  })

  test('replace-selection passes the captured range to insertMarkdown', async () => {
    mockRunningJob()
    renderPopover({ from: 3, to: 9 })
    openHelper()
    fireEvent.click(screen.getByRole('button', { name: 'Make more compact' }))
    await waitFor(() => expect(startEditorTransform).toHaveBeenCalled())
    emitDone('compact result')
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Replace selection' })).not.toBeDisabled()
    )
    fireEvent.click(screen.getByRole('button', { name: 'Replace selection' }))
    await waitFor(() =>
      expect(insertMarkdown).toHaveBeenCalledWith(
        fakeEditor,
        'compact result',
        'replace-selection',
        { from: 3, to: 9 }
      )
    )
  })

  test('an error event surfaces inline', async () => {
    mockRunningJob()
    renderPopover({ from: 1, to: 12 })
    openHelper()
    fireEvent.click(screen.getByRole('button', { name: 'Make more compact' }))
    await waitFor(() =>
      expect(startEditorTransform).toHaveBeenCalledWith(
        expect.objectContaining({ preset: 'compact' })
      )
    )
    act(() => {
      transformHandler?.({ type: 'editor_error', message: 'model exploded' })
    })
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('model exploded'))
  })

  test('stop cancels the job and returns to idle', async () => {
    mockRunningJob()
    cancelEditorTransformJob.mockResolvedValue(undefined)
    renderPopover({ from: 1, to: 12 })
    openHelper()
    fireEvent.click(screen.getByRole('button', { name: 'Answer the question' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Stop' })).not.toBeNull())
    fireEvent.click(screen.getByRole('button', { name: 'Stop' }))
    await waitFor(() => expect(cancelEditorTransformJob).toHaveBeenCalledWith(7))
    await waitFor(() =>
      expect(screen.getByPlaceholderText(/Ask the AI/)).not.toBeNull()
    )
  })

  test('without a selection, presets transform the whole note and can replace it', async () => {
    mockRunningJob()
    renderPopover(null)
    openHelper()
    fireEvent.click(screen.getByRole('button', { name: 'Explain' }))
    await waitFor(() =>
      expect(startEditorTransform).toHaveBeenCalledWith(
        expect.objectContaining({
          text: 'hello world',
          preset: 'explain',
          mode: 'transform',
          include_context: false,
        })
      )
    )
    emitDone('whole note result')
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Replace note' })).not.toBeNull()
    )
    fireEvent.click(screen.getByRole('button', { name: 'Replace note' }))
    await waitFor(() =>
      expect(insertMarkdown).toHaveBeenCalledWith(
        fakeEditor,
        'whole note result',
        'replace-document',
        null
      )
    )
  })

  test('a running transform renders the flow status card with cancel', async () => {
    mockRunningJob()
    renderPopover({ from: 1, to: 12 })
    openHelper()
    fireEvent.click(screen.getByRole('button', { name: 'Explain' }))
    await waitFor(() =>
      expect(document.body.querySelector('[data-status="running"]')).not.toBeNull()
    )
    const card = document.body.querySelector('[data-status="running"]') as HTMLElement
    expect(within(card).getAllByText('Transform').length).toBeGreaterThan(0)
    expect(within(card).getAllByText('Review').length).toBeGreaterThan(0)
    expect(within(card).getByText('1/2')).not.toBeNull()
    expect(within(card).getByRole('button', { name: 'Stop' })).not.toBeNull()
  })

  test('a failed transform renders the flow status card with retry', async () => {
    mockRunningJob()
    renderPopover({ from: 1, to: 12 })
    openHelper()
    fireEvent.click(screen.getByRole('button', { name: 'Explain' }))
    await waitFor(() => expect(startEditorTransform).toHaveBeenCalled())
    act(() => {
      transformHandler?.({ type: 'editor_error', message: 'model exploded' })
    })
    await waitFor(() =>
      expect(document.body.querySelector('[data-status="failed"]')).not.toBeNull()
    )
    expect(screen.getByRole('button', { name: 'Retry' })).not.toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(startEditorTransform).toHaveBeenCalledTimes(2))
  })

  test('Try to fix repairs a broken diagram deterministically and applies through the gate', async () => {
    renderPopover(
      { from: 1, to: 40 },
      blockCapture('```mermaid\nflowchart TD\n  A((v: (a,b)))\n```', { diagrams: 1 })
    )
    openHelper()
    fireEvent.click(screen.getByRole('button', { name: 'Try to fix' }))
    expect(await screen.findByText('Fixed without AI')).toBeInTheDocument()
    expect(startEditorTransform).not.toHaveBeenCalled()
    await waitFor(() =>
      expect(screen.getByText('Renders cleanly')).toBeInTheDocument()
    )
    const apply = screen.getByRole('button', { name: 'Replace selection' })
    expect(apply).not.toBeDisabled()
    fireEvent.click(apply)
    await waitFor(() =>
      expect(insertMarkdown).toHaveBeenCalledWith(
        fakeEditor,
        expect.stringContaining('A(("v: (a,b)"))'),
        'replace-selection',
        { from: 1, to: 40 }
      )
    )
  })

  test('a failed AI fix is gated: Apply is disabled and the error shows', async () => {
    mockRunningJob()
    renderPopover(
      { from: 1, to: 40 },
      blockCapture('```mermaid\nBAD line\n```', { diagrams: 1 })
    )
    openHelper()
    fireEvent.click(screen.getByRole('button', { name: 'Try to fix' }))
    await waitFor(() =>
      expect(startEditorTransform).toHaveBeenCalledWith(
        expect.objectContaining({
          preset: 'fix_mermaid',
          text: 'BAD line',
          diagnostic: 'Parse error on line 2',
        })
      )
    )
    emitDone('```mermaid\nBAD line\n```')
    await screen.findByText('Renderer still rejects it')
    expect(screen.getByText(/Parse error on line 2/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Replace selection' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Insert as markdown anyway' })).not.toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Insert as markdown anyway' }))
    await waitFor(() =>
      expect(insertMarkdown).toHaveBeenCalledWith(
        fakeEditor,
        '```mermaid\nBAD line\n```',
        'replace-selection',
        { from: 1, to: 40 }
      )
    )
  })

  test('a passing fix streams through the same review diff with the gate ok', async () => {
    mockRunningJob()
    renderPopover(
      { from: 1, to: 40 },
      blockCapture('```mermaid\nBAD line\n```', { diagrams: 1 })
    )
    openHelper()
    fireEvent.click(screen.getByRole('button', { name: 'Try to fix' }))
    await waitFor(() => expect(startEditorTransform).toHaveBeenCalled())
    emitDone('```mermaid\nflowchart TD\n  A --> B\n```')
    await screen.findByText('Renders cleanly')
    expect(
      screen.getByRole('button', { name: 'Replace selection' })
    ).not.toBeDisabled()
    const diff = document.querySelector('[data-as="text-diff-view"]') as HTMLElement
    expect(diff.textContent).toContain('BAD line')
    expect(diff.textContent).toContain('flowchart TD')
  })

  test('a cross-kind rewrite of a diagram applies as markdown without gating', async () => {
    mockRunningJob()
    renderPopover(
      { from: 1, to: 40 },
      blockCapture('```mermaid\nflowchart TD\n  A --> B\n```', { diagrams: 1 })
    )
    openHelper()
    fireEvent.click(screen.getByRole('button', { name: 'Explain' }))
    await waitFor(() => expect(startEditorTransform).toHaveBeenCalled())
    emitDone('This flowchart moves data from A to B.')
    await screen.findByText('Applies as markdown')
    const apply = screen.getByRole('button', { name: 'Replace selection' })
    expect(apply).not.toBeDisabled()
    fireEvent.click(apply)
    await waitFor(() =>
      expect(insertMarkdown).toHaveBeenCalledWith(
        fakeEditor,
        'This flowchart moves data from A to B.',
        'replace-selection',
        { from: 1, to: 40 }
      )
    )
  })

  test('a same-kind math result passes the gate and applies as a node', async () => {
    mockRunningJob()
    renderPopover(
      { from: 1, to: 40 },
      blockCapture('$\\frac{1}{2}$', { formulas: 1 })
    )
    openHelper()
    fireEvent.click(screen.getByRole('button', { name: 'Explain' }))
    await waitFor(() => expect(startEditorTransform).toHaveBeenCalled())
    emitDone('$\\frac{1}{3}$')
    await screen.findByText('Renders cleanly')
    expect(screen.queryByText('Applies as markdown')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Replace selection' }))
    await waitFor(() =>
      expect(insertMarkdown).toHaveBeenCalledWith(
        fakeEditor,
        '$\\frac{1}{3}$',
        'replace-selection',
        { from: 1, to: 40 }
      )
    )
  })

  test('a mixed selection fix routes the whole slice through the fix preset without gating', async () => {
    mockRunningJob()
    renderPopover(
      { from: 1, to: 60 },
      blockCapture('```mermaid\nBAD line\n```\n\nnote text', {
        diagrams: 1,
        textBlocks: 1,
      })
    )
    openHelper()
    fireEvent.click(screen.getByRole('button', { name: 'Try to fix' }))
    await waitFor(() =>
      expect(startEditorTransform).toHaveBeenCalledWith(
        expect.objectContaining({
          preset: 'fix_mermaid',
          text: '```mermaid\nBAD line\n```\n\nnote text',
        })
      )
    )
    emitDone('rewritten slice')
    await screen.findByText('Applies as markdown')
    expect(screen.getByRole('button', { name: 'Replace selection' })).not.toBeDisabled()
  })
})
