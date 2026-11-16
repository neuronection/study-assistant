import { apiFetch } from './api/client'
import {
  forgetSessionScope,
  getLastSessionScope,
  rememberSessionScope,
} from './session-scope'

export const AUDIO_CACHE_PREFIX = 'sa-audio-offline-v1'
export const AUDIO_STATE_PREFIX = 'sa-audio-state'

export type OfflineAudioState = 'unknown' | 'cached' | 'not-cached'

export interface AudioCacheDiagnostics {
  supported: boolean
  scopes: string[]
  lastError: string | null
}

let lastCacheError: string | null = null

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function recordError(error: unknown): void {
  lastCacheError = errorMessage(error)
}

export function getLastAudioCacheError(): string | null {
  return lastCacheError
}

export function offlineAudioSupported(): boolean {
  return typeof caches !== 'undefined'
}

export function audioCacheName(scope: string): string {
  return `${AUDIO_CACHE_PREFIX}:${scope}`
}

export function audioStateKey(scope: string): string {
  return `${AUDIO_STATE_PREFIX}:${scope}`
}

async function openCache(scope: string): Promise<Cache | null> {
  if (!offlineAudioSupported()) {
    return null
  }
  try {
    return await caches.open(audioCacheName(scope))
  } catch (error) {
    recordError(error)
    return null
  }
}

async function openExistingCache(scope: string): Promise<Cache | null> {
  if (!offlineAudioSupported()) {
    return null
  }
  try {
    if (!(await caches.has(audioCacheName(scope)))) {
      return null
    }
    return await caches.open(audioCacheName(scope))
  } catch (error) {
    recordError(error)
    return null
  }
}

export async function readCachedAudio(
  scope: string,
  src: string,
): Promise<Blob | null> {
  const cache = await openExistingCache(scope)
  if (cache === null) {
    return null
  }
  try {
    const response = await cache.match(src)
    return response === undefined ? null : await response.blob()
  } catch (error) {
    recordError(error)
    return null
  }
}

/** Download through the app's authenticated fetch path. `cache.add(src)`
 * bypasses `X-Profile-Id`/CSRF and can fetch the wrong scope or fail on a
 * protected API URL, so the response is fetched with `apiFetch` and stored
 * explicitly. */
export async function cacheAudio(scope: string, src: string): Promise<boolean> {
  const cache = await openCache(scope)
  if (cache === null) {
    return false
  }
  try {
    const response = await apiFetch(src)
    if (!response.ok) {
      lastCacheError = `download failed (${response.status})`
      return false
    }
    await cache.put(src, response.clone())
    lastCacheError = null
    return true
  } catch (error) {
    recordError(error)
    return false
  }
}

export async function removeCachedAudio(
  scope: string,
  src: string,
): Promise<boolean> {
  const cache = await openExistingCache(scope)
  if (cache === null) {
    return false
  }
  try {
    return await cache.delete(src)
  } catch (error) {
    recordError(error)
    return false
  }
}

/** Logout/session-loss cleanup: the scoped Cache Storage namespace and the
 * scoped persisted player state. Durable data (blobs, database rows) is
 * never touched. Profile switches deliberately do not call this. */
export async function purgeSessionScope(scope: string): Promise<boolean> {
  let ok = true
  if (offlineAudioSupported()) {
    try {
      await caches.delete(audioCacheName(scope))
    } catch (error) {
      recordError(error)
      ok = false
    }
  }
  try {
    window.localStorage.removeItem(audioStateKey(scope))
  } catch (error) {
    recordError(error)
    ok = false
  }
  return ok
}

/** The one storage cleanup used by every session-loss path. Captures the
 * last resolved scope synchronously so callers may clear the user first. */
export async function purgeLastSessionScope(): Promise<boolean> {
  const scope = getLastSessionScope()
  forgetSessionScope(scope)
  if (scope === null) {
    return true
  }
  return purgeSessionScope(scope)
}

export async function listAudioCacheScopes(): Promise<string[]> {
  if (!offlineAudioSupported()) {
    return []
  }
  try {
    const names = await caches.keys()
    const prefix = `${AUDIO_CACHE_PREFIX}:`
    return names
      .filter((name) => name.startsWith(prefix))
      .map((name) => name.slice(prefix.length))
      .sort()
  } catch (error) {
    recordError(error)
    return []
  }
}

/** Developer diagnostics/clear: removes every scoped audio cache and its
 * persisted state, including scopes of other profiles on this browser. */
export async function clearAllScopedAudioCaches(): Promise<boolean> {
  let ok = true
  if (offlineAudioSupported()) {
    try {
      const names = await caches.keys()
      const prefix = `${AUDIO_CACHE_PREFIX}:`
      await Promise.all(
        names
          .filter((name) => name.startsWith(prefix))
          .map((name) => caches.delete(name)),
      )
    } catch (error) {
      recordError(error)
      ok = false
    }
  }
  try {
    const keys: string[] = []
    for (let index = 0; index < window.localStorage.length; index += 1) {
      const key = window.localStorage.key(index)
      if (key !== null && key.startsWith(`${AUDIO_STATE_PREFIX}:`)) {
        keys.push(key)
      }
    }
    for (const key of keys) {
      window.localStorage.removeItem(key)
    }
  } catch (error) {
    recordError(error)
    ok = false
  }
  if (ok) {
    lastCacheError = null
  }
  return ok
}

export async function getAudioCacheDiagnostics(): Promise<AudioCacheDiagnostics> {
  return {
    supported: offlineAudioSupported(),
    scopes: await listAudioCacheScopes(),
    lastError: getLastAudioCacheError(),
  }
}

/** A resolved scope is remembered for later session-loss cleanup. A
 * transient `null` (profile list still loading, web-mode reconciliation
 * between two selections) is not a session loss and must never purge a
 * scope's downloads; logout/401/account deletion call
 * `purgeLastSessionScope` explicitly. */
export function applySessionScopeChange(next: string | null): void {
  if (next !== null) {
    rememberSessionScope(next)
  }
}
