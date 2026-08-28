import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import type { TextFileEditState } from '@/lib/api'
import { NewTextFileDialog } from './NewTextFileDialog'

vi.mock('@/components/editor/LazyMarkdownEditor', () => ({
  LazyMarkdownEditor: ({
    value,
    onChange,
    ariaLabel,
    drawingAdapter,
    aiHelper,
  }: {
    value: string
    onChange: (markdown: string) => void
    ariaLabel: string
    drawingAdapter?: {
      create: (strokes: unknown[], pngBase64: string, ocr: boolean) => Promise<number | null>
    }
    aiHelper?: { courseId?: number; title: string }
  }) => (
    <div>
      <input
        aria-label={ariaLabel}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <button
        type="button"
        aria-label={`dialog-ai-helper-${aiHelper?.courseId ?? 'none'}`}
      >
        dialog-ai-helper
      </button>
      {drawingAdapter ? (
        <button
          type="button"
          onClick={() => void drawingAdapter.create([{ points: [[0, 0]] }], 'AAA', true)}
        >
          editor-create-drawing
        </button>
      ) : null}
    </div>
  ),
}))

const editState = (overrides: Partial<TextFileEditState> = {}): TextFileEditState => ({
  materialId: 7,
  content: '',
  refToReal: {},
  jobId: null,
  ...overrides,
})

describe('NewTextFileDialog', () => {
  test('passes the course to the AI helper when provided', () => {
    render(
      <NewTextFileDialog
        defaultKind="md"
        courseId={5}
        onCreate={vi.fn().mockResolvedValue(null)}
        onSave={vi.fn()}
        onCancel={() => {}}
      />
    )
    expect(screen.getByRole('button', { name: 'dialog-ai-helper-5' })).not.toBeNull()
  })

  test('creates a markdown file with edited content and keeps the dialog open', async () => {
    const onCreate = vi.fn().mockResolvedValue(editState({ content: '$x^2$ rules' }))
    const onCancel = vi.fn()
    render(
      <NewTextFileDialog
        defaultKind="md"
        onCreate={onCreate}
        onSave={vi.fn()}
        onCancel={onCancel}
      />
    )
    fireEvent.change(screen.getByPlaceholderText('File name'), {
      target: { value: 'derivation' },
    })
    fireEvent.change(screen.getByLabelText('File content (markdown + LaTeX)'), {
      target: { value: '$x^2$ rules' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    await waitFor(() =>
      expect(onCreate).toHaveBeenCalledWith('derivation.md', '$x^2$ rules', [])
    )
    expect(onCancel).not.toHaveBeenCalled()
    expect(await screen.findByRole('button', { name: 'Save' })).not.toBeNull()
    expect(screen.getByRole('button', { name: 'Done' })).not.toBeNull()
  })

  test('plain text kind keeps the name without extension', async () => {
    const onCreate = vi.fn().mockResolvedValue(editState({ content: 'plain words' }))
    render(
      <NewTextFileDialog
        defaultKind="md"
        onCreate={onCreate}
        onSave={vi.fn()}
        onCancel={() => {}}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: 'Plain text' }))
    fireEvent.change(screen.getByPlaceholderText('File name'), {
      target: { value: 'scratch' },
    })
    fireEvent.change(screen.getByLabelText('File content (markdown + LaTeX)'), {
      target: { value: 'plain words' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    await waitFor(() => expect(onCreate).toHaveBeenCalledWith('scratch', 'plain words', []))
  })

  test('Enter in the name field submits', async () => {
    const onCreate = vi.fn().mockResolvedValue(editState({ content: '' }))
    render(
      <NewTextFileDialog
        defaultKind="md"
        onCreate={onCreate}
        onSave={vi.fn()}
        onCancel={() => {}}
      />
    )
    const name = screen.getByPlaceholderText('File name')
    fireEvent.change(name, { target: { value: 'notes' } })
    fireEvent.keyDown(name, { key: 'Enter' })
    await waitFor(() => expect(onCreate).toHaveBeenCalledWith('notes.md', '', []))
  })

  test('create stays disabled without a name and cancel aborts', async () => {
    const onCreate = vi.fn()
    const onCancel = vi.fn()
    render(
      <NewTextFileDialog
        defaultKind="txt"
        onCreate={onCreate}
        onSave={vi.fn()}
        onCancel={onCancel}
      />
    )
    expect(screen.getByRole('button', { name: 'Create' })).toBeDisabled()
    fireEvent.change(screen.getByPlaceholderText('File name'), {
      target: { value: '   ' },
    })
    expect(screen.getByRole('button', { name: 'Create' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onCancel).toHaveBeenCalled()
    expect(onCreate).not.toHaveBeenCalled()
  })

  test('kind toggle reflects the default kind', () => {
    render(
      <NewTextFileDialog
        defaultKind="txt"
        onCreate={vi.fn().mockResolvedValue(null)}
        onSave={vi.fn()}
        onCancel={() => {}}
      />
    )
    expect(screen.getByRole('button', { name: 'Plain text' }).className).toContain(
      'font-medium'
    )
    expect(screen.getByRole('button', { name: 'Markdown' }).className).not.toContain(
      'font-medium'
    )
  })

  test('drawings buffered in the dialog ride along with the create', async () => {
    const onCreate = vi.fn().mockResolvedValue(editState({ content: '' }))
    render(
      <NewTextFileDialog
        defaultKind="md"
        onCreate={onCreate}
        onSave={vi.fn()}
        onCancel={() => {}}
      />
    )
    fireEvent.change(screen.getByPlaceholderText('File name'), {
      target: { value: 'handwritten' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'editor-create-drawing' }))
    fireEvent.click(screen.getByRole('button', { name: 'editor-create-drawing' }))
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    await waitFor(() =>
      expect(onCreate).toHaveBeenCalledWith('handwritten.md', '', [
        { ref: -1, strokes: [{ points: [[0, 0]] }], png_base64: 'AAA', ocr: true },
        { ref: -2, strokes: [{ points: [[0, 0]] }], png_base64: 'AAA', ocr: true },
      ])
    )
  })

  test('a deduplicated create closes the dialog', async () => {
    const onCancel = vi.fn()
    const onCreate = vi.fn().mockResolvedValue(null)
    render(
      <NewTextFileDialog
        defaultKind="md"
        onCreate={onCreate}
        onSave={vi.fn()}
        onCancel={onCancel}
      />
    )
    fireEvent.change(screen.getByPlaceholderText('File name'), {
      target: { value: 'dup' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    await waitFor(() => expect(onCancel).toHaveBeenCalled())
  })

  test('save persists edits to the created material and stays open', async () => {
    const onCreate = vi.fn().mockResolvedValue(editState({ content: 'draft' }))
    const onSave = vi.fn().mockResolvedValue(editState({ content: 'draft + more' }))
    render(
      <NewTextFileDialog
        defaultKind="md"
        onCreate={onCreate}
        onSave={onSave}
        onCancel={() => {}}
      />
    )
    fireEvent.change(screen.getByPlaceholderText('File name'), {
      target: { value: 'notes' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    const saveButton = await screen.findByRole('button', { name: 'Save' })
    expect(saveButton).toBeDisabled()
    fireEvent.change(screen.getByLabelText('File content (markdown + LaTeX)'), {
      target: { value: 'draft + more' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith('draft + more', [], expect.objectContaining({ materialId: 7 }))
    )
    expect(await screen.findByRole('button', { name: 'Done' })).not.toBeNull()
  })

  test('save remaps committed drawing refs onto the dialog', async () => {
    const onCreate = vi
      .fn()
      .mockResolvedValue(editState({ content: '![d](ca-drawing://3)' }))
    render(
      <NewTextFileDialog
        defaultKind="md"
        onCreate={onCreate}
        onSave={vi.fn()}
        onCancel={() => {}}
      />
    )
    fireEvent.change(screen.getByPlaceholderText('File name'), {
      target: { value: 'notes' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'editor-create-drawing' }))
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save' })).not.toBeNull())
    expect(screen.getByLabelText('File content (markdown + LaTeX)')).toHaveValue(
      '![d](ca-drawing://3)'
    )
  })
})