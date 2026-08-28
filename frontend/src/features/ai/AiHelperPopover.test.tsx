import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import type { Editor } from '@tiptap/react'

import { AiHelperPopover, type AiHelperContext } from './AiHelperPopover'

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

vi.mock('@/components/editor/LazyMarkdownEditor', () => ({
  LazyMarkdownEditor: ({
    value,
    onChange,
    ariaLabel,
  }: {
    value: string
    onChange: (markdown: string) => void
    ariaLabel: string
  }) => (
    <textarea
      aria-label={ariaLabel}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  ),
}))

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

function renderPopover(selection: { from: number; to: number } | null) {
  const onInsert = vi.fn()
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

describe('AiHelperPopover', () => {
  beforeEach(() => {
    textBetween.mockReturnValue('hello world')
    startEditorTransform.mockReset()
    getEditorTransformJob.mockReset()
    cancelEditorTransformJob.mockReset()
    insertMarkdown.mockClear()
  })

  test('opens, shows the free-form prompt and disables presets without a selection', () => {
    renderPopover(null)
    const dialog = openHelper()
    expect(dialog).not.toBeNull()
    expect(screen.getByPlaceholderText(/Ask the AI/)).not.toBeNull()
    expect(screen.getByText('Context')).not.toBeNull()
    expect(screen.getByText('Course material')).not.toBeNull()
    expect(screen.getByRole('button', { name: 'Explain' })).toBeDisabled()
    expect(dialog.querySelector('[data-popover-drag-handle]')).not.toBeNull()
    expect(dialog.querySelectorAll('[data-resize-dir]').length).toBe(8)
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
    selectionRef.current = { from: 1, to: 12 }
    openHelper()
    expect(screen.getByRole('button', { name: 'Explain' })).not.toBeDisabled()
    expect(screen.getByText('Context')).not.toBeNull()
  })

  test('a preset transform streams into review and inserts at the cursor', async () => {
    startEditorTransform.mockResolvedValue({ job_id: 7 })
    getEditorTransformJob.mockResolvedValue({
      status: 'running',
      result_md: '',
      error: null,
      problems: [],
      rounds: 0,
    })
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

  test('the review view renders markdown and can toggle to the rich editor', async () => {
    startEditorTransform.mockResolvedValue({ job_id: 11 })
    getEditorTransformJob.mockResolvedValue({
      status: 'running',
      result_md: '',
      error: null,
      problems: [],
      rounds: 0,
    })
    renderPopover({ from: 1, to: 12 })
    openHelper()
    fireEvent.click(screen.getByRole('button', { name: 'Explain' }))
    await waitFor(() => expect(startEditorTransform).toHaveBeenCalled())
    emitDone('## Heading\n\n**bold** and $x^2$')
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Insert at cursor' })).not.toBeNull()
    )
    expect(screen.getByRole('heading', { name: 'Heading' })).not.toBeNull()
    expect(screen.queryByLabelText('AI result')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }))
    expect(screen.getByLabelText('AI result')).toHaveValue('## Heading\n\n**bold** and $x^2$')
  })

  test('replace-selection passes the captured range to insertMarkdown', async () => {
    startEditorTransform.mockResolvedValue({ job_id: 10 })
    getEditorTransformJob.mockResolvedValue({
      status: 'running',
      result_md: '',
      error: null,
      problems: [],
      rounds: 0,
    })
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
    startEditorTransform.mockResolvedValue({ job_id: 8 })
    getEditorTransformJob.mockResolvedValue({
      status: 'running',
      result_md: '',
      error: null,
      problems: [],
      rounds: 0,
    })
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
    startEditorTransform.mockResolvedValue({ job_id: 9 })
    getEditorTransformJob.mockResolvedValue({
      status: 'running',
      result_md: '',
      error: null,
      problems: [],
      rounds: 0,
    })
    cancelEditorTransformJob.mockResolvedValue(undefined)
    renderPopover({ from: 1, to: 12 })
    openHelper()
    fireEvent.click(screen.getByRole('button', { name: 'Answer the question' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Stop' })).not.toBeNull())
    fireEvent.click(screen.getByRole('button', { name: 'Stop' }))
    await waitFor(() => expect(cancelEditorTransformJob).toHaveBeenCalledWith(9))
    await waitFor(() =>
      expect(screen.getByPlaceholderText(/Ask the AI/)).not.toBeNull()
    )
  })

  test('the whole-note action is offered when there is no selection', () => {
    renderPopover(null)
    openHelper()
    expect(screen.getByRole('button', { name: 'Apply to whole note' })).not.toBeNull()
  })
})