import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  ChatSessionList as ChatSessionListBase,
  type ChatSessionView,
} from '@/components/ui/chat-session-list'
import { RenameDialog } from '@/components/RenameDialog'
import { UndoDeleteNotice } from '@/components/UndoDeleteNotice'
import {
  deleteChatSession,
  listChatSessions,
  renameChatSession,
  type ChatSession,
} from '@/lib/api'
import { useActiveChatSession } from '@/features/chat/useChatSession'
import { exportSessionAsMarkdown } from '@/features/chat/exportSessionMarkdown'
import { useConfirm } from '@/lib/use-confirm'

export function ChatSessionList({
  onSelect,
  onSelectSession,
  onNewChat,
  activeSessionId,
}: {
  onSelect?: () => void
  onSelectSession?: (session: ChatSession) => void
  onNewChat?: () => void
  activeSessionId?: number | null
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const urlSessionId = useActiveChatSession().sessionId
  const activeSession = activeSessionId ?? urlSessionId
  const [renaming, setRenaming] = useState<{ id: number; title: string } | null>(null)
  const [confirm, confirmElement] = useConfirm()
  const [deletedItemId, setDeletedItemId] = useState<number | null>(null)

  const sessions = useQuery({ queryKey: ['chat-sessions'], queryFn: () => listChatSessions() })

  const rename = useMutation({
    mutationFn: ({ id, title }: { id: number; title: string }) =>
      renameChatSession(id, title),
    onSuccess: async () => {
      setRenaming(null)
      await queryClient.invalidateQueries({ queryKey: ['chat-sessions'] })
    },
  })

  const remove = useMutation({
    mutationFn: (id: number) => deleteChatSession(id),
    onSuccess: async (result) => {
      if (activeSession === result.deleted_item_id) {
        if (onNewChat) {
          onNewChat()
        } else {
          void navigate({ to: '/chat' })
        }
      }
      setDeletedItemId(result.deleted_item_id)
      await queryClient.invalidateQueries({ queryKey: ['chat-sessions'] })
    },
  })

  const byId = new Map((sessions.data ?? []).map((session) => [String(session.id), session]))

  const select = (session: ChatSession) => {
    if (onSelectSession) {
      onSelectSession(session)
    } else {
      void navigate({ to: '/chat/$chatId', params: { chatId: session.public_id } })
    }
    onSelect?.()
  }

  const newChat = () => {
    if (onNewChat) {
      onNewChat()
    } else {
      void navigate({ to: '/chat' })
    }
    onSelect?.()
  }

  const views: ChatSessionView[] = (sessions.data ?? []).map((session) => ({
    id: String(session.id),
    title: session.title || t('chat.newSession'),
    updatedAt: session.created_at,
  }))

  return (
    <div className="flex h-full min-h-0 flex-col p-2">
      <UndoDeleteNotice deletedItemId={deletedItemId} onDismiss={() => setDeletedItemId(null)} />
      <ChatSessionListBase
        sessions={views}
        activeId={activeSession !== null ? String(activeSession) : null}
        onSelect={(id) => {
          const session = byId.get(id)
          if (session !== undefined) {
            select(session)
          }
        }}
        onNew={newChat}
        onRename={(id) => {
          const session = byId.get(id)
          if (session !== undefined) {
            setRenaming({ id: session.id, title: session.title })
          }
        }}
        onDelete={(id) => {
          const session = byId.get(id)
          if (session === undefined) {
            return
          }
          void (async () => {
            const ok = await confirm({
              title: t('chat.deleteSession'),
              description: t('chat.confirmDeleteSession', {
                title: session.title || t('chat.newSession'),
              }),
              confirmLabel: t('chat.deleteSession'),
              cancelLabel: t('common.cancel'),
            })
            if (ok) {
              remove.mutate(session.id)
            }
          })()
        }}
        onExport={(id) => {
          const session = byId.get(id)
          if (session !== undefined) {
            void exportSessionAsMarkdown(session)
          }
        }}
        labels={{
          search: t('chat.search'),
          searchPlaceholder: t('chat.search'),
          newChat: t('chat.newSession'),
          rename: t('chat.renameSession'),
          delete: t('chat.deleteSession'),
          export: t('chat.sessionExport'),
          today: t('chat.time.today'),
          yesterday: t('chat.time.yesterday'),
          earlier: t('chat.time.earlier'),
          empty: t('chat.noChats'),
          noResults: t('chat.noResults'),
        }}
      />
      {renaming !== null ? (
        <RenameDialog
          title={t('chat.renameSession')}
          initialName={renaming.title}
          onClose={() => setRenaming(null)}
          onConfirm={(title) => rename.mutate({ id: renaming.id, title })}
        />
      ) : null}
      {confirmElement}
    </div>
  )
}
