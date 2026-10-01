import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import {
  AdminUserTable,
  type AdminUserTableLabels,
} from '@/components/ui/admin-user-table'
import {
  InstanceModeControl,
  type InstanceModeControlLabels,
} from '@/components/ui/instance-mode-control'
import {
  forceLogoutUser,
  getInstanceConfig,
  listAdminUsers,
  patchAdminUser,
  resetAdminUserPassword,
  updateInstanceMode,
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

  const instance = useQuery({
    queryKey: ['instance-config'],
    queryFn: getInstanceConfig,
  })

  const instanceLabels: InstanceModeControlLabels = {
    title: t('settings.instance.title'),
    modeOpen: t('settings.instance.modeOpen'),
    modeAuthenticated: t('settings.instance.modeAuthenticated'),
    modeOpenHint: t('settings.instance.modeOpenHint'),
    modeAuthenticatedHint: t('settings.instance.modeAuthenticatedHint'),
    enableLogin: t('settings.instance.enableLogin'),
    enableLoginNote: (minLength: number) =>
      t('settings.instance.enableLoginNote', { minLength }),
    disableLogin: t('settings.instance.disableLogin'),
    disableLoginNote: t('settings.instance.disableLoginNote'),
    password: t('settings.instance.password'),
    confirmPassword: t('settings.instance.confirmPassword'),
    passwordMismatch: t('settings.instance.passwordMismatch'),
    passwordTooShort: (minLength: number) =>
      t('settings.instance.passwordTooShort', { minLength }),
    submitEnable: t('settings.instance.submitEnable'),
    submitDisable: t('settings.instance.submitDisable'),
    confirmAck: t('settings.instance.confirmAck'),
    blockedServer: t('settings.instance.blockedServer'),
    blockedUsers: (count: number) => t('settings.instance.blockedUsers', { count }),
    auditNote: t('settings.instance.auditNote'),
    errorGeneric: t('settings.instance.errorGeneric'),
    errorForbidden: t('settings.instance.errorForbidden'),
  }

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
    <div className="space-y-6">
      <InstanceModeControl
        mode={instance.data?.auth_mode === 'open' ? 'open' : 'authenticated'}
        otherUserCount={Math.max(0, (users.data?.length ?? 1) - 1)}
        loading={instance.isLoading}
        error={instance.error ? t('settings.instance.errorGeneric') : null}
        onSetAuthenticated={async (password) => {
          await updateInstanceMode('authenticated', password)
          await Promise.all([users.refetch(), instance.refetch()])
        }}
        onSetOpen={async (password) => {
          await updateInstanceMode('open', password)
          await Promise.all([users.refetch(), instance.refetch()])
        }}
        labels={instanceLabels}
      />
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
    </div>
  )
}
