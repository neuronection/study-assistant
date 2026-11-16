import i18next from 'i18next'
import { initReactI18next } from 'react-i18next'

import en from '@/locales/en.json'
import { storageKeys } from '@/lib/constants'
import { availableLocales } from '@/lib/locales'

type Catalog = { [key: string]: string | Catalog }

const lazyCatalogs: Record<string, () => Promise<Catalog>> = {
  de: () => import('@/locales/de.json').then((module) => module.default as Catalog),
  el: () => import('@/locales/el.json').then((module) => module.default as Catalog),
}

async function loadCatalog(code: string): Promise<Catalog | null> {
  const loader = lazyCatalogs[code]
  return loader === undefined ? null : loader()
}

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

export const initI18n = async () => {
  const locale = resolveSavedLocale()
  const resources: Record<string, { translation: Catalog }> = {
    en: { translation: en as Catalog },
  }
  if (locale !== 'en') {
    const catalog = await loadCatalog(locale)
    if (catalog !== null) {
      resources[locale] = { translation: catalog }
    }
  }
  await i18next.use(initReactI18next).init({
    lng: locale,
    fallbackLng: 'en',
    returnNull: false,
    defaultNS: 'translation',
    resources,
    interpolation: {
      escapeValue: false,
    },
  })
  document.documentElement.lang = i18next.resolvedLanguage ?? 'en'
}

export async function setLocale(code: string): Promise<void> {
  localStorage.setItem(storageKeys.locale, code)
  if (code !== 'en' && !i18next.hasResourceBundle(code, 'translation')) {
    const catalog = await loadCatalog(code)
    if (catalog !== null) {
      i18next.addResourceBundle(code, 'translation', catalog, true, true)
    }
  }
  await i18next.changeLanguage(code)
  document.documentElement.lang = i18next.resolvedLanguage ?? code
}
