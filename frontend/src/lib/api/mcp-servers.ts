import type { components } from '@/lib/api-schema'
import { apiFetch, json } from './client'

export type McpServerRow = components['schemas']['McpServerOut']

export interface McpServerToolInfo {
  name: string
  description: string
  enabled: boolean
  contract: string
  url_pattern: string | null
}

export async function listMcpServers(): Promise<McpServerRow[]> {
  const response = await apiFetch('/api/v1/mcp/servers')
  return json<McpServerRow[]>(response)
}

export async function createMcpServer(body: {
  name: string
  command: string
  args?: string[]
  timeout_sec?: number
}): Promise<McpServerRow> {
  const response = await apiFetch('/api/v1/mcp/servers', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<McpServerRow>(response)
}

export async function updateMcpServer(
  id: string,
  body: {
    enabled?: boolean
    timeout_sec?: number
    tools?: {
      name: string
      enabled?: boolean
      contract?: string
      url_pattern?: string | null
    }[]
  }
): Promise<McpServerRow> {
  const response = await apiFetch(`/api/v1/mcp/servers/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<McpServerRow>(response)
}

export async function deleteMcpServer(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/mcp/servers/${id}`, { method: 'DELETE' })
  if (!response.ok && response.status !== 204) {
    throw new Error(`delete failed: ${response.status}`)
  }
}

export async function refreshMcpServer(id: number | string): Promise<McpServerRow> {
  const response = await apiFetch(`/api/v1/mcp/servers/${id}/refresh`, {
    method: 'POST',
  })
  return json<McpServerRow>(response)
}
