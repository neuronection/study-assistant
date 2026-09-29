import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { LoginForm } from '@/components/ui/login-form'
import { RegisterForm } from '@/components/ui/register-form'
import { apiFetch } from '@/lib/api/client'

type Mode = 'login' | 'register'

export function LoginOverlay({ onSignedIn }: { onSignedIn: () => void }) {
  const { t } = useTranslation()
  const [mode, setMode] = useState<Mode>('login')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(path: Mode, email: string, password: string) {
    setBusy(true)
    setError(null)
    try {
      const response = await apiFetch(`/api/v1/auth/${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      if (response.ok) {
        onSignedIn()
        return
      }
      let detail = t('auth.genericError')
      try {
        const body: unknown = await response.json()
        const candidate = (body as { detail?: unknown } | null)?.detail
        if (typeof candidate === 'string' && candidate.length > 0) {
          detail = candidate
        }
      } catch {
        // keep the generic message
      }
      setError(detail)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="bg-app text-foreground flex min-h-screen items-center justify-center p-4">
      <div className="bg-surface border-border w-full max-w-sm space-y-4 rounded-lg border p-6 shadow-lg">
        <h1 className="text-lg font-semibold text-center">
          {mode === 'login' ? t('auth.signInTitle') : t('auth.registerTitle')}
        </h1>
        {mode === 'login' ? (
          <LoginForm
            loading={busy}
            error={error}
            labels={{
              submit: t('auth.signIn'),
              register: t('auth.switchToRegister'),
            }}
            fields={{
              email: { label: t('auth.emailLabel') },
              password: { label: t('auth.passwordLabel') },
            }}
            onSubmit={(email, password) => submit('login', email, password)}
            onRegister={() => {
              setMode('register')
              setError(null)
            }}
          />
        ) : (
          <RegisterForm
            loading={busy}
            error={error}
            labels={{
              submit: t('auth.register'),
              passwordHint: t('auth.passwordHint'),
              mismatch: t('auth.passwordMismatch'),
              login: t('auth.switchToLogin'),
            }}
            fields={{
              email: { label: t('auth.emailLabel') },
              password: { label: t('auth.passwordLabel') },
              confirmPassword: { label: t('auth.confirmPasswordLabel') },
            }}
            onSubmit={(email, password) => submit('register', email, password)}
            onLogin={() => {
              setMode('login')
              setError(null)
            }}
          />
        )}
      </div>
    </div>
  )
}
