import { useQuery } from '@tanstack/react-query'
import { Loader2, Wrench, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorBanner } from '@/components/ErrorBanner'
import { listAiTools, type AiToolInfo } from '@/lib/api'
import { useCloseFloatings } from '@/lib/ui-overlays'

function ToolCard({ tool }: { tool: AiToolInfo }) {
  const { t } = useTranslation()
  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-mono text-sm">{tool.name}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-xs">
        <p>{tool.description}</p>
        {tool.example ? (
          <pre className="bg-subtle border-border rounded-md border p-2 font-mono text-[11px] whitespace-pre-wrap">
            {tool.example}
          </pre>
        ) : null}
        {tool.arguments.length > 0 ? (
          <div>
            <h4 className="text-muted-foreground mb-1 text-[11px] font-semibold uppercase">
              {t('chat.tools.arguments')}
            </h4>
            <ul className="space-y-1">
              {tool.arguments.map((argument) => (
                <li key={argument.name} className="flex flex-wrap gap-1">
                  <span className="font-mono">{argument.name}</span>
                  <span className="text-muted-foreground">({argument.type}</span>
                  {argument.required ? null : (
                    <span className="text-muted-foreground">
                      , {t('chat.tools.optional')}
                    </span>
                  )}
                  <span className="text-muted-foreground">)</span>
                  {argument.description ? (
                    <span className="text-muted-foreground w-full">
                      {argument.description}
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        <div>
          <h4 className="text-muted-foreground text-[11px] font-semibold uppercase">
            {t('chat.tools.response')}
          </h4>
          <p>{tool.response}</p>
        </div>
        <div>
          <h4 className="text-muted-foreground text-[11px] font-semibold uppercase">
            {t('chat.tools.scope')}
          </h4>
          <p>{tool.scope}</p>
        </div>
      </CardContent>
    </Card>
  )
}

export function ToolsDialog({ onClose }: { onClose: () => void }) {
  useCloseFloatings()
  const { t } = useTranslation()
  const catalog = useQuery({ queryKey: ['ai-tools'], queryFn: listAiTools })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-surface border-border flex max-h-[85vh] w-full max-w-lg flex-col rounded-lg border shadow-lg">
        <header className="border-border flex items-center justify-between border-b px-4 py-3">
          <span className="flex items-center gap-2 text-sm font-semibold">
            <Wrench className="size-4" aria-hidden />
            {t('chat.tools.title')}
          </span>
          <Button variant="ghost" size="icon" onClick={onClose} title={t('chat.close')}>
            <X className="size-4" aria-hidden />
          </Button>
        </header>
        <div className="space-y-4 overflow-y-auto p-4">
          {catalog.isPending ? (
            <p className="text-muted-foreground flex items-center gap-2 py-8 text-center text-sm">
              <Loader2 className="size-4 animate-spin" aria-hidden />
              {t('chat.tools.loading')}
            </p>
          ) : null}
          <ErrorBanner
            message={catalog.isError ? (catalog.error as Error).message : null}
          />
          <div className="grid gap-3">
            {(catalog.data ?? []).map((tool) => (
              <ToolCard key={tool.name} tool={tool} />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
