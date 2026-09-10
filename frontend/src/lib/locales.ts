import de from '@/locales/de.json'
import el from '@/locales/el.json'
import en from '@/locales/en.json'

export interface LocaleOption {
  code: string
  name: string
}

export const MAX_MISSING_RATIO = 0.02

export const LOCALES: LocaleOption[] = [
  { code: 'en', name: 'English' },
  { code: 'el', name: 'Ελληνικά' },
  { code: 'de', name: 'Deutsch' },
]

const catalogs: Record<string, unknown> = { en, el, de }

function flattenKeys(value: unknown, prefix = ''): string[] {
  if (typeof value !== 'object' || value === null) return []
  const keys: string[] = []
  for (const [key, child] of Object.entries(value)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (typeof child === 'string') {
      if (child.trim() !== '') keys.push(path)
    } else if (typeof child === 'object' && child !== null) {
      keys.push(...flattenKeys(child, path))
    } else {
      keys.push(path)
    }
  }
  return keys
}

const SOURCE_KEYS = new Set(flattenKeys(en))

export function missingRatio(code: string): number {
  if (!SOURCE_KEYS.size) return 0
  const present = new Set(flattenKeys(catalogs[code] ?? {}))
  let missing = 0
  for (const key of SOURCE_KEYS) {
    if (!present.has(key)) missing += 1
  }
  return missing / SOURCE_KEYS.size
}

export function availableLocales(): LocaleOption[] {
  return LOCALES.filter(
    (locale) => locale.code === 'en' || missingRatio(locale.code) <= MAX_MISSING_RATIO,
  )
}
