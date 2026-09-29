import { type ReactNode, useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { AuthGate } from '@/components/ui/auth-gate'
import { DemoBanner } from '@/components/layout/DemoBanner'
import { UNAUTHENTICATED_EVENT } from '@/lib/api/client'
import { bootSession } from '@/lib/auth-session'

import { LoginOverlay } from './LoginOverlay'

/** Composition root for the shared `AuthGate` (identity-auth §4): the
 * `checking → authenticated | anonymous` machine lives in the library —
 * study only wires the endpoints. `bootSession` (cookie → refresh →
 * desktop exchange, §10/§11) is the machine input; a mid-session 401
 * after a failed refresh dispatches `UNAUTHENTICATED_EVENT`, which bumps
 * the gate's `resetKey` and re-runs the flow. The demo badge (§13) rides
 * outside the gate so it renders in every state, before login too. */
export function SessionGate({ children }: { children: ReactNode }) {
  const { t } = useTranslation()
  const [epoch, setEpoch] = useState(0)
  const recheck = useCallback(() => setEpoch((e) => e + 1), [])

  useEffect(() => {
    window.addEventListener(UNAUTHENTICATED_EVENT, recheck)
    return () => window.removeEventListener(UNAUTHENTICATED_EVENT, recheck)
  }, [recheck])

  return (
    <>
      <DemoBanner />
      <AuthGate
        boot={bootSession}
        resetKey={epoch}
        login={<LoginOverlay onSignedIn={recheck} />}
        checking={
          <div className="bg-app text-muted-foreground flex min-h-screen items-center justify-center">
            {t('auth.checking')}
          </div>
        }
      >
        {children}
      </AuthGate>
    </>
  )
}
