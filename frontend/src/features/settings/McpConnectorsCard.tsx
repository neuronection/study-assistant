import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  KeyRound,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
} from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Modal,
  ModalContent,
  ModalDescription,
  ModalHeader,
  ModalTitle,
} from '@neuronection/assistant-ui'
import { IntegrationInstancesList } from '@neuronection/assistant-ui/integration-instances-list'
import type { IntegrationInstanceView } from '@neuronection/assistant-ui/integration-contracts'
import {
  createMcpServer,
  deleteMcpServer,
  getMcpCharter,
  listMcpServers,
  refreshMcpServer,
  updateMcpServer,
  type McpServerRow,
  type McpServerToolInfo,
} from '@/lib/api'
import { mcpGroup, mcpInstanceMetadata } from './mcpIntegrationViews'
import { ExtensionDocsButton } from './ExtensionDocsButton'

const CONTRACTS = ['none', 'discovery', 'parse'] as const

function parseEnvText(text: string): Record<string, string> | null | 'invalid' {
  const trimmed = text.trim()
  if (!trimmed) {
    return null
  }
  try {
    const parsed: unknown = JSON.parse(trimmed)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      return 'invalid'
    }
    return Object.fromEntries(
      Object.entries(parsed as Record<string, unknown>).map(([key, value]) => [
        key,
        String(value),
      ]),
    )
  } catch {
    return 'invalid'
  }
}

interface ServerDialogProps {
  server: McpServerRow | null
  onClose: () => void
}

function ServerDialog({ server, onClose }: ServerDialogProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [name, setName] = useState(server?.name ?? '')
  const [transport, setTransport] = useState<string>(server?.transport ?? 'stdio')
  const [command, setCommand] = useState(server?.command ?? '')
  const [args, setArgs] = useState((server?.args ?? []).join(' '))
  const [url, setUrl] = useState(server?.url ?? '')
  const [token, setToken] = useState('')
  const [envText, setEnvText] = useState('')
  const [clearToken, setClearToken] = useState(false)
  const [clearEnv, setClearEnv] = useState(false)
  const [timeoutSec, setTimeoutSec] = useState(String(server?.timeout_sec ?? 30))
  const [maxConcurrent, setMaxConcurrent] = useState(
    String(server?.max_concurrent ?? 4),
  )
  const [error, setError] = useState<string | null>(null)

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['mcp-servers'] })
  }

  const save = useMutation({
    mutationFn: async () => {
      const parsedEnv = transport === 'stdio' ? parseEnvText(envText) : null
      if (parsedEnv === 'invalid') {
        throw new Error(t('mcpConnectors.envInvalid'))
      }
      if (server === null) {
        const base = {
          name: name.trim(),
          timeout_sec: Number(timeoutSec) || 30,
          transport,
          url: url.trim(),
          max_concurrent: Number(maxConcurrent) || 4,
          token: token.trim() || null,
          env: parsedEnv,
        }
        if (transport !== 'stdio') {
          return createMcpServer(base)
        }
        return createMcpServer({
          ...base,
          command: command.trim(),
          args: args
            .split(' ')
            .map((arg) => arg.trim())
            .filter((arg) => arg !== ''),
        })
      }
      const patch: Record<string, unknown> = {
        name: name.trim(),
        timeout_sec: Number(timeoutSec) || 30,
        transport,
        url: url.trim(),
        max_concurrent: Number(maxConcurrent) || 4,
      }
      if (transport === 'stdio') {
        patch.command = command.trim()
        patch.args = args
          .split(' ')
          .map((arg) => arg.trim())
          .filter((arg) => arg !== '')
      }
      if (token.trim()) {
        patch.token = token.trim()
      } else if (clearToken) {
        patch.token = null
      }
      if (envText.trim() && transport === 'stdio') {
        patch.env = parsedEnv
      } else if (clearEnv) {
        patch.env = null
      }
      return updateMcpServer(server.id, patch)
    },
    onSuccess: invalidate,
    onError: (cause: Error) => setError(cause.message),
  })

  const envParsed = transport === 'stdio' ? parseEnvText(envText) : null
  const validationError =
    !name.trim()
      ? t('mcpConnectors.nameRequired')
      : transport === 'stdio' && !command.trim()
        ? t('mcpConnectors.commandRequired')
        : transport !== 'stdio' && !url.trim()
          ? t('mcpConnectors.urlRequired')
          : envParsed === 'invalid'
            ? t('mcpConnectors.envInvalid')
            : null

  return (
    <Modal open onOpenChange={(next) => !next && onClose()}>
      <ModalContent size="md" closeLabel={t('common.close')}>
        <ModalHeader>
          <ModalTitle className="text-base">
            {server === null
              ? t('mcpConnectors.addTitle')
              : t('mcpConnectors.editTitle')}
          </ModalTitle>
          <ModalDescription>{t('mcpConnectors.addHint')}</ModalDescription>
        </ModalHeader>
        <form
          className="space-y-3 px-6 pb-6"
          onSubmit={(event) => {
            event.preventDefault()
            if (validationError) {
              setError(validationError)
              return
            }
            setError(null)
            save.mutate()
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
            <span className="text-muted-foreground text-xs">{t('mcpConnectors.transport')}</span>
            <select
              className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
              value={transport}
              onChange={(event) => setTransport(event.target.value)}
            >
              <option value="stdio">{t('mcpConnectors.transport_stdio')}</option>
              <option value="http">{t('mcpConnectors.transport_http')}</option>
              <option value="sse">{t('mcpConnectors.transport_sse')}</option>
            </select>
          </label>
          {transport === 'stdio' ? (
            <>
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
            </>
          ) : (
            <label className="block space-y-1">
              <span className="text-muted-foreground text-xs">{t('mcpConnectors.url')}</span>
              <input
                className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm font-mono"
                placeholder="http://host:port/mcp"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                required
              />
            </label>
          )}
          {server !== null && (server.has_token || server.has_env) ? (
            <div className="text-muted-foreground flex items-center gap-1.5 text-[11px]">
              <KeyRound className="size-3 shrink-0" aria-hidden />
              {server.has_token ? t('mcpConnectors.tokenStored') : null}
              {server.has_token && server.has_env ? ' · ' : null}
              {server.has_env ? t('mcpConnectors.envStored') : null}
            </div>
          ) : null}
          <label className="block space-y-1">
            <span className="text-muted-foreground text-xs">{t('mcpConnectors.token')}</span>
            <input
              type="password"
              className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
              placeholder={server?.has_token ? t('mcpConnectors.tokenKeep') : undefined}
              value={token}
              onChange={(event) => setToken(event.target.value)}
            />
          </label>
          {server !== null && server.has_token ? (
            <label className="text-muted-foreground flex items-center gap-2 text-[11px]">
              <input
                type="checkbox"
                checked={clearToken}
                onChange={(event) => setClearToken(event.target.checked)}
              />
              {t('mcpConnectors.clearToken')}
            </label>
          ) : null}
          {transport === 'stdio' ? (
            <>
              <label className="block space-y-1">
                <span className="text-muted-foreground text-xs">{t('mcpConnectors.env')}</span>
                <textarea
                  rows={2}
                  className="bg-surface border-border w-full rounded-md border px-3 py-2 font-mono text-xs"
                  placeholder='{"KEY": "value"}'
                  value={envText}
                  onChange={(event) => setEnvText(event.target.value)}
                />
              </label>
              {server !== null && server.has_env && !envText.trim() ? (
                <label className="text-muted-foreground flex items-center gap-2 text-[11px]">
                  <input
                    type="checkbox"
                    checked={clearEnv}
                    onChange={(event) => setClearEnv(event.target.checked)}
                  />
                  {t('mcpConnectors.clearEnv')}
                </label>
              ) : null}
            </>
          ) : null}
          <div className="flex gap-2">
            <label className="block flex-1 space-y-1">
              <span className="text-muted-foreground text-xs">{t('mcpConnectors.timeout')}</span>
              <input
                type="number"
                min={5}
                max={120}
                className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
                value={timeoutSec}
                onChange={(event) => setTimeoutSec(event.target.value)}
              />
            </label>
            <label className="block flex-1 space-y-1">
              <span className="text-muted-foreground text-xs">
                {t('mcpConnectors.maxConcurrent')}
              </span>
              <input
                type="number"
                min={1}
                max={8}
                className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
                value={maxConcurrent}
                onChange={(event) => setMaxConcurrent(event.target.value)}
              />
            </label>
          </div>
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
            <Button
              type="submit"
              size="sm"
              disabled={save.isPending || !name.trim()}
            >
              {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
              {t('mcpConnectors.save')}
            </Button>
          </div>
        </form>
      </ModalContent>
    </Modal>
  )
}

/** Per-instance kit action slot: the app-owned refresh domain action plus
 * the wire line, sealed-credential chips and the last error (study-domain
 * detail the kit rows carry via instance metadata). */
function McpInstanceActions({
  server,
  onEdit,
  onError,
}: {
  server: McpServerRow
  onEdit: () => void
  onError: (message: string) => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const refresh = useMutation({
    mutationFn: () => refreshMcpServer(server.id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['mcp-servers'] })
    },
    onError: (cause: Error) => onError(cause.message),
  })

  const meta = mcpInstanceMetadata(server)

  return (
    <span className="flex flex-wrap items-center gap-2">
      <code
        className="text-muted-foreground max-w-56 truncate font-mono text-[11px]"
        data-testid={`mcp-server-command-${server.id}`}
      >
        {meta.commandLine}
      </code>
      {meta.hasToken || meta.hasEnv ? (
        <span className="text-muted-foreground flex items-center gap-1 text-[11px]">
          <KeyRound className="size-3 shrink-0" aria-hidden />
          {meta.hasToken ? t('mcpConnectors.tokenStored') : null}
          {meta.hasToken && meta.hasEnv ? ' · ' : null}
          {meta.hasEnv ? t('mcpConnectors.envStored') : null}
        </span>
      ) : null}
      {meta.lastError ? (
        <span className="text-warning flex items-center gap-1 text-[11px]">
          <AlertTriangle className="size-3 shrink-0" aria-hidden />
          {meta.lastError}
        </span>
      ) : null}
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
      <Button size="sm" variant="ghost" onClick={onEdit} title={t('mcpConnectors.edit')}>
        <Pencil aria-hidden />
        {t('mcpConnectors.edit')}
      </Button>
    </span>
  )
}

/** Study-domain tool-contract editor (discovery | parse | none) — the kit's
 * instance rows have no per-tool channel; this stays app content under the
 * list, one section per server that declares tools. */
function McpToolContracts({ server }: { server: McpServerRow }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [notice, setNotice] = useState<string | null>(null)

  const setTool = useMutation({
    mutationFn: (patch: {
      name: string
      enabled?: boolean
      contract?: string
      url_pattern?: string
    }) => updateMcpServer(server.id, { tools: [patch] }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['mcp-servers'] })
    },
    onError: (cause: Error) => setNotice(cause.message),
  })

  if (server.tools.length === 0) return null

  return (
    <div className="border-border space-y-1 rounded-md border p-2" data-testid={`mcp-server-tools-${server.id}`}>
      <p className="text-muted-foreground text-[11px] font-semibold">
        {t('mcpConnectors.toolsTitle')}: {server.name}
      </p>
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
  const queryClient = useQueryClient()
  const servers = useQuery({ queryKey: ['mcp-servers'], queryFn: listMcpServers })
  const charter = useQuery({ queryKey: ['mcp-charter'], queryFn: getMcpCharter })
  const [dialog, setDialog] = useState<'closed' | 'new' | McpServerRow>('closed')
  const [notice, setNotice] = useState<string | null>(null)

  const rows = servers.data ?? []

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['mcp-servers'] })
  }

  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      updateMcpServer(id, { enabled }),
    onSuccess: invalidate,
    onError: (cause: Error) => setNotice(cause.message),
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteMcpServer(id),
    onSuccess: invalidate,
    onError: (cause: Error) => setNotice(cause.message),
  })

  return (
    <Card data-testid="mcp-connectors-card">
      <CardHeader>
        <CardTitle className="text-sm flex items-center gap-2">
          {t('mcpConnectors.title')}
          <span className="ml-auto">
            <ExtensionDocsButton extensionId="mcp" />
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <p className="text-muted-foreground text-xs">{t('mcpConnectors.hint')}</p>
        {charter.data ? (
          <div className="bg-subtle rounded-md p-2" data-testid="mcp-t3-disclosure">
            <p className="flex items-center gap-1 text-[11px] font-semibold">
              <AlertTriangle className="size-3 shrink-0" aria-hidden />
              {t('mcpConnectors.t3Disclosure')}
            </p>
            <p className="text-muted-foreground mt-1 text-[11px]">
              {charter.data.t3_perimeter_disclosure}
            </p>
          </div>
        ) : null}
        <div data-testid="mcp-servers-list">
          <IntegrationInstancesList
            groups={rows.length > 0 ? [mcpGroup(rows)] : []}
            busy={toggle.isPending || remove.isPending}
            error={notice}
            labels={{
              emptyLabel: t('mcpConnectors.empty'),
              enableAriaLabel: t('mcpConnectors.enabledLabel'),
              tombstoneLabel: t('mcpConnectors.delete'),
              lastSuccessLabel: t('mcpConnectors.lastSuccess'),
              failuresLabel: t('mcpConnectors.failures'),
              conditionLabels: {
                'needs-config': t('mcpConnectors.needsConfig'),
                'needs-secret': t('mcpConnectors.needsSecret'),
              },
              statusLabels: {
                ok: t('mcpConnectors.status_ok'),
                degraded: t('mcpConnectors.status_degraded'),
                failing: t('mcpConnectors.status_failing'),
                stale: t('mcpConnectors.status_stale'),
              },
            }}
            onToggleEnabled={(instance: IntegrationInstanceView, enabled) =>
              toggle.mutate({ id: instance.id, enabled })
            }
            onTombstone={(instance: IntegrationInstanceView) => remove.mutate(instance.id)}
            renderInstanceActions={(instance: IntegrationInstanceView) => {
              const server = rows.find((row) => row.id === instance.id)
              if (!server) return null
              return (
                <McpInstanceActions
                  server={server}
                  onEdit={() => setDialog(server)}
                  onError={setNotice}
                />
              )
            }}
          />
        </div>
        {rows.some((server) => server.tools.length > 0) ? (
          <div className="space-y-2">
            {rows
              .filter((server) => server.tools.length > 0)
              .map((server) => (
                <McpToolContracts key={server.id} server={server} />
              ))}
          </div>
        ) : null}
        <Button size="sm" variant="outline" onClick={() => setDialog('new')}>
          <Plus aria-hidden />
          {t('mcpConnectors.add')}
        </Button>
      </CardContent>
      {dialog !== 'closed' ? (
        <ServerDialog
          server={dialog === 'new' ? null : dialog}
          onClose={() => setDialog('closed')}
        />
      ) : null}
    </Card>
  )
}
