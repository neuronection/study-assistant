import { readFileSync } from 'node:fs'
import path from 'node:path'

const ROOT = path.resolve(process.cwd(), '..')
const STATE_FILE = path.join(ROOT, 'frontend', 'e2e', '.state.json')

interface SeedState {
  provider: boolean
}

const seed: SeedState = { provider: false }

interface RunState {
  baseUrl: string
  mockBaseUrl: string
  /** Cookie header for the e2e service session (bootstrapped in global-setup). */
  serviceCookie: string
  /** Double-submit CSRF token (the nx_csrf cookie value). */
  csrfToken: string
  /** Default profile of the service account (S5: X-Profile-Id required). */
  profileId: string
}

function runState(): RunState {
  return JSON.parse(readFileSync(STATE_FILE, 'utf-8')) as RunState
}

export function baseUrl(): string {
  return runState().baseUrl
}

function mockBaseUrl(): string {
  return runState().mockBaseUrl
}

export function apiUrl(route: string): string {
  return `${baseUrl()}/api/v1${route}`
}

export async function api<T>(verb: string, route: string, body?: unknown): Promise<T> {
  // Session-authenticated like any real client — since S4b enforces a
  // session on every /api/* request, bare fetches get 401. The service
  // session is bootstrapped once in global-setup; unsafe methods also
  // carry the double-submit CSRF token.
  const run = runState()
  const headers: Record<string, string> = {
    Cookie: run.serviceCookie,
    'X-Profile-Id': run.profileId,
  }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (verb !== 'GET' && verb !== 'HEAD') headers['X-CSRF-Token'] = run.csrfToken
  const response = await fetch(apiUrl(route), {
    method: verb,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    throw new Error(`api ${verb} ${route} failed: ${response.status} ${await response.text()}`)
  }
  return (response.status === 204 ? null : response.json()) as Promise<T>
}

export async function seedProvider(): Promise<void> {
  if (seed.provider) return
  const existing = await api<Array<{ id: number }>>('GET', '/providers')
  if (existing.length === 0) {
    await api('POST', '/providers', {
      name: 'Mock provider',
      type: 'openai_compatible',
      base_url: mockBaseUrl(),
      api_key: null,
    })
  }
  const models = await api<Array<{ id: number; external_id: string }>>('GET', '/models')
  if (models.length === 0) throw new Error('mock models missing after provider create')
  for (const model of models) {
    await api('PATCH', `/models/${model.id}`, {
      enabled: true,
      caps: model.external_id === 'mock-embed' ? ['embeddings'] : ['text'],
    })
  }
  const text = models.find((model) => model.external_id === 'mock-text')
  const embed = models.find((model) => model.external_id === 'mock-embed')
  if (!text || !embed) throw new Error('mock model ids not found')
  await api('PUT', '/tasks/defaults/text', { model_id: text.id, fallback_model_id: null })
  await api('PUT', '/tasks/defaults/embeddings', { model_id: embed.id, fallback_model_id: null })
  seed.provider = true
}
