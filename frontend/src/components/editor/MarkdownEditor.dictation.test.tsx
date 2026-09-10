import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { transcribeAudio } from '@/lib/api'
import {
  installDictationMediaStub,
  removeMediaSupport,
} from '@/test/dictationMedia'

import { MarkdownEditor } from './MarkdownEditor'

vi.mock('mermaid', () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn(async (_id: string, code: string) => ({
      svg: `<svg data-testid="mermaid-svg" data-code="${code}"></svg>`,
    })),
  },
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    transcribeAudio: vi.fn(),
  }
})

const transcribeMock = vi.mocked(transcribeAudio)

function proseRoot(): HTMLElement {
  const node = document.querySelector('.ProseMirror')
  if (node === null) {
    throw new Error('prosemirror root not mounted')
  }
  return node as HTMLElement
}

afterEach(() => {
  vi.unstubAllGlobals()
  transcribeMock.mockReset()
})

describe('MarkdownEditor dictation', () => {
  test('inserts the transcript at the cursor', async () => {
    installDictationMediaStub()
    transcribeMock.mockResolvedValue({
      text: 'a dictated sentence',
      model: 'whisper-1',
    })
    const onChange = vi.fn()
    render(<MarkdownEditor value="" onChange={onChange} ariaLabel="Note body" />)

    fireEvent.click(screen.getByRole('button', { name: 'Dictate' }))
    const stop = await screen.findByRole('button', { name: 'Insert' })
    fireEvent.click(stop)

    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith('a dictated sentence')
    })
    expect(proseRoot().textContent).toContain('a dictated sentence')
    expect(screen.queryByRole('button', { name: 'Insert' })).toBeNull()
  })

  test('cancel leaves the document untouched', async () => {
    installDictationMediaStub()
    const onChange = vi.fn()
    render(
      <MarkdownEditor value="existing text" onChange={onChange} ariaLabel="Note body" />,
    )
    await waitFor(() => expect(proseRoot().textContent).toContain('existing text'))

    fireEvent.click(screen.getByRole('button', { name: 'Dictate' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }))

    expect(transcribeMock).not.toHaveBeenCalled()
    expect(onChange).not.toHaveBeenCalled()
    expect(proseRoot().textContent).toContain('existing text')
  })

  test('shows the unassigned hint when no model is set', async () => {
    installDictationMediaStub()
    transcribeMock.mockRejectedValue(
      new (await import('@/lib/api')).ApiError('unassigned', 409),
    )
    render(<MarkdownEditor value="" onChange={vi.fn()} ariaLabel="Note body" />)

    fireEvent.click(screen.getByRole('button', { name: 'Dictate' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Insert' }))

    await screen.findByRole('alert')
    expect(screen.getByRole('alert').textContent).toContain('speech-to-text model')
  })

  test('reports unsupported browsers through the strip', async () => {
    removeMediaSupport()
    render(<MarkdownEditor value="" onChange={vi.fn()} ariaLabel="Note body" />)

    fireEvent.click(screen.getByRole('button', { name: 'Dictate' }))

    await screen.findByRole('alert')
    expect(screen.getByRole('alert').textContent).toContain('MediaRecorder')
  })
})
