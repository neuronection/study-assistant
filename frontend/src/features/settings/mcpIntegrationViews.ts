import type {
  IntegrationConditionId,
  IntegrationExtensionGroupView,
} from '@neuronection/assistant-ui/integration-contracts'
import { isExtensionStatusState } from '@neuronection/assistant-ui/integration-atoms'
import type { ExtensionStatusState } from '@neuronection/assistant-ui/integration-contracts'
import type { McpServerRow } from '@/lib/api'

/**
 * Pure wire → kit view-model mapping (plan 33 Phase D — desktop's
 * integration-views precedent): study's MCP server rows surface as D19
 * instances of the bundled `mcp` extension (T3 — the user-configured servers
 * run as external processes, hence the verbatim perimeter disclosure the
 * settings card renders). No fetching, no state — mapping only.
 */

export const MCP_EXTENSION_ID = 'mcp'

export type McpInstanceMetadata = {
  transport: string
  commandLine: string
  hasToken: boolean
  hasEnv: boolean
  lastError: string | null
}

export function mcpStatus(status: string | null | undefined): ExtensionStatusState | null {
  return status && isExtensionStatusState(status) ? status : null
}

export function mcpConditions(conditions: string[] | null | undefined): IntegrationConditionId[] {
  return (conditions ?? []).filter(
    (condition): condition is IntegrationConditionId =>
      condition === 'needs-config' || condition === 'needs-secret',
  )
}

export function mcpCommandLine(server: McpServerRow): string {
  return server.transport === 'stdio'
    ? [server.command, ...server.args].join(' ')
    : server.url
}

export function mcpInstanceMetadata(server: McpServerRow): McpInstanceMetadata {
  return {
    transport: server.transport,
    commandLine: mcpCommandLine(server),
    hasToken: server.has_token,
    hasEnv: server.has_env,
    lastError: server.last_error ?? null,
  }
}

/** All configured servers as instances of the ONE `mcp` extension (G1). */
export function mcpGroup(servers: McpServerRow[]): IntegrationExtensionGroupView {
  return {
    extension: {
      id: MCP_EXTENSION_ID,
      name: 'mcp',
      originClass: 'bundled',
      tier: 'T3',
      kind: 'connector',
      capabilities: [{ id: 'secrets' }],
      summary: null,
      provenance: null,
      digest: null,
      update: null,
    },
    instances: servers.map((server) => ({
      id: server.id,
      extensionId: MCP_EXTENSION_ID,
      name: server.name,
      enabled: server.enabled,
      status: mcpStatus(server.status),
      lastSuccessAt: server.last_success_at ?? null,
      consecutiveFailures: server.consecutive_failures ?? null,
      conditions: mcpConditions(server.conditions),
      originClass: 'bundled',
      tier: 'T3',
      metadata: mcpInstanceMetadata(server),
    })),
  }
}
