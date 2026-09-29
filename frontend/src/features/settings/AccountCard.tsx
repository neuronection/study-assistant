import { useQuery } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { ErrorBanner } from '@/components/ErrorBanner'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  ApiError,
  apiDetailMessage,
  changeMyPassword,
  deleteMyAccount,
  listMySessions,
  revokeMySession,
  type UserSession,
} from '@/lib/api'
import { UNAUTHENTICATED_EVENT } from '@/lib/api/client'
import { setCurrentUser } from '@/lib/auth-session'
import { formatDateTime } from '@/lib/format'
import { useConfirm } from '@/lib/use-confirm'

const MIN_PASSWORD_LENGTH = 10

function errorText(
  err: unknown,
  wrongPassword: string,
  generic: string,
): string {
  if (err instanceof ApiError && err.status === 403) return wrongPassword
  const detail = err instanceof ApiError ? apiDetailMessage(err.detail) : null
  return detail ?? generic
}

function SessionRow({
  session,
  onRevoke,
}: {
  session: UserSession
  onRevoke: (session: UserSession) => void
}) {
  const { t } = useTranslation()
  return (
    <li
      className="flex flex-wrap items-center justify-between gap-2 py-2"
      data-testid="account-session"
    >
      <div className="min-w-0">
        <p className="text-sm">
          {session.client_label || '—'}
          {session.current ? (
            <span className="text-muted-foreground ml-2 text-xs">
              ({t('settings.account.sessionCurrent')})
            </span>
          ) : null}
        </p>
        <p className="text-muted-foreground text-xs">
          {session.created_at
            ? t('settings.account.sessionCreated', {
                when: formatDateTime(session.created_at),
              })
            : '—'}
          {' · '}
          {t('settings.account.sessionExpires', {
            when: formatDateTime(session.expires_at),
          })}
        </p>
      </div>
      {session.revoked_at ? (
        <span className="text-muted-foreground text-xs">
          {t('settings.account.sessionRevoked')}
        </span>
      ) : (
        <Button
          variant="outline"
          size="sm"
          onClick={() => onRevoke(session)}
          aria-label={`${t('settings.account.revoke')} — ${session.client_label || session.id}`}
        >
          {t('settings.account.revoke')}
        </Button>
      )}
    </li>
  )
}

/** Account self-service (identity-auth §12, `/api/v1/me`): the caller's
 * sessions with revocation, password change and account deletion. */
export function AccountCard() {
  const { t } = useTranslation()
  const [confirm, confirmElement] = useConfirm()
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [deletePassword, setDeletePassword] = useState('')

  const sessions = useQuery({
    queryKey: ['my-sessions'],
    queryFn: listMySessions,
  })

  const dropToLogin = () => {
    setCurrentUser(null)
    window.dispatchEvent(new Event(UNAUTHENTICATED_EVENT))
  }

  const revoke = async (session: UserSession) => {
    const ok = await confirm({
      title: t('settings.account.revokeConfirmTitle'),
      description: session.current
        ? t('settings.account.revokeCurrentBody')
        : t('settings.account.revokeConfirmBody'),
      confirmLabel: t('settings.account.revoke'),
    })
    if (!ok) return
    try {
      await revokeMySession(session.id)
      setError(null)
      setMessage(t('settings.account.revoked'))
      if (session.current) {
        dropToLogin()
        return
      }
      await sessions.refetch()
    } catch (err) {
      setError(
        errorText(
          err,
          t('settings.account.errorWrongPassword'),
          t('settings.account.errorGeneric'),
        ),
      )
    }
  }

  const changePassword = async (event: FormEvent) => {
    event.preventDefault()
    if (newPassword.length < MIN_PASSWORD_LENGTH) return
    try {
      const user = await changeMyPassword(currentPassword, newPassword)
      setCurrentUser(user)
      setError(null)
      setMessage(t('settings.account.passwordChanged'))
      setCurrentPassword('')
      setNewPassword('')
      await sessions.refetch()
    } catch (err) {
      setError(
        errorText(
          err,
          t('settings.account.errorWrongPassword'),
          t('settings.account.errorGeneric'),
        ),
      )
    }
  }

  const deleteAccount = async (event: FormEvent) => {
    event.preventDefault()
    try {
      await deleteMyAccount(deletePassword)
      setError(null)
      dropToLogin()
    } catch (err) {
      setError(
        errorText(
          err,
          t('settings.account.errorWrongPassword'),
          t('settings.account.errorGeneric'),
        ),
      )
    }
  }

  return (
    <Card data-testid="account-card">
      <CardHeader>
        <CardTitle className="text-sm">{t('settings.account.title')}</CardTitle>
        <CardDescription>{t('settings.account.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <ErrorBanner message={error} />
        {message ? <p className="text-muted-foreground text-xs">{message}</p> : null}

        <section aria-label={t('settings.account.sessionsTitle')} className="space-y-2">
          <div>
            <h3 className="text-sm font-medium">{t('settings.account.sessionsTitle')}</h3>
            <p className="text-muted-foreground text-xs">
              {t('settings.account.sessionsDescription')}
            </p>
          </div>
          {sessions.isLoading ? (
            <p className="text-muted-foreground text-xs">
              {t('settings.account.sessionsLoading')}
            </p>
          ) : sessions.error ? (
            <p className="text-danger text-xs">{t('settings.account.errorGeneric')}</p>
          ) : (sessions.data ?? []).length === 0 ? (
            <p className="text-muted-foreground text-xs">
              {t('settings.account.sessionsEmpty')}
            </p>
          ) : (
            <ul className="divide-border divide-y">
              {(sessions.data ?? []).map((session) => (
                <SessionRow key={session.id} session={session} onRevoke={revoke} />
              ))}
            </ul>
          )}
        </section>

        <section aria-label={t('settings.account.passwordTitle')} className="space-y-2">
          <div>
            <h3 className="text-sm font-medium">{t('settings.account.passwordTitle')}</h3>
            <p className="text-muted-foreground text-xs">
              {t('settings.account.passwordDescription')}
            </p>
          </div>
          <form
            className="max-w-sm space-y-2"
            onSubmit={(event) => void changePassword(event)}
          >
            <label className="block space-y-1 text-sm">
              <span className="text-muted-foreground">
                {t('settings.account.currentPassword')}
              </span>
              <input
                className="bg-app border-border w-full rounded-md border px-3 py-2"
                type="password"
                autoComplete="current-password"
                required
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
              />
            </label>
            <label className="block space-y-1 text-sm">
              <span className="text-muted-foreground">
                {t('settings.account.newPassword')}
              </span>
              <input
                className="bg-app border-border w-full rounded-md border px-3 py-2"
                type="password"
                autoComplete="new-password"
                required
                minLength={MIN_PASSWORD_LENGTH}
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
              />
            </label>
            <p className="text-muted-foreground text-xs">
              {t('settings.account.newPasswordHint', {
                minLength: MIN_PASSWORD_LENGTH,
              })}
            </p>
            <Button
              type="submit"
              size="sm"
              disabled={newPassword.length < MIN_PASSWORD_LENGTH}
            >
              {t('settings.account.changePassword')}
            </Button>
          </form>
        </section>

        <section aria-label={t('settings.account.deleteTitle')} className="space-y-2">
          <div>
            <h3 className="text-danger text-sm font-medium">
              {t('settings.account.deleteTitle')}
            </h3>
            <p className="text-muted-foreground text-xs">
              {t('settings.account.deleteDescription')}
            </p>
          </div>
          <form
            className="max-w-sm space-y-2"
            onSubmit={(event) => void deleteAccount(event)}
          >
            <label className="block space-y-1 text-sm">
              <span className="text-muted-foreground">
                {t('settings.account.deletePasswordLabel')}
              </span>
              <input
                className="bg-app border-border w-full rounded-md border px-3 py-2"
                type="password"
                autoComplete="current-password"
                required
                value={deletePassword}
                onChange={(event) => setDeletePassword(event.target.value)}
              />
            </label>
            <Button
              type="submit"
              size="sm"
              variant="destructive"
              disabled={deletePassword.length === 0}
            >
              {t('settings.account.deleteAccount')}
            </Button>
          </form>
        </section>
      </CardContent>
      {confirmElement}
    </Card>
  )
}
