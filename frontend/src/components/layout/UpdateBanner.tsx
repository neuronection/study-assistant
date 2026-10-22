import { useQuery } from '@tanstack/react-query'
import { Download, X } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { getUpdateCheck } from '@/lib/api'
import { storageKeys } from '@/lib/constants'

const SIX_HOURS_MS = 6 * 60 * 60 * 1000

function readDismissed(): string | null {
  try {
    return window.localStorage.getItem(storageKeys.updateDismissed)
  } catch {
    return null
  }
}

export function UpdateBanner() {
  const { t } = useTranslation()
  const [dismissed, setDismissed] = useState<string | null>(readDismissed)
  const update = useQuery({
    queryKey: ['update-check'],
    queryFn: getUpdateCheck,
    staleTime: SIX_HOURS_MS,
    retry: false,
  })
  const latest = update.data?.latest_version ?? null
  if (!update.data?.update_available || latest === null || dismissed === latest) {
    return null
  }
  const dismiss = () => {
    setDismissed(latest)
    try {
      window.localStorage.setItem(storageKeys.updateDismissed, latest)
    } catch {
      return
    }
  }
  return (
    <div className="border-primary/30 bg-primary/5 flex items-center gap-2 border-b px-4 py-2 text-xs">
      <Download className="text-primary size-3.5 shrink-0" aria-hidden />
      <span className="flex-1">
        {t('update.available', { version: latest.replace(/^v/, '') })}
      </span>
      <a
        href={update.data.release_url}
        target="_blank"
        rel="noreferrer"
        className="text-primary shrink-0 font-medium underline"
      >
        {t('update.download')}
      </a>
      <button
        type="button"
        className="text-muted-foreground hover:text-foreground shrink-0 rounded p-0.5"
        aria-label={t('update.dismiss')}
        onClick={dismiss}
      >
        <X className="size-3.5" aria-hidden />
      </button>
    </div>
  )
}
