import type { PublicUser } from './api/admin'
import { UNAUTHENTICATED_EVENT, apiFetch, tryRefreshSession } from './api/client'

let currentUser: PublicUser | null = null

/** The signed-in user (identity-auth §12 `PublicUser`) established by the
 * boot/login flow — `null` while anonymous. Module state on purpose: the
 * value is fixed once `bootSession` resolves and is not reactive; read it
 * after boot (e.g. settings tabs) or via `setCurrentUser` after an
 * account mutation. */
export function getCurrentUser(): PublicUser | null {
  return currentUser
}

export function setCurrentUser(user: PublicUser | null): void {
  currentUser = user
}

async function loadUser(): Promise<boolean> {
  const response = await apiFetch('/api/v1/auth/me')
  if (!response.ok) {
    currentUser = null
    return false
  }
  currentUser = (await response.json()) as PublicUser
  return true
}

/** Establish a session before the app renders (identity-auth §4/§11).

1. live session → done (the `PublicUser` incl. `is_admin` is stored);
2. expired access + valid refresh cookie → rotate, re-check;
3. desktop entrypoint (`?shell=`) → one-time exchange (zero setup —
   implicit owner on `open` instances; 404 on `authenticated` ones);
4. otherwise anonymous → the login gate.
*/
export async function bootSession(): Promise<boolean> {
  if (await loadUser()) return true
  if (await tryRefreshSession()) {
    if (await loadUser()) return true
  }
  // Desktop DIM boot exchange: the shipped shell (?shell=) or the
  // shell-less dev server (gate disarmed, ADR-0023) mints the implicit
  // owner. The route is unmounted on server deployments (404) and 404s
  // on authenticated desktop instances — both fall to the login gate.
  const exchange = await apiFetch('/api/v1/auth/desktop/exchange', {
    method: 'POST',
  })
  if (exchange.ok) return loadUser()
  currentUser = null
  return false
}

/** End the session (identity-auth §4): revoke server-side, drop the
 * cached `PublicUser` and announce the loss so the SessionGate re-runs
 * the boot flow into the login overlay. Network errors never block the
 * local sign-out — the refresh cookie family dies with the revoke, and a
 * stale cookie still 401s through the normal refresh path. */
export async function logoutSession(): Promise<void> {
  try {
    await apiFetch('/api/v1/auth/logout', { method: 'POST' })
  } catch {
    // unreachable server — the local session is dead regardless
  }
  currentUser = null
  window.dispatchEvent(new Event(UNAUTHENTICATED_EVENT))
}
