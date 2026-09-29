import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import {
  AdminUserTable,
  type AdminUserTableLabels,
} from '@/components/ui/admin-user-table'
import {
  forceLogoutUser,
  listAdminUsers,
  patchAdminUser,
  resetAdminUserPassword,
} from '@/lib/api'
import { getCurrentUser } from '@/lib/auth-session'

/** Admin user management (identity-auth §12): the shared
 * `AdminUserTable` fed by the `/api/v1/admin/users` API. Actions
 * persist through the api layer and re-supply the list; guard-rail 403s
 * surface as the table's friendly messages. Admin-only — `SettingsPage`
 * hides the tab for everyone else. */
export function UsersTab() {
  const { t } = useTranslation()
  const me = getCurrentUser()

  const users = useQuery({
    queryKey: ['admin-users'],
    queryFn: listAdminUsers,
  })

  const labels: AdminUserTableLabels = {
    tableCaption: t('settings.users.tableCaption'),
    you: t('settings.users.you'),
    email: t('settings.users.email'),
    activity: t('settings.users.activity'),
    role: t('settings.users.role'),
    status: t('settings.users.status'),
    actions: t('settings.users.actions'),
    adminRole: t('settings.users.adminRole'),
    userRole: t('settings.users.userRole'),
    activeStatus: t('settings.users.activeStatus'),
    disabledStatus: t('settings.users.disabledStatus'),
    promote: t('settings.users.promote'),
    demote: t('settings.users.demote'),
    activate: t('settings.users.activate'),
    deactivate: t('settings.users.deactivate'),
    resetPassword: t('settings.users.resetPassword'),
    forceLogout: t('settings.users.forceLogout'),
    loading: t('settings.users.loading'),
    empty: t('settings.users.empty'),
    resetTitle: (email: string) => t('settings.users.newPasswordFor', { email }),
    newPassword: t('settings.users.newPassword'),
    passwordHint: (minLength: number) => t('settings.users.minChars', { minLength }),
    setPassword: t('settings.users.setPassword'),
    cancel: t('settings.cancel'),
    resetNote: (email: string) => t('settings.users.resetNote', { email }),
    errorGeneric: t('settings.users.errorGeneric'),
    errorForbidden: t('settings.users.errorForbidden'),
    errorSelf: t('settings.users.errorSelf'),
    errorLastAdmin: t('settings.users.errorLastAdmin'),
  }

  return (
    <AdminUserTable
      users={users.data ?? []}
      currentUserId={me?.id ?? ''}
      loading={users.isLoading}
      error={users.error ? t('settings.users.errorGeneric') : null}
      onPatch={async (user, patch) => {
        await patchAdminUser(user.id, patch)
        await users.refetch()
      }}
      onResetPassword={async (user, newPassword) => {
        await resetAdminUserPassword(user.id, newPassword)
        await users.refetch()
      }}
      onForceLogout={async (user) => {
        await forceLogoutUser(user.id)
        await users.refetch()
      }}
      labels={labels}
    />
  )
}
