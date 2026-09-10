import { useQuery } from '@tanstack/react-query'
import { useRouterState } from '@tanstack/react-router'

import { listChatSessions, type ChatSession } from '@/lib/api'
import { useChatStore } from '@/lib/chat-store'

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
  const storeSession = useChatStore((state) => state.session)
  const chatId = extractChatId(pathname)
  const sessions = useQuery({ queryKey: ['chat-sessions'], queryFn: () => listChatSessions() })
  const loaded = sessions.data !== undefined
  const listed =
    chatId !== null ? (sessions.data?.find((entry) => entry.public_id === chatId) ?? null) : null
  const storeRef =
    chatId !== null && listed === null && storeSession?.publicId === chatId ? storeSession : null
  const bridging = storeRef !== null && (sessions.isFetching || !loaded)
  const sessionId = listed?.id ?? (bridging ? storeRef.id : null)
  return {
    chatId,
    sessionId,
    session: listed,
    isResolving: chatId !== null && !loaded,
  }
}
