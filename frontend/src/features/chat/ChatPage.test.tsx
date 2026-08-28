import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { ChatPage } from './ChatPage'
import { useChatStore } from '@/lib/chat-store'

const navigate = vi.fn()

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigate,
}))

const activeSession = vi.hoisted(() => ({
  value: null as unknown as
    | { chatId: string | null; sessionId: number | null; session: unknown; isResolving: boolean }
    | undefined,
}))

vi.mock('./useChatSession', () => ({
  useActiveChatSession: () =>
    activeSession.value ?? {
      chatId: 'uuid-9',
      sessionId: 9,
      session: { id: 9, public_id: 'uuid-9' },
      isResolving: false,
    },
}))

vi.mock('./ChatPanel', () => ({
  ChatPanel: ({ onCollapse }: { onCollapse?: () => void }) => (
    <button type="button" onClick={onCollapse}>
      collapse
    </button>
  ),
}))

vi.mock('./ChatSessionList', () => ({
  ChatSessionList: () => null,
}))

function defaultSession(): void {
  activeSession.value = {
    chatId: 'uuid-9',
    sessionId: 9,
    session: { id: 9, public_id: 'uuid-9' },
    isResolving: false,
  }
}

describe('ChatPage', () => {
  beforeEach(() => {
    navigate.mockReset()
    useChatStore.setState({ open: false, session: null })
  })

  test('collapse opens the sidepanel pinned to the current session', async () => {
    defaultSession()
    render(<ChatPage />)

    fireEvent.click(screen.getByRole('button', { name: 'collapse' }))

    await waitFor(() => expect(navigate).toHaveBeenCalledWith({ to: '/' }))
    expect(useChatStore.getState().open).toBe(true)
    expect(useChatStore.getState().session).toEqual({ id: 9, publicId: 'uuid-9' })
  })

  test('collapse without a resolved session opens a fresh sidepanel', async () => {
    activeSession.value = { chatId: null, sessionId: null, session: null, isResolving: false }
    render(<ChatPage />)

    fireEvent.click(screen.getByRole('button', { name: 'collapse' }))

    await waitFor(() => expect(navigate).toHaveBeenCalledWith({ to: '/' }))
    expect(useChatStore.getState().open).toBe(true)
    expect(useChatStore.getState().session).toBeNull()
  })
})
