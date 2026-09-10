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

let activeProfileId: number | null = null

export function setActiveProfile(profileId: number | null): void {
  activeProfileId = profileId
}

export function getActiveProfile(): number | null {
  return activeProfileId
}

export function apiFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  if (activeProfileId !== null) {
    headers.set('X-Profile-Id', String(activeProfileId))
  }
  return fetch(url, { ...init, headers })
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
