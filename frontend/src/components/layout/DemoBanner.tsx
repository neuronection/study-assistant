import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { FlaskConical } from 'lucide-react'

import { getInstanceConfig, type InstanceConfig } from '@/lib/api'

let demoModeFlag: Promise<boolean> | null = null
let instanceConfigFlag: Promise<InstanceConfig | undefined> | null = null

/** Whether this is a demo instance (`instance_settings.demo_mode`,
 * identity-auth §13) — fetched once per app boot from the public
 * `GET /api/v1/instance/config`, cached so the badge never refetches.
 * A failed fetch reads as "not a demo" (fail-closed, never a blocker). */
export function loadDemoMode(): Promise<boolean> {
  if (demoModeFlag === null) {
    demoModeFlag = loadInstanceConfig().then((config) => config?.demo_mode === true)
  }
  return demoModeFlag
}

/** The public instance facts, fetched once per app boot (the same
 * request the demo badge uses — the promise is shared). A failed fetch
 * reads as `undefined`: the profile-selection repair skips it (the
 * middleware still enforces server-side; nothing client-side can
 * un-fail a request). */
export function loadInstanceConfig(): Promise<InstanceConfig | undefined> {
  if (instanceConfigFlag === null) {
    instanceConfigFlag = getInstanceConfig().catch(() => undefined)
  }
  return instanceConfigFlag
}

export function clearDemoModeCache(): void {
  demoModeFlag = null
  instanceConfigFlag = null
}

/** Persistent "Demo — synthetic data" badge (identity-auth §13). Lives
 * in the boot gate, not the app shell, so it renders before login as
 * well — a public demo is badged from the very first pixel. */
export function DemoBanner() {
  const { t } = useTranslation()
  const [demo, setDemo] = useState(false)

  useEffect(() => {
    let alive = true
    void loadDemoMode().then((value) => {
      if (alive) setDemo(value)
    })
    return () => {
      alive = false
    }
  }, [])

  if (!demo) return null
  return (
    <div
      role="status"
      className="border-amber-500/20 bg-amber-500/10 text-amber-700 dark:text-amber-400 sticky top-0 z-50 flex items-center justify-center gap-2 border-b px-3 py-1.5 text-xs font-medium"
    >
      <FlaskConical className="size-3.5 shrink-0" aria-hidden />
      <span>{t('demo.badge')}</span>
      <span className="font-normal opacity-80">{t('demo.description')}</span>
    </div>
  )
}
