export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(message: string, status: number, detail?: unknown) {
    super(message)
    this.status = status
    this.detail = detail
  }
}

export interface UnsupportedTypeDetail {
  reason: 'unsupported_type'
  suffix: string
  accepted: string[]
}

export function unsupportedTypeDetail(detail: unknown): UnsupportedTypeDetail | null {
  if (
    detail !== null &&
    typeof detail === 'object' &&
    !Array.isArray(detail) &&
    (detail as { reason?: unknown }).reason === 'unsupported_type'
  ) {
    return detail as UnsupportedTypeDetail
  }
  return null
}

export function apiDetailMessage(detail: unknown): string | null {
  if (typeof detail === 'string') {
    return detail.trim() ? detail : null
  }
  if (Array.isArray(detail)) {
    const parts = detail
      .map((entry) => {
        if (entry === null || typeof entry !== 'object') {
          return String(entry)
        }
        const record = entry as { loc?: unknown; msg?: unknown }
        const loc = Array.isArray(record.loc)
          ? record.loc.filter((part) => part !== 'body').join('.')
          : ''
        const msg =
          typeof record.msg === 'string' ? record.msg : String(record.msg ?? '')
        return loc ? `${loc}: ${msg}` : msg
      })
      .filter((part) => part.length > 0)
    return parts.length > 0 ? parts.join('; ') : null
  }
  if (detail !== null && detail !== undefined) {
    return String(detail)
  }
  return null
}

export async function json<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: unknown } | null
    throw new ApiError(
      apiDetailMessage(body?.detail) ?? `request failed: ${response.status}`,
      response.status,
      body?.detail,
    )
  }
  return (await response.json()) as T
}

export async function expectOk(response: Response): Promise<void> {
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: unknown } | null
    throw new ApiError(
      apiDetailMessage(body?.detail) ?? `request failed: ${response.status}`,
      response.status,
      body?.detail,
    )
  }
}

let activeProfileId: string | null = null

// §15 boot gate — the shell's first render wave fires profile-scoped
// queries before the active profile is settled (localStorage restore +
// web-mode Default adoption), and in server identity mode those would
// all 400 ("X-Profile-Id required"). Profile-scoped requests therefore
// wait on `markProfileSettled`, which AppShell calls once the selection
// is decided. Exempt prefixes mirror the backend's
// PROFILE_BIND_EXEMPT_PREFIXES (main.py) so auth/instance/profile
// traffic is never blocked.
let profileSettled = false
let profileWaiters: Array<() => void> = []

export function markProfileSettled(): void {
  if (profileSettled) {
    return
  }
  profileSettled = true
  for (const resolve of profileWaiters.splice(0)) {
    resolve()
  }
}

/** Test seam — the settled state is process-wide module state. */
export function resetProfileGateForTests(): void {
  profileSettled = false
  profileWaiters = []
}

const PROFILE_EXEMPT_PREFIXES: readonly string[] = [
  '/api/v1/auth',
  '/api/v1/me',
  '/api/v1/profiles',
  '/api/v1/admin',
  '/api/v1/health',
  '/api/v1/instance',
  '/api/v1/desktop',
  '/api/v1/shell',
  '/api/docs',
]

function needsProfileGate(url: string): boolean {
  if (profileSettled || !url.startsWith('/api/')) {
    return false
  }
  return !PROFILE_EXEMPT_PREFIXES.some((prefix) => url.startsWith(prefix))
}

let shellToken: string | null = null
try {
  const fromUrl = new URLSearchParams(window.location.search).get('shell')
  if (fromUrl) sessionStorage.setItem('nx_shell', fromUrl)
  shellToken = fromUrl ?? sessionStorage.getItem('nx_shell')
} catch {
  shellToken = null
}

/** Fired when a request cannot be authenticated even after a refresh
 * attempt — the AuthGate listens and drops back to the login screen. */
export const UNAUTHENTICATED_EVENT = 'nx:unauthenticated'

export function hasShellToken(): boolean {
  return shellToken !== null
}

function cookieValue(name: string): string | null {
  const prefix = `${name}=`
  const match = document.cookie.split('; ').find((part) => part.startsWith(prefix))
  return match ? decodeURIComponent(match.slice(prefix.length)) : null
}

export function setActiveProfile(profileId: string | null): void {
  activeProfileId = profileId
}

export function getActiveProfile(): string | null {
  return activeProfileId
}

async function rawFetch(url: string, init: RequestInit): Promise<Response> {
  if (needsProfileGate(url)) {
    await new Promise<void>((resolve) => {
      profileWaiters.push(resolve)
    })
  }
  const headers = new Headers(init.headers)
  if (activeProfileId !== null) {
    headers.set('X-Profile-Id', activeProfileId)
  }
  if (shellToken !== null && !headers.has('X-Shell-Token')) {
    headers.set('X-Shell-Token', shellToken)
  }
  const csrf = cookieValue('nx_csrf')
  if (csrf !== null && !headers.has('X-CSRF-Token')) {
    headers.set('X-CSRF-Token', csrf)
  }
  return fetch(url, { ...init, headers })
}

let refreshInFlight: Promise<boolean> | null = null

/** Rotate the refresh cookie once (deduplicated) — true when a new
 * session was established. */
export function tryRefreshSession(): Promise<boolean> {
  if (refreshInFlight === null) {
    refreshInFlight = rawFetch('/api/v1/auth/refresh', { method: 'POST' })
      .then((response) => response.ok)
      .catch(() => false)
      .finally(() => {
        refreshInFlight = null
      })
  }
  return refreshInFlight
}

export async function apiFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const response = await rawFetch(url, init)
  if (response.status !== 401 || url.startsWith('/api/v1/auth/')) {
    return response
  }
  // Expired access with a live refresh cookie: rotate + retry once,
  // silently. Otherwise tell the world the session is gone.
  if (await tryRefreshSession()) {
    const retried = await rawFetch(url, init)
    if (retried.status !== 401) {
      return retried
    }
    window.dispatchEvent(new Event(UNAUTHENTICATED_EVENT))
    return retried
  }
  window.dispatchEvent(new Event(UNAUTHENTICATED_EVENT))
  return response
}

export function blobUrl(sha: string): string {
  return `/api/v1/blobs/${sha}`
}

export function audioFilename(blob: Blob): string {
  if (blob.type.includes('mp4')) return 'dictation.m4a'
  if (blob.type.includes('ogg')) return 'dictation.ogg'
  if (blob.type.includes('wav')) return 'dictation.wav'
  return 'dictation.webm'
}
