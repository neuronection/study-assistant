import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  Loader2,
  Plus,
  RefreshCw,
  Trash2,
} from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Modal,
  ModalContent,
  ModalDescription,
  ModalHeader,
  ModalTitle,
} from '@neuronection/assistant-ui'
import {
  createMcpServer,
  deleteMcpServer,
  listMcpServers,
  refreshMcpServer,
  updateMcpServer,
  type McpServerRow,
  type McpServerToolInfo,
} from '@/lib/api'

const CONTRACTS = ['none', 'discovery', 'parse'] as const

function AddServerDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [command, setCommand] = useState('')
  const [args, setArgs] = useState('')
  const [error, setError] = useState<string | null>(null)

  const create = useMutation({
    mutationFn: () =>
      createMcpServer({
        name: name.trim(),
        command: command.trim(),
        args: args
          .split(' ')
          .map((arg) => arg.trim())
          .filter((arg) => arg !== ''),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['mcp-servers'] })
      onClose()
    },
    onError: (cause: Error) => setError(cause.message),
  })

  return (
    <Modal open onOpenChange={(next) => !next && onClose()}>
      <ModalContent size="md" closeLabel={t('common.close')}>
        <ModalHeader>
          <ModalTitle className="text-base">{t('mcpConnectors.addTitle')}</ModalTitle>
          <ModalDescription>{t('mcpConnectors.addHint')}</ModalDescription>
        </ModalHeader>
        <form
          className="space-y-3 px-6 pb-6"
          onSubmit={(event) => {
            event.preventDefault()
            create.mutate()
          }}
        >
          <label className="block space-y-1">
            <span className="text-muted-foreground text-xs">{t('mcpConnectors.name')}</span>
            <input
              className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
            />
          </label>
          <label className="block space-y-1">
            <span className="text-muted-foreground text-xs">{t('mcpConnectors.command')}</span>
            <input
              className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm font-mono"
              placeholder="/usr/bin/python -m their_server"
              value={command}
              onChange={(event) => setCommand(event.target.value)}
              required
            />
          </label>
          <label className="block space-y-1">
            <span className="text-muted-foreground text-xs">{t('mcpConnectors.args')}</span>
            <input
              className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm font-mono"
              placeholder="-m their_server --port 8080"
              value={args}
              onChange={(event) => setArgs(event.target.value)}
            />
          </label>
          <p className="text-muted-foreground text-[11px]">{t('mcpConnectors.disabledNote')}</p>
          {error !== null ? (
            <p className="text-destructive text-xs" role="alert">
              {error}
            </p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" size="sm" disabled={create.isPending || !name.trim() || !command.trim()}>
              {create.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
              {t('mcpConnectors.save')}
            </Button>
          </div>
        </form>
      </ModalContent>
    </Modal>
  )
}

function ServerRow({ server }: { server: McpServerRow }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [notice, setNotice] = useState<string | null>(null)

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['mcp-servers'] })
  }

  const toggle = useMutation({
    mutationFn: (enabled: boolean) => updateMcpServer(server.id, { enabled }),
    onSuccess: invalidate,
    onError: (cause: Error) => setNotice(cause.message),
  })

  const refresh = useMutation({
    mutationFn: () => refreshMcpServer(server.id),
    onSuccess: invalidate,
    onError: (cause: Error) => setNotice(cause.message),
  })

  const remove = useMutation({
    mutationFn: () => deleteMcpServer(server.id),
    onSuccess: invalidate,
    onError: (cause: Error) => setNotice(cause.message),
  })

  const setTool = useMutation({
    mutationFn: (patch: {
      name: string
      enabled?: boolean
      contract?: string
      url_pattern?: string
    }) => updateMcpServer(server.id, { tools: [patch] }),
    onSuccess: invalidate,
    onError: (cause: Error) => setNotice(cause.message),
  })

  const commandLine = [server.command, ...server.args].join(' ')

  return (
    <div className="border-border space-y-2 rounded-md border p-2" data-testid="mcp-server-row">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-medium">{server.name}</span>
            {!server.enabled ? (
              <Badge variant="outline">{t('mcpConnectors.off')}</Badge>
            ) : null}
          </div>
          <code className="text-muted-foreground block truncate font-mono text-[11px]">
            {commandLine}
          </code>
          {server.last_error ? (
            <p className="text-warning mt-0.5 flex items-center gap-1 text-[11px]">
              <AlertTriangle className="size-3 shrink-0" aria-hidden />
              {server.last_error}
            </p>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <label className="text-muted-foreground flex items-center gap-1 text-[11px]">
            <input
              type="checkbox"
              checked={server.enabled}
              aria-label={t('mcpConnectors.enabledLabel')}
              onChange={(event) => toggle.mutate(event.target.checked)}
            />
            {t('mcpConnectors.enabledShort')}
          </label>
          <Button
            size="sm"
            variant="ghost"
            disabled={refresh.isPending}
            onClick={() => refresh.mutate()}
            title={t('mcpConnectors.refresh')}
          >
            {refresh.isPending ? (
              <Loader2 className="animate-spin" aria-hidden />
            ) : (
              <RefreshCw aria-hidden />
            )}
            {t('mcpConnectors.refresh')}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="text-destructive"
            onClick={() => remove.mutate()}
            title={t('mcpConnectors.delete')}
          >
            <Trash2 aria-hidden />
          </Button>
        </div>
      </div>
      {server.tools.length > 0 ? (
        <div className="space-y-1">
          {(server.tools as unknown as McpServerToolInfo[]).map((tool) => (
            <div
              key={tool.name}
              className="bg-subtle flex flex-wrap items-center gap-2 rounded-md px-2 py-1"
            >
              <input
                type="checkbox"
                checked={tool.enabled}
                aria-label={`${t('mcpConnectors.toolEnabled')}: ${tool.name}`}
                onChange={(event) =>
                  setTool.mutate({ name: tool.name, enabled: event.target.checked })
                }
              />
              <code className="text-xs font-semibold">{tool.name}</code>
              <select
                className="bg-surface border-border rounded-md border px-1.5 py-0.5 text-[11px]"
                value={tool.contract}
                aria-label={`${t('mcpConnectors.contract')}: ${tool.name}`}
                onChange={(event) =>
                  setTool.mutate({ name: tool.name, contract: event.target.value })
                }
              >
                {CONTRACTS.map((contract) => (
                  <option key={contract} value={contract}>
                    {t(`mcpConnectors.contract_${contract}`)}
                  </option>
                ))}
              </select>
              {tool.contract === 'parse' ? (
                <input
                  className="bg-surface border-border w-44 rounded-md border px-1.5 py-0.5 text-[11px]"
                  placeholder="example.com/learn/*"
                  value={tool.url_pattern ?? ''}
                  aria-label={`${t('mcpConnectors.urlPattern')}: ${tool.name}`}
                  onChange={(event) =>
                    setTool.mutate({
                      name: tool.name,
                      url_pattern: event.target.value,
                    })
                  }
                />
              ) : null}
              {tool.description ? (
                <span className="text-muted-foreground truncate text-[11px]">
                  {String(tool.description)}
                </span>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
      {notice !== null ? (
        <p className="text-destructive text-xs" role="alert">
          {notice}
        </p>
      ) : null}
    </div>
  )
}

export function McpConnectorsCard() {
  const { t } = useTranslation()
  const servers = useQuery({ queryKey: ['mcp-servers'], queryFn: listMcpServers })
  const [adding, setAdding] = useState(false)

  return (
    <Card data-testid="mcp-connectors-card">
      <CardHeader>
        <CardTitle className="text-sm">{t('mcpConnectors.title')}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <p className="text-muted-foreground text-xs">{t('mcpConnectors.hint')}</p>
        <div className="space-y-2" data-testid="mcp-servers-list">
          {(servers.data ?? []).length === 0 ? (
            <p className="text-muted-foreground text-xs">{t('mcpConnectors.empty')}</p>
          ) : null}
          {(servers.data ?? []).map((server) => (
            <ServerRow key={server.id} server={server} />
          ))}
        </div>
        <Button size="sm" variant="outline" onClick={() => setAdding(true)}>
          <Plus aria-hidden />
          {t('mcpConnectors.add')}
        </Button>
      </CardContent>
      {adding ? <AddServerDialog onClose={() => setAdding(false)} /> : null}
    </Card>
  )
}
