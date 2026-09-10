import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { AskMaterialsDialog } from './AskMaterialsDialog'
import type { Material } from '@/lib/api'
import { useChatStore } from '@/lib/chat-store'

const createChatSession = vi.fn()
const updateChatSessionQuizme = vi.fn()

vi.mock('@/lib/api', () => ({
  createChatSession: (...args: unknown[]) => createChatSession(...(args as [])),
  updateChatSessionQuizme: (...args: unknown[]) =>
    updateChatSessionQuizme(...(args as [number, boolean])),
}))

function material(id: number, title: string): Material {
  return {
    id,
    course_id: 3,
    title,
    kind: 'pdf',
    status: 'ready',
    filename: `${title}.pdf`,
    mime: 'application/pdf',
    pages: null,
    group_id: null,
    folder_id: null,
    blob_sha: null,
    created_at: '2026-09-07T00:00:00Z',
  }
}

const MATERIALS = [material(12, 'Lecture notes'), material(7, 'Problem set')]

describe('AskMaterialsDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useChatStore.setState({
      open: false,
      session: null,
      pendingSend: null,
      viewerAsks: {},
      selectionAsks: {},
      width: 384,
    })
  })

  test('renders every attached material and disables Ask until text is present', async () => {
    render(<AskMaterialsDialog materials={MATERIALS} onClose={() => undefined} />)
    expect(screen.getByText('Lecture notes')).toBeInTheDocument()
    expect(screen.getByText('Problem set')).toBeInTheDocument()
    expect(
      screen.getByText('Attached materials (2)', { exact: false }),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled()
    expect(createChatSession).not.toHaveBeenCalled()
  })

  test('chips fill the input with multi-material phrasing', async () => {
    render(<AskMaterialsDialog materials={MATERIALS} onClose={() => undefined} />)
    fireEvent.click(screen.getByRole('button', { name: 'Summarize' }))
    const input = screen.getByLabelText('Your question') as HTMLTextAreaElement
    expect(input.value).toBe('Summarize the key points across these materials.')
    expect(createChatSession).not.toHaveBeenCalled()
  })

  test('submit attaches every material to one new session and queues the send', async () => {
    createChatSession.mockResolvedValue({
      id: 31,
      public_id: 'uuid-31',
      course_id: 3,
      title: '2 materials',
    })
    const onClose = vi.fn()
    render(<AskMaterialsDialog materials={MATERIALS} onClose={onClose} />)
    const input = screen.getByLabelText('Your question') as HTMLTextAreaElement
    fireEvent.change(input, { target: { value: 'Compare these two.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    await waitFor(() =>
      expect(createChatSession).toHaveBeenCalledWith(3, null, '2 materials'),
    )
    const state = useChatStore.getState()
    expect(state.open).toBe(true)
    expect(state.session).toEqual({ id: 31, publicId: 'uuid-31' })
    expect(state.selectionAsks['7-12']).toEqual({ id: 31, publicId: 'uuid-31' })
    expect(state.pendingSend).toEqual({
      content: 'Compare these two.',
      attachments: [
        { kind: 'material', id: 12, title: 'Lecture notes' },
        { kind: 'material', id: 7, title: 'Problem set' },
      ],
      mode: 'send',
    })
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  test('the quiz-me chip keeps its flag and patches the session', async () => {
    createChatSession.mockResolvedValue({
      id: 31,
      public_id: 'uuid-31',
      course_id: 3,
      title: '2 materials',
    })
    updateChatSessionQuizme.mockResolvedValue({ id: 31, quizme: true })
    render(<AskMaterialsDialog materials={MATERIALS} onClose={() => undefined} />)
    fireEvent.click(screen.getByRole('button', { name: 'Quiz me' }))
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    await waitFor(() => expect(updateChatSessionQuizme).toHaveBeenCalledWith(31, true))
  })

  test('more than ten selected materials disables Ask with a warning', () => {
    const many = Array.from({ length: 11 }, (_, index) => material(index + 1, `M${index + 1}`))
    render(<AskMaterialsDialog materials={many} onClose={() => undefined} />)
    const input = screen.getByLabelText('Your question') as HTMLTextAreaElement
    fireEvent.change(input, { target: { value: 'Too many' } })
    expect(screen.getByRole('alert')).toHaveTextContent('Attach at most 10 materials')
    expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled()
  })

  test('a single material keeps singular phrasing and title', async () => {
    createChatSession.mockResolvedValue({
      id: 21,
      public_id: 'uuid-21',
      course_id: 3,
      title: 'Lecture notes',
    })
    render(
      <AskMaterialsDialog materials={[material(12, 'Lecture notes')]} onClose={() => undefined} />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Summarize' }))
    const input = screen.getByLabelText('Your question') as HTMLTextAreaElement
    expect(input.value).toBe('Summarize the key points of this material.')
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    await waitFor(() =>
      expect(createChatSession).toHaveBeenCalledWith(3, null, 'Lecture notes'),
    )
  })
})
