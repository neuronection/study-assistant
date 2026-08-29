import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { Download, MessageSquare, MoreHorizontal, Pencil, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { PopoverMenu } from '@/components/ui/popover-menu'
import { RenameDialog } from '@/components/RenameDialog'
import { SearchInput } from '@/components/ui/SearchInput'
import { UndoDeleteNotice } from '@/components/UndoDeleteNotice'
import { deleteChatSession, listChatSessions, renameChatSession, type ChatSession } from '@/lib/api'
import { useActiveChatSession } from '@/features/chat/useChatSession'
import { exportSessionAsMarkdown } from '@/features/chat/exportSessionMarkdown'
import { cn } from '@/lib/utils'
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
  const [query, setQuery] = useState('')
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

  const timeLabel = (iso: string): string => {
    const date = new Date(iso)
    if (Number.isNaN(date.getTime())) {
      return ''
    }
    const minutes = Math.floor((Date.now() - date.getTime()) / 60000)
    if (minutes < 1) return t('chat.time.justNow')
    if (minutes < 60) return t('chat.time.minutesAgo', { count: minutes })
    const hours = Math.floor(minutes / 60)
    if (hours < 24) return t('chat.time.hoursAgo', { count: hours })
    const days = Math.floor(hours / 24)
    if (days === 1) return t('chat.time.yesterday')
    if (days < 7) return t('chat.time.daysAgo', { count: days })
    return date.toLocaleDateString()
  }

  const all = sessions.data ?? []
  const normalized = query.trim().toLowerCase()
  const filtered = normalized
    ? all.filter((session) => session.title.toLowerCase().includes(normalized))
    : all

  return (
    <div className="flex h-full min-h-0 flex-col">
      <UndoDeleteNotice deletedItemId={deletedItemId} onDismiss={() => setDeletedItemId(null)} />
      <div className="border-border space-y-2 border-b p-2">
        <SearchInput
          value={query}
          onChange={setQuery}
          placeholder={t('chat.search')}
          ariaLabel={t('chat.search')}
        />
        <Button variant="outline" size="sm" className="w-full" onClick={newChat}>
          <Plus className="size-4" aria-hidden />
          {t('chat.newSession')}
        </Button>
      </div>
      <div className="min-h-0 flex-1 space-y-0.5 overflow-y-auto p-2">
        {filtered.length === 0 ? (
          <p className="text-muted-foreground px-2 py-6 text-center text-xs">
            {query.trim() ? t('chat.noResults') : t('chat.noChats')}
          </p>
        ) : (
          filtered.map((session) => {
            const active = session.id === activeSession
            return (
              <div
                key={session.id}
                className={cn(
                  'group flex items-center rounded-md transition-colors',
                  active ? 'bg-surface' : 'hover:bg-subtle',
                )}
              >
                <button
                  type="button"
                  onClick={() => select(session)}
                  aria-current={active ? 'true' : undefined}
                  aria-label={t('chat.sessionLabel', {
                    title: session.title || t('chat.newSession'),
                    id: session.id,
                  })}
                  className="flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-2 text-left"
                >
                  <MessageSquare
                    className={cn(
                      'size-4 shrink-0',
                      active ? 'text-primary' : 'text-muted-foreground',
                    )}
                    aria-hidden
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm">
                      {session.title || t('chat.newSession')}
                    </span>
                    <span className="text-muted-foreground block truncate text-[11px]">
                      {timeLabel(session.created_at)}
                    </span>
                  </span>
                </button>
                <PopoverMenu
                  label={t('chat.sessionActionsFor', {
                    title: session.title || t('chat.newSession'),
                  })}
                  triggerClassName="size-7 mr-1 shrink-0"
                  trigger={<MoreHorizontal className="size-4" aria-hidden />}
                  items={[
                    {
                      key: 'rename',
                      label: t('chat.renameSession'),
                      icon: Pencil,
                      onSelect: () =>
                        setRenaming({ id: session.id, title: session.title }),
                    },
                    {
                      key: 'export',
                      label: t('chat.sessionExport'),
                      icon: Download,
                      onSelect: () => {
                        void exportSessionAsMarkdown(session)
                      },
                    },
                    {
                      key: 'delete',
                      label: t('chat.deleteSession'),
                      icon: Trash2,
                      danger: true,
                      onSelect: async () => {
                        const ok = await confirm({
                          title: t('chat.deleteSession'),
                          description: t('chat.confirmDeleteSession', {
                            title: session.title || t('chat.newSession'),
                          }),
                          confirmLabel: t('chat.deleteSession'),
                          cancelLabel: t('common.cancel'),
                        })
                        if (ok) remove.mutate(session.id)
                      },
                    },
                  ]}
                />
              </div>
            )
          })
        )}
      </div>
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
