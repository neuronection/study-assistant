import { Keyboard } from 'lucide-react'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useCloseFloatings } from '@/lib/ui-overlays'
import { SHORTCUT_GROUPS } from '@/lib/shortcuts'

export function ShortcutsDialog({ onClose }: { onClose: () => void }) {
  useCloseFloatings()
  const { t } = useTranslation()
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose()
        }
      }}
    >
      <Card className="max-h-[85vh] w-full max-w-2xl overflow-y-auto">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Keyboard className="size-4" aria-hidden />
            {t('shortcuts.title')}
          </CardTitle>
          <p className="text-muted-foreground text-xs">{t('shortcuts.hint')}</p>
        </CardHeader>
        <CardContent>
          <div className="grid gap-x-8 gap-y-5 sm:grid-cols-2">
            {SHORTCUT_GROUPS.map((group) => (
              <section key={group.id} aria-label={t(`shortcuts.group.${group.id}`)}>
                <h2 className="text-muted-foreground mb-2 text-xs font-semibold tracking-wide uppercase">
                  {t(`shortcuts.group.${group.id}`)}
                </h2>
                <ul className="space-y-1.5">
                  {group.entries.map((entry) => (
                    <li key={entry.id} className="flex items-center justify-between gap-3 text-sm">
                      <span>{t(`shortcuts.${entry.id}`)}</span>
                      <kbd className="text-muted-foreground bg-subtle rounded border border-border px-1.5 py-0.5 font-mono text-[11px] whitespace-nowrap">
                        {entry.keys}
                      </kbd>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        </CardContent>
        <div className="flex justify-end gap-2 px-6 pb-6">
          <Button variant="ghost" size="sm" onClick={onClose}>
            {t('common.close')}
          </Button>
        </div>
      </Card>
    </div>
  )
}
