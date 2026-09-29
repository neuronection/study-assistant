import type { components } from '@/lib/api-schema'
import { json, apiFetch } from './client'

export type InstanceConfig = components['schemas']['InstanceConfigOut']

/** Public instance facts (`GET /api/v1/instance/config`) — readable
 * without a session so the demo badge renders before login. */
export async function getInstanceConfig(): Promise<InstanceConfig> {
  const response = await apiFetch('/api/v1/instance/config')
  return json<InstanceConfig>(response)
}
