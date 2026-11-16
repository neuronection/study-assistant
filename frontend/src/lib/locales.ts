import { findLanguage } from '@neuronection/assistant-ui/languages'

export interface LocaleOption {
  code: string
  name: string
  flag?: string
}

export const MAX_MISSING_RATIO = 0.02

/** Locale registry: which dictionaries ship. Display names and flags come
 * from the shared language catalog (ADR-0024) — endonyms, no local list.
 * Completeness is enforced by `i18n-audit.test.ts`; the shell must not
 * import the dictionaries themselves (plan 101-D). */
export const LOCALES: LocaleOption[] = (['en', 'el', 'de'] as const).map((code) => {
  const language = findLanguage(code)
  return {
    code,
    name: language?.nativeName ?? code,
    flag: language?.flag,
  }
})

export function availableLocales(): LocaleOption[] {
  return [...LOCALES]
}
