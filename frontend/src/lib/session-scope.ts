import type { PublicUser } from './api/admin'

const LOCAL_SCOPE = 'local'

let lastResolvedScope: string | null = null
let currentScope: string | null = null
const scopeListeners = new Set<() => void>()

/** One identity for every profile-scoped browser store: the signed-in
 * user plus the active profile. `null` means "not resolved yet" — stores
 * must not read or write durable state until it is non-null. */
export function resolveSessionScope(
  user: PublicUser | null,
  profileId: string | null,
): string | null {
  if (user === null || profileId === null || profileId.length === 0) {
    return null
  }
  return `u:${user.id}:p:${profileId}`
}

/** Reactive source for components that need the CURRENT resolved scope
 * (the shell resolves it after boot). `null` until resolved. */
export function getCurrentSessionScope(): string | null {
  return currentScope
}

export function subscribeSessionScope(listener: () => void): () => void {
  scopeListeners.add(listener)
  return () => {
    scopeListeners.delete(listener)
  }
}

function setCurrentSessionScope(scope: string | null): void {
  if (currentScope === scope) {
    return
  }
  currentScope = scope
  for (const listener of scopeListeners) {
    listener()
  }
}

/** Kept for session-loss cleanup: logout/401 paths run after the shell has
 * already cleared the user, so they need the scope the browser last used. */
export function rememberSessionScope(scope: string | null): void {
  if (scope !== null) {
    lastResolvedScope = scope
    setCurrentSessionScope(scope)
  }
}

export function getLastSessionScope(): string | null {
  return lastResolvedScope
}

export function forgetSessionScope(scope?: string | null): void {
  if (scope === undefined || scope === null || lastResolvedScope === scope) {
    lastResolvedScope = null
    setCurrentSessionScope(null)
  }
}

/** Stable local key for browser state that predates a resolved scope (the
 * desktop owner before the profile list loads). Never used as a durable
 * cache bucket for authenticated users. */
export function scopeStorageKey(scope: string | null): string {
  return scope ?? LOCAL_SCOPE
}

export function resetSessionScopeForTests(): void {
  lastResolvedScope = null
  setCurrentSessionScope(null)
}
