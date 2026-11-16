import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { audioCacheName, audioStateKey } from './audio-offline'
import { getCurrentUser, logoutSession, setCurrentUser } from './auth-session'
import { rememberSessionScope, resetSessionScopeForTests } from './session-scope'
import { installFakeCaches } from '@/test/caches'

const { apiFetch, tryRefreshSession } = vi.hoisted(() => ({
  apiFetch: vi.fn(),
  tryRefreshSession: vi.fn(),
}))

vi.mock('./api/client', () => ({
  apiFetch,
  tryRefreshSession,
  UNAUTHENTICATED_EVENT: 'nx:unauthenticated',
}))

const SCOPE = 'u:user-1:p:profile-a'

describe('logoutSession', () => {
  beforeEach(() => {
    resetSessionScopeForTests()
    setCurrentUser(null)
    window.localStorage.clear()
    apiFetch.mockReset().mockResolvedValue(new Response(null, { status: 204 }))
    tryRefreshSession.mockReset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  test('purges the scoped audio cache and state before announcing the loss', async () => {
    const storage = installFakeCaches()
    rememberSessionScope(SCOPE)
    await storage.open(audioCacheName(SCOPE))
    window.localStorage.setItem(audioStateKey(SCOPE), 'state')
    window.localStorage.setItem('sa-first-event.local.first_review', '1')
    setCurrentUser({
      id: 'user-1',
      email: 'ada@example.com',
      full_name: 'Ada',
      is_admin: true,
      is_active: true,
    })

    await logoutSession()

    expect(getCurrentUser()).toBeNull()
    expect(await caches.keys()).not.toContain(audioCacheName(SCOPE))
    expect(window.localStorage.getItem(audioStateKey(SCOPE))).toBeNull()
    expect(
      window.localStorage.getItem('sa-first-event.local.first_review'),
    ).toBeNull()
  })
})
