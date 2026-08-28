import { useQuery } from '@tanstack/react-query'
import { useRouterState } from '@tanstack/react-router'

import { listChatSessions, type ChatSession } from '@/lib/api'

function extractChatId(pathname: string): string | null {
  const match = /^\/chat\/([^/]+)$/.exec(pathname)
  return match ? match[1] : null
}

export interface ActiveChatSession {
  chatId: string | null
  sessionId: number | null
  session: ChatSession | null
  isResolving: boolean
}

export function useActiveChatSession(): ActiveChatSession {
  const pathname = useRouterState({ select: (state) => state.location.pathname })
  const chatId = extractChatId(pathname)
  const sessions = useQuery({ queryKey: ['chat-sessions'], queryFn: () => listChatSessions() })
  const loaded = sessions.data !== undefined
  const session = chatId
    ? (sessions.data?.find((entry) => entry.public_id === chatId) ?? null)
    : null
  return {
    chatId,
    sessionId: session?.id ?? null,
    session,
    isResolving: chatId !== null && !loaded,
  }
}
