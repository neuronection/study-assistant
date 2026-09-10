import { X } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'

export function StudyPaneHeader({
  title,
  meta,
  tabs,
  primary,
  overflow,
  onClose,
  closeLabel,
}: {
  title: ReactNode
  meta?: ReactNode
  tabs?: ReactNode
  primary?: ReactNode
  overflow?: ReactNode
  onClose?: () => void
  closeLabel?: string
}) {
  const { t } = useTranslation()
  const closeText = closeLabel ?? t('common.close')
  return (
    <header className="border-border flex min-h-11 flex-wrap items-center gap-x-2 gap-y-1 border-b">
      <div className="flex min-w-0 flex-1 basis-48 flex-wrap items-center gap-x-2 gap-y-1">
        {typeof title === 'string' ? (
          <h1 className="truncate text-base font-semibold">{title}</h1>
        ) : (
          title
        )}
        {meta ? (
          <div className="flex min-w-0 flex-wrap items-center gap-1.5">{meta}</div>
        ) : null}
      </div>
      {tabs ? (
        <div className="flex flex-wrap items-center gap-1">{tabs}</div>
      ) : null}
      <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
        {primary}
        {overflow}
        {onClose ? (
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            title={closeText}
            aria-label={closeText}
          >
            <X className="size-4" aria-hidden />
          </Button>
        ) : null}
      </div>
    </header>
  )
}
