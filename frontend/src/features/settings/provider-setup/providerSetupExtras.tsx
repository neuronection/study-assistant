import { Banknote, House } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Combobox } from '@/components/ui/combobox'
import { COUNTRIES, countryDisplayName } from '@neuronection/assistant-ui/countries'

export function HostingToggle({
  local,
  onChange,
  disabled,
}: {
  local: boolean
  onChange: (local: boolean) => void
  disabled?: boolean
}) {
  const { t } = useTranslation()
  return (
    <div className="space-y-1">
      <span className="text-muted-foreground block text-sm">{t('settings.hosting')}</span>
      <div className="grid grid-cols-2 gap-2" role="group" aria-label={t('settings.hosting')}>
        {(
          [
            [true, t('settings.localKind'), House],
            [false, t('settings.cloudKind'), Banknote],
          ] as const
        ).map(([value, label, Icon]) => (
          <button
            key={label}
            type="button"
            aria-pressed={local === value}
            disabled={disabled}
            onClick={() => onChange(value)}
            className={`flex items-center justify-center gap-2 rounded-lg border px-3 py-2 text-sm transition ${
              local === value
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-border bg-surface text-muted-foreground hover:bg-subtle'
            }`}
          >
            <Icon className="size-4" aria-hidden />
            {label}
          </button>
        ))}
      </div>
    </div>
  )
}

export function CountrySelect({
  country,
  onChange,
}: {
  country: string
  onChange: (country: string) => void
}) {
  const { t, i18n } = useTranslation()
  const locale = i18n.resolvedLanguage ?? 'en'
  const options = COUNTRIES.map((entry) => ({
    value: entry.code,
    label: `${entry.flag} ${countryDisplayName(entry.code, locale)}`,
  }))
  return (
    <Combobox
      options={options}
      value={country}
      onChange={onChange}
      label={t('settings.country')}
      placeholder={t('settings.countryPlaceholder')}
      searchPlaceholder={t('settings.countrySearch')}
      searchLabel={t('settings.countrySearch')}
      emptyLabel={t('settings.countryEmpty')}
      clearable
      clearLabel={t('settings.countryClear')}
    />
  )
}
