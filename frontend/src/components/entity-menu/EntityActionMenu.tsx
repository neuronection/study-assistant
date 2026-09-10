import { X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { EntityActionGroup } from './types'
import { useCloseFloatings } from '@/lib/ui-overlays'

export function EntityActionMenu({
  title,
  groups,
  onClose,
}: {
  title: string
  groups: EntityActionGroup[]
  onClose: () => void
}) {
  useCloseFloatings()
  const { t } = useTranslation()
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <Card
        className="max-h-[85vh] w-full max-w-md overflow-y-auto"
        onClick={(event) => event.stopPropagation()}
      >
        <CardHeader className="flex-row items-start justify-between gap-2 space-y-0">
          <div className="min-w-0">
            <CardTitle className="truncate text-base">{title}</CardTitle>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} title={t('settings.cancel')}>
            <X className="size-4" aria-hidden />
          </Button>
        </CardHeader>
        <CardContent className="space-y-3">
          {groups.map((group, groupIndex) => (
            <section key={groupIndex} className="space-y-1.5">
              {group.label ? (
                <h3 className="text-muted-foreground text-xs font-medium">{group.label}</h3>
              ) : null}
              <div className="grid grid-cols-2 gap-2">
                {group.actions.map((action) => (
                  <button
                    key={action.key}
                    type="button"
                    className={
                      action.danger
                        ? 'bg-surface hover:bg-subtle border-border flex items-center gap-2 rounded-lg border px-3 py-2 text-left text-sm text-danger'
                        : 'bg-surface hover:bg-subtle border-border flex items-center gap-2 rounded-lg border px-3 py-2 text-left text-sm'
                    }
                    onClick={action.onSelect}
                  >
                    <action.icon className="text-muted-foreground size-4 shrink-0" aria-hidden />
                    <span className="truncate">{action.label}</span>
                  </button>
                ))}
              </div>
            </section>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}
