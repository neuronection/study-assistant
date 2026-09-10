import { useQueryClient } from '@tanstack/react-query'
import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { useTranslation } from 'react-i18next'

import { useChatStream } from '@/components/ui/chat-core'
import { createStudyChatTransport, type StudyChatTransport } from '@/features/chat/chatTransport'
import type { ChatAttachmentInput } from '@/lib/api'
import { getWsClient } from '@/lib/ws-client'
import { WsTopic } from '@/lib/constants'

function useStudyChatStream(propSessionId: number | null) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [sessionId, setSessionId] = useState(propSessionId)
  const sessionIdRef = useRef<number | null>(sessionId)
  sessionIdRef.current = sessionId
  const adoptingRef = useRef<number | null>(null)

  useEffect(() => {
    setSessionId(propSessionId)
  }, [propSessionId])

  const transportRef = useRef<StudyChatTransport | null>(null)
  if (transportRef.current === null) {
    transportRef.current = createStudyChatTransport({
      getSessionId: () => sessionIdRef.current,
      phaseLabel: (phase) => t(`chat.phase.${phase}`),
    })
  }

  const stream = useChatStream({ transport: transportRef.current })
  const reset = stream.reset

  useEffect(() => {
    if (sessionId === null) {
      return undefined
    }
    const unsubscribe = getWsClient().subscribe(WsTopic.chat(sessionId), (payload) => {
      transportRef.current?.push(payload)
    })
    return unsubscribe
  }, [sessionId])

  useEffect(() => {
    if (sessionId !== null && adoptingRef.current === sessionId) {
      adoptingRef.current = null
      return
    }
    reset()
  }, [sessionId, reset])

  useEffect(() => {
    if (stream.status !== 'done' && stream.status !== 'interrupted') {
      return
    }
    const current = sessionIdRef.current
    if (current === null) {
      reset()
      return
    }
    let cancelled = false
    void (async () => {
      await queryClient.invalidateQueries({ queryKey: ['chat-messages', current] })
      if (!cancelled) {
        reset()
      }
    })()
    return () => {
      cancelled = true
    }
  }, [stream.status, queryClient, reset])

  const send = async (text: string, attachments: ChatAttachmentInput[] = []) => {
    transportRef.current?.setAttachments(attachments)
    return stream.send(text)
  }

  const beginEdit = (messageId: number) => {
    transportRef.current?.beginEdit(messageId)
  }

  const beginRegenerate = (messageId: number) => {
    transportRef.current?.beginRegenerate(messageId)
  }

  const adoptSession = (session: { id: number }) => {
    adoptingRef.current = session.id
    sessionIdRef.current = session.id
    setSessionId(session.id)
  }

  return { sessionId, stream, send, beginEdit, beginRegenerate, adoptSession }
}

export interface StudyChat {
  sessionId: number | null
  stream: ReturnType<typeof useChatStream>
  send: (text: string, attachments?: ChatAttachmentInput[]) => Promise<boolean>
  beginEdit: (messageId: number) => void
  beginRegenerate: (messageId: number) => void
  adoptSession: (session: { id: number }) => void
}

const StudyChatContext = createContext<StudyChat | null>(null)

export function StudyChatProvider({
  sessionId,
  children,
}: {
  sessionId: number | null
  children: ReactNode
}) {
  const chat = useStudyChatStream(sessionId)
  return <StudyChatContext.Provider value={chat}>{children}</StudyChatContext.Provider>
}

export function useStudyChatContext(): StudyChat {
  const chat = useContext(StudyChatContext)
  if (chat === null) {
    throw new Error('useStudyChatContext requires a StudyChatProvider ancestor')
  }
  return chat
}
