import { useTranslation } from 'react-i18next'

import { LanguagePicker } from '@/components/LanguagePicker'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

export function GeneralTab() {
  const { t } = useTranslation()

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
    </div>
  )
}
