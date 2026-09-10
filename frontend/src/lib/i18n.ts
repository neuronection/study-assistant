import i18next from 'i18next'
import { initReactI18next } from 'react-i18next'

import de from '@/locales/de.json'
import el from '@/locales/el.json'
import en from '@/locales/en.json'
import { storageKeys } from '@/lib/constants'
import { availableLocales } from '@/lib/locales'

type Catalog = { [key: string]: string | Catalog }

const catalogs: Record<string, Catalog> = { en, el, de }

export function resolveSavedLocale(): string {
  let saved: string | null = null
  try {
    saved = localStorage.getItem(storageKeys.locale)
  } catch {
    return 'en'
  }
  if (saved && availableLocales().some((locale) => locale.code === saved)) return saved
  return 'en'
}

export const initI18n = () =>
  i18next
    .use(initReactI18next)
    .init({
      lng: resolveSavedLocale(),
      fallbackLng: 'en',
      returnNull: false,
      defaultNS: 'translation',
      resources: Object.fromEntries(
        Object.entries(catalogs).map(([code, catalog]) => [code, { translation: catalog }]),
      ),
      interpolation: {
        escapeValue: false,
      },
    })
    .then(() => {
      document.documentElement.lang = i18next.resolvedLanguage ?? 'en'
    })

export async function setLocale(code: string): Promise<void> {
  localStorage.setItem(storageKeys.locale, code)
  await i18next.changeLanguage(code)
  document.documentElement.lang = i18next.resolvedLanguage ?? code
}
