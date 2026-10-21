import type { components } from '@/lib/api-schema'

import { apiFetch, expectOk, json } from './client'
import type { AdminUser, AdminUserPatch, PublicUser, UserSession } from './hand-types'

type Schemas = components['schemas']

export type { AdminUser, AdminUserPatch, PublicUser, UserSession } from './hand-types'
export type InstanceAuthMode = NonNullable<Schemas['InstanceUpdateIn']['auth_mode']>

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

/** `PATCH /api/v1/admin/instance` (identity-auth §4.5): the audited
 * `auth_mode` transition — admin + password; `open → authenticated` sets
 * the owner credentials in the same call, `authenticated → open` is
 * refused while other accounts exist. */
export async function updateInstanceMode(
  authMode: InstanceAuthMode,
  password: string,
): Promise<void> {
  const response = await apiFetch('/api/v1/admin/instance', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ auth_mode: authMode, password }),
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
