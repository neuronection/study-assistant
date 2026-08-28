import { Settings } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from '@tanstack/react-router'

import { Button } from '@/components/ui/button'

export function ErrorBanner({ message }: { message: string | null }) {
  const { t } = useTranslation()
  if (!message) {
    return null
  }
  const actionable = /unassigned|provider/i.test(message)
  return (
    <div
      role="alert"
      className="border-danger/40 bg-danger/10 text-danger flex items-center gap-3 rounded-lg border px-3 py-2 text-xs"
    >
      <span className="min-w-0 flex-1">{message}</span>
      {actionable ? (
        <Button variant="outline" size="sm" asChild>
          <Link to="/settings">
            <Settings aria-hidden />
            {t('errors.openSettings')}
          </Link>
        </Button>
      ) : null}
    </div>
  )
}
