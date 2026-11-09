import { Copy } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { InstanceConfig } from '@/lib/api'

import { loadInstanceConfig } from './DemoBanner'

const SEEN_KEY = 'sa.datastore-quarantine-seen'

type Quarantine = NonNullable<InstanceConfig['datastore_quarantine']>

/** One-time notice for the deliberate 0.13 datastore break: the entrypoint
 * moved the old data aside and started fresh. Dismissal is local. */
export function DatastoreQuarantineDialog() {
  const { t } = useTranslation()
  const [notice, setNotice] = useState<Quarantine | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    let alive = true
    void loadInstanceConfig().then((config) => {
      const quarantine = config?.datastore_quarantine
      if (!alive || !quarantine) {
        return
      }
      if (localStorage.getItem(SEEN_KEY) === quarantine.quarantined_at) {
        return
      }
      setNotice(quarantine)
    })
    return () => {
      alive = false
    }
  }, [])

  useEffect(() => {
    if (!notice) {
      return
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        localStorage.setItem(SEEN_KEY, notice.quarantined_at)
        setNotice(null)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [notice])

  if (!notice) {
    return null
  }

  const dismiss = () => {
    localStorage.setItem(SEEN_KEY, notice.quarantined_at)
    setNotice(null)
  }

  const copyPath = async () => {
    try {
      await navigator.clipboard.writeText(notice.path)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      // clipboard is best-effort
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          dismiss()
        }
      }}
    >
      <Card
        role="dialog"
        aria-modal="true"
        aria-labelledby="datastore-quarantine-title"
        className="w-full max-w-lg"
      >
        <CardHeader>
          <CardTitle id="datastore-quarantine-title" className="text-base">
            {t('quarantine.title')}
          </CardTitle>
          <p className="text-muted-foreground text-xs">{t('quarantine.body')}</p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1">
            <p className="text-muted-foreground text-xs">{t('quarantine.pathLabel')}</p>
            <p className="bg-subtle rounded border border-border p-2 font-mono text-xs break-all">
              {notice.path}
            </p>
          </div>
          <p className="text-muted-foreground text-xs">{t('quarantine.hint')}</p>
          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => void copyPath()}>
              <Copy className="size-3.5" aria-hidden />
              {copied ? t('quarantine.copied') : t('quarantine.copy')}
            </Button>
            <Button size="sm" autoFocus onClick={dismiss}>
              {t('quarantine.dismiss')}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
