import { useQueryClient } from '@tanstack/react-query'
import { create } from 'zustand'
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from '@tanstack/react-router'

import { getNotifications } from '@/lib/api'
import { storageKeys } from '@/lib/constants'

const NUDGE_INTERVAL_MS = 30 * 60 * 1000

export type NudgePermission = 'granted' | 'denied' | 'default' | 'unsupported'

interface NotificationCtor {
  new (title: string, options?: NotificationOptions): Notification
}

interface NotificationApi {
  permission: NotificationPermission
  requestPermission(): Promise<NotificationPermission>
  Notification: NotificationCtor
}

function notificationApi(): NotificationApi | null {
  if (typeof window === 'undefined' || typeof window.Notification === 'undefined') {
    return null
  }
  return window.Notification as unknown as NotificationApi
}

export function readNudgeEnabled(): boolean {
  try {
    return window.localStorage.getItem(storageKeys.reviewNudges) === '1'
  } catch {
    return false
  }
}

function writeNudgeEnabled(enabled: boolean): void {
  try {
    if (enabled) {
      window.localStorage.setItem(storageKeys.reviewNudges, '1')
    } else {
      window.localStorage.removeItem(storageKeys.reviewNudges)
    }
  } catch {
    return
  }
}

interface NudgeStoreState {
  enabled: boolean
  setEnabled: (enabled: boolean) => void
}

export const useNudgeStore = create<NudgeStoreState>((set) => ({
  enabled: readNudgeEnabled(),
  setEnabled: (enabled) => {
    writeNudgeEnabled(enabled)
    set({ enabled })
  },
}))

/** Settings surface: permission handshake + persisted opt-in flag. */
export function useReviewNudgeSetting(): {
  enabled: boolean
  permission: NudgePermission
  setEnabled: (enabled: boolean) => void
} {
  const api = notificationApi()
  const enabled = useNudgeStore((state) => state.enabled)
  const storeSetEnabled = useNudgeStore((state) => state.setEnabled)
  const [permission, setPermission] = useState<NudgePermission>(() =>
    api === null ? 'unsupported' : (api.permission as NudgePermission)
  )

  const setEnabled = useCallback(
    (next: boolean) => {
      if (next) {
        const currentApi = notificationApi()
        if (currentApi === null) {
          setPermission('unsupported')
          return
        }
        void currentApi.requestPermission().then((result) => {
          setPermission(result as NudgePermission)
          storeSetEnabled(result === 'granted')
        })
        return
      }
      storeSetEnabled(false)
    },
    [storeSetEnabled]
  )

  return { enabled, permission, setEnabled }
}

/** App-wide interval: at most one summary notification per 30 minutes while enabled. */
export function useReviewNudgeInterval(): void {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const enabled = useNudgeStore((state) => state.enabled)

  useEffect(() => {
    const api = notificationApi()
    if (!enabled || api === null || api.permission !== 'granted') {
      return
    }
    const fire = () => {
      const active =
        document.visibilityState === 'visible' || document.hasFocus()
      if (!active) {
        return
      }
      void getNotifications().then((data) => {
        if (data.due_cards <= 0) {
          return
        }
        const currentApi = notificationApi()
        if (currentApi === null || currentApi.permission !== 'granted') {
          return
        }
        const notice = new currentApi.Notification(
          t('nudges.title', { count: data.due_cards }),
          {
            body: t('nudges.body'),
            tag: 'review-nudge',
          }
        )
        notice.onclick = () => {
          window.focus()
          void queryClient.invalidateQueries({ queryKey: ['notifications'] })
          navigate({ to: '/review' })
        }
      })
    }
    fire()
    const interval = window.setInterval(fire, NUDGE_INTERVAL_MS)
    return () => window.clearInterval(interval)
  }, [enabled, t, navigate, queryClient])
}
