import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { AskAiPopover } from './AskAiPopover'
import { useChatStore } from '@/lib/chat-store'

const createChatSession = vi.fn()
const updateChatSessionQuizme = vi.fn()

vi.mock('@/lib/api', () => ({
  createChatSession: (...args: unknown[]) => createChatSession(...(args as [])),
  updateChatSessionQuizme: (...args: unknown[]) =>
    updateChatSessionQuizme(...(args as [number, boolean])),
}))

const MATERIAL = { id: 12, course_id: 3, title: 'Lecture notes', kind: 'pdf' }

describe('AskAiPopover (plan 61-B)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useChatStore.setState({
      open: false,
      session: null,
      pendingSend: null,
      viewerAsks: {},
      width: 384,
    })
  })

  test('chips fill the input without any network call', async () => {
    render(<AskAiPopover material={MATERIAL} scopeNodeId={8} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Ask the AI about this material' }))
    const chip = await screen.findByRole('button', { name: 'Summarize' })
    fireEvent.click(chip)
    const input = (await screen.findByPlaceholderText(
      'Ask anything about this material…',
    )) as HTMLTextAreaElement
    expect(input.value).toBe('Summarize the key points of this material.')
    expect(createChatSession).not.toHaveBeenCalled()
    expect(useChatStore.getState().pendingSend).toBeNull()
  })

  test('submit asks with the material attached and the store carries the send', async () => {
    createChatSession.mockResolvedValue({
      id: 21,
      public_id: 'uuid-21',
      course_id: 3,
      title: 'Lecture notes',
    })
    render(<AskAiPopover material={MATERIAL} scopeNodeId={8} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Ask the AI about this material' }))
    const input = (await screen.findByPlaceholderText(
      'Ask anything about this material…',
    )) as HTMLTextAreaElement
    fireEvent.change(input, { target: { value: 'Why does the limit fail here?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    await waitFor(() => expect(createChatSession).toHaveBeenCalledWith(3, 8, 'Lecture notes'))
    const state = useChatStore.getState()
    expect(state.open).toBe(true)
    expect(state.pendingSend).toEqual({
      content: 'Why does the limit fail here?',
      attachments: [{ kind: 'material', id: 12, title: 'Lecture notes' }],
      mode: 'send',
    })
  })

  test('empty input disables submit; Enter submits typed text', async () => {
    render(<AskAiPopover material={MATERIAL} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Ask the AI about this material' }))
    const input = (await screen.findByPlaceholderText(
      'Ask anything about this material…',
    )) as HTMLTextAreaElement
    const submit = screen.getByRole('button', { name: 'Ask' })
    expect(submit).toBeDisabled()
    fireEvent.change(input, { target: { value: 'hi' } })
    expect(submit).toBeEnabled()
    fireEvent.keyDown(input, { key: 'Enter' })
    await waitFor(() => expect(useChatStore.getState().pendingSend?.content).toBe('hi'))
  })

  test('an unedited quiz-me chip enables quiz mode on the session', async () => {
    createChatSession.mockResolvedValue({
      id: 21,
      public_id: 'uuid-21',
      course_id: 3,
      title: 'Lecture notes',
    })
    updateChatSessionQuizme.mockResolvedValue({ id: 21, quizme: true })
    render(<AskAiPopover material={MATERIAL} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Ask the AI about this material' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Quiz me' }))
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    await waitFor(() => expect(updateChatSessionQuizme).toHaveBeenCalledWith(21, true))
    expect(useChatStore.getState().pendingSend?.content).toBe(
      'Quiz me on this material, one question at a time.',
    )
  })

  test('an edited chip text sends as a plain question without quiz mode', async () => {
    createChatSession.mockResolvedValue({
      id: 21,
      public_id: 'uuid-21',
      course_id: 3,
      title: 'Lecture notes',
    })
    render(<AskAiPopover material={MATERIAL} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Ask the AI about this material' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Quiz me' }))
    const input = (await screen.findByPlaceholderText(
      'Ask anything about this material…',
    )) as HTMLTextAreaElement
    fireEvent.change(input, { target: { value: 'Quiz me on the second section only' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    await waitFor(() => expect(createChatSession).toHaveBeenCalled())
    expect(updateChatSessionQuizme).not.toHaveBeenCalled()
  })
})
