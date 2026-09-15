import { useTranslation } from 'react-i18next'

import { LanguagePicker } from '@/components/LanguagePicker'
import { CheckIndicator } from '@/components/ui/CheckIndicator'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { useReviewNudgeSetting } from '@/lib/review-nudges'

export function GeneralTab() {
  const { t } = useTranslation()
  const { enabled, permission, setEnabled } = useReviewNudgeSetting()

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t('settings.generalTitle')}</CardTitle>
          <CardDescription>{t('settings.generalDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="max-w-sm space-y-2">
          <LanguagePicker />
          <p className="text-muted-foreground text-[11px]">{t('settings.languageHint')}</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t('settings.remindersTitle')}</CardTitle>
          <CardDescription>{t('settings.remindersDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="max-w-sm space-y-2">
          {permission === 'unsupported' ? (
            <p className="text-muted-foreground text-xs">{t('settings.remindersUnsupported')}</p>
          ) : (
            <div className="flex items-center gap-2">
              <CheckIndicator
                checked={enabled}
                label={t('settings.remindersToggle')}
                onToggle={() => setEnabled(!enabled)}
              />
              <span className="text-foreground text-xs">{t('settings.remindersToggle')}</span>
            </div>
          )}
          <p className="text-muted-foreground text-[11px]">
            {permission === 'denied'
              ? t('settings.remindersDenied')
              : t('settings.remindersHint')}
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
