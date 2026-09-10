import { ChevronRight, Home } from 'lucide-react'

import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'

export interface Crumb {
  key: string
  label: string
  onClick?: () => void
}

export function LibraryBreadcrumbs({ items }: { items: Crumb[] }) {
  const { t } = useTranslation()
  return (
    <nav
      className="border-border bg-surface flex items-center gap-0.5 rounded-md border px-2 py-1 text-sm"
      aria-label={t('library.location')}
    >
      <button
        type="button"
        className="text-muted-foreground hover:text-foreground rounded p-1"
        title={t('library.home')}
        onClick={items[0]?.onClick}
        disabled={!items[0]?.onClick}
      >
        <Home className="size-4" aria-hidden />
      </button>
      {items.map((item, index) => (
        <span key={item.key} className="flex min-w-0 items-center gap-0.5">
          <ChevronRight className="text-muted-foreground size-3 shrink-0" aria-hidden />
          <button
            type="button"
            className={cn(
              'truncate rounded px-1.5 py-0.5',
              index === items.length - 1
                ? 'text-foreground font-medium'
                : 'text-muted-foreground hover:text-foreground'
            )}
            onClick={item.onClick}
            disabled={!item.onClick}
          >
            {item.label}
          </button>
        </span>
      ))}
    </nav>
  )
}
