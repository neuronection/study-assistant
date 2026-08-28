import { useQuery } from '@tanstack/react-query'
import { Check, Copy, Loader2, ShieldCheck, Terminal } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorBanner } from '@/components/ui/error-banner'
import { listMcpInfo } from '@/lib/api'

export function McpTab() {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  const info = useQuery({ queryKey: ['mcp-info'], queryFn: listMcpInfo })

  const copyCommand = async () => {
    const command = info.data?.command
    if (!command) {
      return
    }
    try {
      await navigator.clipboard.writeText(command)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      // clipboard is best-effort
    }
  }

  return (
    <div className="space-y-4">
      <header>
        <h2 className="text-sm font-medium">{t('settings.mcpTitle')}</h2>
        <p className="text-muted-foreground mt-1 text-xs">{t('settings.mcpHint')}</p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Terminal className="size-4" aria-hidden />
            {t('settings.mcpTitle')}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center gap-2">
            <code className="bg-subtle border-border flex-1 overflow-x-auto rounded-md border px-2 py-1.5 font-mono text-xs">
              {info.data?.command ?? '…'}
            </code>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void copyCommand()}
              disabled={!info.data}
            >
              {copied ? (
                <Check className="size-3.5" aria-hidden />
              ) : (
                <Copy className="size-3.5" aria-hidden />
              )}
              {copied ? t('settings.mcpCopied') : t('settings.mcpCopy')}
            </Button>
          </div>
          <p className="text-muted-foreground flex items-center gap-1.5 text-xs">
            <ShieldCheck className="size-3.5 shrink-0" aria-hidden />
            {t('settings.mcpReadOnly')}
          </p>
        </CardContent>
      </Card>

      {info.isPending ? (
        <p className="text-muted-foreground flex items-center gap-2 text-sm">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          {t('chat.tools.loading')}
        </p>
      ) : null}
      <ErrorBanner message={info.isError ? (info.error as Error).message : null} />

      <section className="space-y-2">
        <h3 className="text-muted-foreground text-[11px] font-semibold uppercase">
          {t('settings.mcpTools')}
        </h3>
        <div className="grid gap-2">
          {(info.data?.tools ?? []).map((tool) => (
            <Card key={tool.name}>
              <CardContent className="py-3">
                <h4 className="font-mono text-xs font-semibold">{tool.name}</h4>
                <p className="text-muted-foreground mt-1 text-xs">{tool.description}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>
    </div>
  )
}
