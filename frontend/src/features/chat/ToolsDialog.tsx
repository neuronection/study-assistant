import { useQuery } from '@tanstack/react-query'
import { Loader2, Wrench, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { ChatToolsCatalog, type ChatToolCatalogEntry } from '@/components/ui/chat-tools-catalog'
import { Button } from '@/components/ui/button'
import { ErrorBanner } from '@/components/ErrorBanner'
import { listAiTools, type AiToolInfo } from '@/lib/api'
import { useCloseFloatings } from '@/lib/ui-overlays'

function toolCatalogEntry(tool: AiToolInfo): ChatToolCatalogEntry {
  return {
    name: tool.name,
    description: tool.scope
      ? `${tool.description} ${tool.scope}`
      : tool.description,
    arguments: tool.arguments.map((argument) => ({
      name: argument.name,
      type: argument.type,
      required: argument.required,
      description: argument.description,
    })),
    example: tool.example,
    response: tool.response,
  }
}

export function ToolsDialog({ onClose }: { onClose: () => void }) {
  useCloseFloatings()
  const { t } = useTranslation()
  const catalog = useQuery({ queryKey: ['ai-tools'], queryFn: listAiTools })
  const entries = (catalog.data ?? []).map((tool) => {
    const entry = toolCatalogEntry(tool)
    if (!tool.hitl) return entry
    return {
      ...entry,
      badge: { label: t('chat.tools.hitlBadge'), tone: 'warning' as const },
    }
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-surface border-border flex max-h-[85vh] w-full max-w-lg flex-col rounded-lg border shadow-[var(--as-shadow-2)]">
        <header className="border-border flex items-center justify-between border-b px-4 py-3">
          <span className="flex items-center gap-2 text-sm font-semibold">
            <Wrench className="size-4" aria-hidden />
            {t('chat.tools.title')}
          </span>
          <Button variant="ghost" size="icon" onClick={onClose} title={t('chat.close')}>
            <X className="size-4" aria-hidden />
          </Button>
        </header>
        <div className="overflow-y-auto p-4">
          {catalog.isPending ? (
            <p className="text-muted-foreground flex items-center gap-2 py-8 text-center text-sm">
              <Loader2 className="size-4 animate-spin" aria-hidden />
              {t('chat.tools.loading')}
            </p>
          ) : null}
          <ErrorBanner
            message={catalog.isError ? (catalog.error as Error).message : null}
          />
          <ChatToolsCatalog
            tools={entries}
            labels={{
              tools: t('chat.tools.title'),
              search: t('chat.tools.search'),
              searchPlaceholder: t('chat.tools.searchPlaceholder'),
              arguments: t('chat.tools.arguments'),
              response: t('chat.tools.response'),
              required: t('chat.tools.required'),
              optional: t('chat.tools.optional'),
              empty: t('chat.tools.empty'),
              noResults: t('chat.tools.noResults'),
            }}
          />
        </div>
      </div>
    </div>
  )
}
