import {useQuery} from '@tanstack/react-query'
import {useNavigate} from '@tanstack/react-router'
import {Loader2, MessageSquare} from 'lucide-react'
import {useTranslation} from 'react-i18next'
import {Button} from '@/components/ui/button'
import {EmptyState} from '@/components/ui/empty-state'
import {TabActionBar} from '@/components/layout/TabActionBar'
import {listChatSessions} from '@/lib/api'

export function TutorTab({
  currentId,
  nodeTitle,
  onAsk,
  askPending,
}: {
  currentId: string
  nodeTitle: string
  onAsk: (targetId: string, title: string) => void
  askPending: boolean
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const sessions = useQuery({
    queryKey: ['chat-sessions', 'node', currentId],
    queryFn: () => listChatSessions(currentId),
  })

  return (
    <div className="space-y-4">
      <TabActionBar
        actions={[
          {
            label: t('workspace.askAbout'),
            icon: MessageSquare,
            onAction: () => onAsk(currentId, nodeTitle),
            pending: askPending,
            primary: true,
          },
        ]}
      />
      <div className="space-y-1">
        {(sessions.data ?? []).length === 0 ? (
          <EmptyState
            icon={MessageSquare}
            title={t('workspace.noSessions')}
            description={t('workspace.tutorEmptyDesc')}
            action={
              <Button size="sm" disabled={askPending} onClick={() => onAsk(currentId, nodeTitle)}>
                {askPending ? (
                  <Loader2 className="animate-spin" aria-hidden />
                ) : (
                  <MessageSquare aria-hidden />
                )}
                {t('workspace.tutorStartChat')}
              </Button>
            }
          />
        ) : (
          (sessions.data ?? []).map((session) => (
            <button
              key={session.id}
              type="button"
              className="hover:bg-subtle flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm"
              onClick={() =>
                void navigate({ to: '/chat/$chatId', params: { chatId: session.public_id } })
              }
            >
              <MessageSquare className="text-muted-foreground size-4 shrink-0" aria-hidden />
              <span className="flex-1 truncate">{session.title}</span>
              <span className="text-muted-foreground shrink-0 text-xs">
                {t('chat.sessionLabel', { title: '', id: session.id })}
              </span>
            </button>
          ))
        )}
      </div>
    </div>
  )
}

