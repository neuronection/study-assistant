import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { installFakeCaches } from '@/test/caches'

import {
  applySessionScopeChange,
  audioCacheName,
  audioStateKey,
  cacheAudio,
  clearAllScopedAudioCaches,
  getAudioCacheDiagnostics,
  getLastAudioCacheError,
  purgeSessionScope,
  purgeLastSessionScope,
  readCachedAudio,
  removeCachedAudio,
} from './audio-offline'
import { getLastSessionScope, rememberSessionScope, resetSessionScopeForTests } from './session-scope'

const { apiFetch } = vi.hoisted(() => ({ apiFetch: vi.fn() }))

vi.mock('./api/client', () => ({ apiFetch }))

const SCOPE_A = 'u:user-1:p:profile-a'
const SCOPE_B = 'u:user-1:p:profile-b'
const SRC = '/api/v1/blobs/abc'

describe('audio-offline', () => {
  beforeEach(() => {
    resetSessionScopeForTests()
    apiFetch.mockReset()
    window.localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  test('cache names are scoped per user and profile', () => {
    expect(audioCacheName(SCOPE_A)).toBe(`sa-audio-offline-v1:${SCOPE_A}`)
    expect(audioCacheName(SCOPE_A)).not.toBe(audioCacheName(SCOPE_B))
    expect(audioStateKey(SCOPE_A)).not.toBe(audioStateKey(SCOPE_B))
  })

  test('downloads through apiFetch and cache.put, never cache.add', async () => {
    const storage = installFakeCaches()
    apiFetch.mockResolvedValue(
      new Response(new Blob(['audio-bytes'], { type: 'audio/webm' })),
    )

    expect(await cacheAudio(SCOPE_A, SRC)).toBe(true)
    expect(apiFetch).toHaveBeenCalledWith(SRC)
    const cache = storage.cache(audioCacheName(SCOPE_A))
    expect(cache?.put).toHaveBeenCalled()
    expect(cache?.add).not.toHaveBeenCalled()
    expect(await readCachedAudio(SCOPE_A, SRC)).not.toBeNull()
  })

  test('cached bytes are never served to another scope', async () => {
    installFakeCaches()
    apiFetch.mockResolvedValue(new Response(new Blob(['audio-bytes'])))

    expect(await cacheAudio(SCOPE_A, SRC)).toBe(true)
    expect(await readCachedAudio(SCOPE_A, SRC)).not.toBeNull()
    expect(await readCachedAudio(SCOPE_B, SRC)).toBeNull()
  })

  test('reading an uncached scope does not create a cache namespace', async () => {
    installFakeCaches()
    expect(await readCachedAudio(SCOPE_A, SRC)).toBeNull()
    expect(await caches.keys()).toEqual([])
  })

  test('a failed download is not cached', async () => {
    const storage = installFakeCaches()
    apiFetch.mockResolvedValue(new Response(null, { status: 401 }))

    expect(await cacheAudio(SCOPE_A, SRC)).toBe(false)
    expect(storage.cache(audioCacheName(SCOPE_A))?.put).not.toHaveBeenCalled()
  })

  test('removeDownload only deletes the current scope entry', async () => {
    const storage = installFakeCaches()
    await storage.seed(audioCacheName(SCOPE_A), SRC, new Blob(['a']))
    await storage.seed(audioCacheName(SCOPE_B), SRC, new Blob(['b']))

    expect(await removeCachedAudio(SCOPE_A, SRC)).toBe(true)
    expect(await readCachedAudio(SCOPE_A, SRC)).toBeNull()
    expect(await readCachedAudio(SCOPE_B, SRC)).not.toBeNull()
  })

  test('session loss purges the last scope only', async () => {
    const storage = installFakeCaches()
    await storage.open(audioCacheName(SCOPE_A))
    await storage.open(audioCacheName(SCOPE_B))
    window.localStorage.setItem(audioStateKey(SCOPE_A), 'state-a')
    window.localStorage.setItem(audioStateKey(SCOPE_B), 'state-b')
    rememberSessionScope(SCOPE_A)

    expect(await purgeLastSessionScope()).toBe(true)
    expect(await caches.keys()).not.toContain(audioCacheName(SCOPE_A))
    expect(await caches.keys()).toContain(audioCacheName(SCOPE_B))
    expect(window.localStorage.getItem(audioStateKey(SCOPE_A))).toBeNull()
    expect(window.localStorage.getItem(audioStateKey(SCOPE_B))).toBe('state-b')
    expect(getLastSessionScope()).toBeNull()
  })

  test('a transient null scope never purges explicit downloads', async () => {
    const storage = installFakeCaches()
    await storage.open(audioCacheName(SCOPE_A))

    applySessionScopeChange(SCOPE_A)
    applySessionScopeChange(null)

    expect(await caches.keys()).toContain(audioCacheName(SCOPE_A))
    expect(getLastSessionScope()).toBe(SCOPE_A)
  })

  test('explicit scope purge leaves other scopes intact', async () => {
    const storage = installFakeCaches()
    await storage.open(audioCacheName(SCOPE_A))
    await storage.open(audioCacheName(SCOPE_B))

    expect(await purgeSessionScope(SCOPE_A)).toBe(true)
    expect(await caches.keys()).not.toContain(audioCacheName(SCOPE_A))
    expect(await caches.keys()).toContain(audioCacheName(SCOPE_B))
  })

  test('developer diagnostics lists scopes and clears every scoped cache', async () => {
    const storage = installFakeCaches()
    await storage.open(audioCacheName(SCOPE_A))
    await storage.open(audioCacheName(SCOPE_B))
    window.localStorage.setItem(audioStateKey(SCOPE_A), 'state-a')
    window.localStorage.setItem('sa-unrelated', 'keep')

    const diagnostics = await getAudioCacheDiagnostics()
    expect(diagnostics.supported).toBe(true)
    expect(diagnostics.scopes).toEqual([SCOPE_A, SCOPE_B])

    expect(await clearAllScopedAudioCaches()).toBe(true)
    expect(await caches.keys()).toEqual([])
    expect(window.localStorage.getItem(audioStateKey(SCOPE_A))).toBeNull()
    expect(window.localStorage.getItem('sa-unrelated')).toBe('keep')
  })

  test('a successful developer clear resets the last cache error', async () => {
    installFakeCaches()
    apiFetch.mockResolvedValue(new Response(null, { status: 401 }))
    expect(await cacheAudio(SCOPE_A, SRC)).toBe(false)
    expect(getLastAudioCacheError()).toBe('download failed (401)')

    expect(await clearAllScopedAudioCaches()).toBe(true)
    expect(getLastAudioCacheError()).toBeNull()
  })

  test('unsupported browsers report no cache support and stay inert', async () => {
    vi.stubGlobal('caches', undefined)
    expect(await cacheAudio(SCOPE_A, SRC)).toBe(false)
    expect(await readCachedAudio(SCOPE_A, SRC)).toBeNull()
    expect((await getAudioCacheDiagnostics()).supported).toBe(false)
  })
})
