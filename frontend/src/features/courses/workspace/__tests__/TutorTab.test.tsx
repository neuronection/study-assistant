import { useChatStore } from '@/lib/chat-store'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import {
  createChatSession,
  listChatSessions,
  primeDefaults,
  renderWorkspace,
} from './harness'

describe('TutorTab', () => {
  test('tutor tab lists node-bound sessions and ask opens the sidebar', async () => {
    primeDefaults()
    listChatSessions.mockResolvedValue([
      { id: '9', course_id: '3', node_id: '5', title: 'Derivatives chat' },
    ])
    createChatSession.mockResolvedValue({ id: '12', public_id: 'uuid-12', course_id: '3', node_id: '5', title: 'Derivatives' })
    renderWorkspace('/courses/3/n/5?tab=tutor')
    expect(await screen.findByText('Derivatives chat')).toBeInTheDocument()
    await waitFor(() => expect(listChatSessions).toHaveBeenCalledWith('5'))

    fireEvent.click(screen.getAllByRole('button', { name: /ask about this node/i })[0])
    await waitFor(() => expect(createChatSession).toHaveBeenCalledWith('3', '5', 'Derivatives'))
    await waitFor(() => expect(useChatStore.getState().open).toBe(true))
    expect(useChatStore.getState().session).toEqual({ id: '12', publicId: 'uuid-12' })
  })

})
