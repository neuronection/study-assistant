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
import { useInterfacePrefsStore, type InterfacePrefKey } from '@/lib/interface-prefs'

const INTERFACE_TOGGLES: { key: InterfacePrefKey; labelKey: string }[] = [
  { key: 'homeContinue', labelKey: 'settings.interfaceHomeContinue' },
  { key: 'paletteRecent', labelKey: 'settings.interfacePaletteRecent' },
  { key: 'courseJumpBackIn', labelKey: 'settings.interfaceCourseJumpBackIn' },
  { key: 'courseCardMeta', labelKey: 'settings.interfaceCourseCardMeta' },
]

export function GeneralTab() {
  const { t } = useTranslation()
  const { enabled, permission, setEnabled } = useReviewNudgeSetting()
  const { prefs, setPref } = useInterfacePrefsStore()

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
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t('settings.interfaceTitle')}</CardTitle>
          <CardDescription>{t('settings.interfaceDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="max-w-sm space-y-2">
          {INTERFACE_TOGGLES.map(({ key, labelKey }) => (
            <div key={key} className="flex items-center gap-2">
              <CheckIndicator
                checked={prefs[key]}
                label={t(labelKey)}
                onToggle={() => setPref(key, !prefs[key])}
              />
              <span className="text-foreground text-xs">{t(labelKey)}</span>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}
