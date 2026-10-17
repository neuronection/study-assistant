import { describe, expect, it } from 'vitest'

import {
  mcpCommandLine,
  mcpConditions,
  mcpGroup,
  mcpInstanceMetadata,
  mcpStatus,
} from './mcpIntegrationViews'
import type { McpServerRow } from '@/lib/api'

const SERVER: McpServerRow = {
  id: 'abc123',
  name: 'coursehub',
  command: 'python',
  args: ['-m', 'coursehub_server'],
  enabled: false,
  timeout_sec: 30,
  transport: 'stdio',
  url: '',
  max_concurrent: 4,
  has_token: true,
  has_env: false,
  tools: [],
  last_error: 'spawn failed',
  refreshed_at: null,
  status: 'degraded',
  last_success_at: '2026-10-10T10:00:00Z',
  consecutive_failures: 2,
  conditions: ['needs-config'],
  declared_contracts: [],
}

describe('mcpIntegrationViews (wire → kit mapping)', () => {
  it('narrows the family status vocabulary, dropping unknown values', () => {
    expect(mcpStatus('degraded')).toBe('degraded')
    expect(mcpStatus('mystery')).toBeNull()
    expect(mcpStatus(undefined)).toBeNull()
  })

  it('keeps only the known conditions', () => {
    expect(mcpConditions(['needs-config', 'mystery'])).toEqual(['needs-config'])
    expect(mcpConditions(null)).toEqual([])
  })

  it('renders the wire line per transport and the instance metadata', () => {
    expect(mcpCommandLine(SERVER)).toBe('python -m coursehub_server')
    expect(
      mcpCommandLine({
        ...SERVER,
        transport: 'http',
        command: '',
        args: [],
        url: 'https://mcp.example.com/mcp',
      }),
    ).toBe('https://mcp.example.com/mcp')
    expect(mcpInstanceMetadata(SERVER)).toEqual({
      transport: 'stdio',
      commandLine: 'python -m coursehub_server',
      hasToken: true,
      hasEnv: false,
      lastError: 'spawn failed',
    })
  })

  it('groups every configured server as an instance of the ONE T3 mcp extension (G1)', () => {
    const group = mcpGroup([
      SERVER,
      { ...SERVER, id: 'def456', name: 'notes-hub', status: 'ok', last_error: null, conditions: [] },
    ])
    expect(group.extension).toMatchObject({
      id: 'mcp',
      originClass: 'bundled',
      tier: 'T3',
      kind: 'connector',
      capabilities: [{ id: 'secrets' }],
    })
    expect(group.instances).toHaveLength(2)
    expect(group.instances[0]).toMatchObject({
      id: 'abc123',
      extensionId: 'mcp',
      name: 'coursehub',
      enabled: false,
      status: 'degraded',
      lastSuccessAt: '2026-10-10T10:00:00Z',
      consecutiveFailures: 2,
      conditions: ['needs-config'],
      tier: 'T3',
    })
    expect(group.instances[0].metadata).toMatchObject({ lastError: 'spawn failed' })
    expect(group.instances[1]).toMatchObject({ id: 'def456', status: 'ok', conditions: [] })
  })
})
