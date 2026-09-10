import { useTranslation } from 'react-i18next'

import { Combobox, type ComboboxOption } from '@/components/ui/combobox'
import { setLocale } from '@/lib/i18n'
import { availableLocales } from '@/lib/locales'

export function LanguagePicker({ className }: { className?: string }) {
  const { t, i18n } = useTranslation()
  const current = i18n.resolvedLanguage ?? 'en'
  const options: ComboboxOption[] = availableLocales().map((locale) => ({
    value: locale.code,
    label: locale.name,
  }))

  return (
    <Combobox
      className={className}
      label={t('settings.languageLabel')}
      options={options}
      value={current}
      onChange={(next) => void setLocale(next)}
      placeholder={t('settings.languagePlaceholder')}
      searchPlaceholder={t('settings.languageSearch')}
      searchLabel={t('settings.languageSearch')}
      emptyLabel={t('settings.languageEmpty')}
    />
  )
}
