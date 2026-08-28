import { useNavigate } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { ChatPanel } from './ChatPanel'
import { ChatSessionList } from './ChatSessionList'
import { useActiveChatSession } from './useChatSession'
import { useChatStore } from '@/lib/chat-store'
import type { ChatSession } from '@/lib/api'

export function ChatPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const setOpen = useChatStore((state) => state.setOpen)
  const setSession = useChatStore((state) => state.setSession)
  const { chatId, sessionId, session, isResolving } = useActiveChatSession()

  const collapse = () => {
    if (session !== null) {
      setSession({ id: session.id, publicId: session.public_id })
    }
    setOpen(true)
    void navigate({ to: '/' })
  }

  const openCreated = (session: ChatSession) => {
    void navigate({ to: '/chat/$chatId', params: { chatId: session.public_id } })
  }

  return (
    <div className="flex h-full w-full">
      <aside className="border-border bg-subtle w-72 shrink-0 border-r">
        <ChatSessionList />
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        {chatId !== null && isResolving ? (
          <p className="text-muted-foreground p-8 text-center text-sm">
            {t('library.loading')}
          </p>
        ) : chatId !== null && session === null ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 p-8">
            <p className="text-muted-foreground text-sm">{t('chat.notFound')}</p>
          </div>
        ) : (
          <ChatPanel
            sessionId={sessionId}
            onSessionCreated={openCreated}
            variant="page"
            onCollapse={collapse}
          />
        )}
      </div>
    </div>
  )
}
