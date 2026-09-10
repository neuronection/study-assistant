import { Settings } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from '@tanstack/react-router'

import { Button } from '@/components/ui/button'
import { ErrorBanner as ErrorBannerPrimitive } from '@neuronection/assistant-ui'

export function ErrorBanner({ message }: { message: string | null }) {
  const { t } = useTranslation()
  if (!message) {
    return null
  }
  const actionable = /unassigned|provider/i.test(message)
  return (
    <ErrorBannerPrimitive
      message={message}
      action={
        actionable ? (
          <Button variant="outline" size="sm" asChild>
            <Link to="/settings">
              <Settings aria-hidden />
              {t('errors.openSettings')}
            </Link>
          </Button>
        ) : undefined
      }
    />
  )
}
