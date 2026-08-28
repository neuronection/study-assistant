import { Search, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export function SearchInput({
  value,
  onChange,
  onSubmit,
  placeholder,
  ariaLabel,
  autoFocus = false,
  clearLabel,
}: {
  value: string
  onChange: (value: string) => void
  onSubmit?: (value: string) => void
  placeholder: string
  ariaLabel: string
  autoFocus?: boolean
  clearLabel?: string
}) {
  const { t } = useTranslation()
  return (
    <form
      className="border-border bg-surface flex items-center gap-2 rounded-md border px-3 py-2"
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit?.(value)
      }}
    >
      <Search className="text-muted-foreground size-4 shrink-0" aria-hidden />
      <input
        autoFocus={autoFocus}
        className="min-w-0 flex-1 bg-transparent text-sm outline-none"
        placeholder={placeholder}
        aria-label={ariaLabel}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      {value ? (
        <button
          type="button"
          onClick={() => onChange('')}
          aria-label={clearLabel ?? t('common.clearSearch')}
        >
          <X className="text-muted-foreground size-4" aria-hidden />
        </button>
      ) : null}
    </form>
  )
}
