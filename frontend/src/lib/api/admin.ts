import { apiFetch, expectOk, json } from './client'

/** `PublicUser` (identity-auth §12) — what `/api/v1/auth/me` and
 * `PATCH /api/v1/me/password` return. Never hashes/counters/stamps. */
export interface PublicUser {
  id: string
  email: string
  full_name: string
  is_admin: boolean
  is_active: boolean
}

/** Admin row shape of `GET /api/v1/admin/users` (identity-auth §12). */
export interface AdminUser {
  id: string
  email: string
  full_name: string
  is_admin: boolean
  is_active: boolean
  created_at: string
  activity_count: number
}

export interface AdminUserPatch {
  is_active?: boolean
  is_admin?: boolean
}

/** Entry of `GET /api/v1/me/sessions`. */
export interface UserSession {
  id: string
  client_label: string
  created_at: string | null
  expires_at: string
  revoked_at: string | null
  current: boolean
}

export async function listAdminUsers(): Promise<AdminUser[]> {
  const response = await apiFetch('/api/v1/admin/users')
  return json<AdminUser[]>(response)
}

export async function patchAdminUser(
  userId: string,
  patch: AdminUserPatch,
): Promise<AdminUser> {
  const response = await apiFetch(`/api/v1/admin/users/${userId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
  return json<AdminUser>(response)
}

export async function resetAdminUserPassword(
  userId: string,
  newPassword: string,
): Promise<void> {
  const response = await apiFetch(`/api/v1/admin/users/${userId}/reset-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ new_password: newPassword }),
  })
  await expectOk(response)
}

export async function forceLogoutUser(userId: string): Promise<void> {
  const response = await apiFetch(`/api/v1/admin/users/${userId}/force-logout`, {
    method: 'POST',
  })
  await expectOk(response)
}

export async function listMySessions(): Promise<UserSession[]> {
  const response = await apiFetch('/api/v1/me/sessions')
  return json<UserSession[]>(response)
}

export async function revokeMySession(familyId: string): Promise<void> {
  const response = await apiFetch(`/api/v1/me/sessions/${familyId}`, {
    method: 'DELETE',
  })
  await expectOk(response)
}

/** Changes the password and rotates the caller's session cookies —
 * the caller stays signed in, every other session is signed out. */
export async function changeMyPassword(
  currentPassword: string,
  newPassword: string,
): Promise<PublicUser> {
  const response = await apiFetch('/api/v1/me/password', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  })
  return json<PublicUser>(response)
}

export async function deleteMyAccount(password: string): Promise<void> {
  const response = await apiFetch('/api/v1/me', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  })
  await expectOk(response)
}
