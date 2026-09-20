import { useTranslation } from 'react-i18next'

import type { ProviderSetupErrorDetail } from '@/lib/api'

const ERROR_CODES = [
  'invalid_key',
  'insufficient_credit',
  'new_user_quota',
  'region_unavailable',
  'timeout',
  'local_not_running',
  'unknown',
] as const

export function errorLabel(code: string): string {
  return (ERROR_CODES as readonly string[]).includes(code) ? code : 'unknown'
}

export function SetupErrorPanel({
  error,
  plainError,
}: {
  error: ProviderSetupErrorDetail | null
  plainError: string | null
}) {
  const { t } = useTranslation()
  if (error) {
    return (
      <div className="text-danger space-y-1 rounded-md border border-dashed border-current/40 px-3 py-2 text-xs">
        <p>{t(`settings.setup.errors.${errorLabel(error.code)}`)}</p>
        {error.suspected_vendor ? (
          <p>{t('settings.setup.errors.suspectedVendor', { vendor: error.suspected_vendor })}</p>
        ) : null}
        {error.detail ? <p className="text-muted-foreground break-words">{error.detail}</p> : null}
      </div>
    )
  }
  if (plainError) {
    return <p className="text-danger text-xs">{plainError}</p>
  }
  return null
}
