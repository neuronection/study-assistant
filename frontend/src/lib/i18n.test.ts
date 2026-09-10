import i18next from 'i18next'
import { describe, expect, test } from 'vitest'

import en from '@/locales/en.json'

import { initI18n, setLocale } from './i18n'

function flattenLeaves(value: unknown, prefix: string[] = []): { key: string; text: string }[] {
  if (typeof value === 'string') {
    return [{ key: prefix.join('.'), text: value }]
  }
  if (value && typeof value === 'object') {
    return Object.entries(value).flatMap(([k, v]) => flattenLeaves(v, [...prefix, k]))
  }
  return []
}

describe('en catalog', () => {
  test('every leaf is a non-empty string', () => {
    const leaves = flattenLeaves(en)
    expect(leaves.length).toBeGreaterThan(0)
    for (const leaf of leaves) {
      expect(leaf.text.trim().length, `empty value for ${leaf.key}`).toBeGreaterThan(0)
    }
  })

  test('i18next resolves keys from the catalog', async () => {
    await initI18n()
    expect(i18next.t('app.name')).toBe('Study Assistant')
    expect(i18next.t('home.backendOnline', { version: '1.0' })).toContain('1.0')
  })

  test('saved locale is picked up and invalid values fall back to en', async () => {
    localStorage.setItem('ca-locale', 'de')
    await initI18n()
    expect(i18next.resolvedLanguage).toBe('de')
    localStorage.setItem('ca-locale', 'xx')
    await initI18n()
    expect(i18next.resolvedLanguage).toBe('en')
    localStorage.removeItem('ca-locale')
    await initI18n()
    expect(i18next.resolvedLanguage).toBe('en')
    expect(document.documentElement.lang).toBe('en')
  })

  test('missing key in current locale falls back to English value, not the key', async () => {
    await initI18n()
    const onlyEnglishKey = ['testProbe', 'onlyEnglish'].join('.')
    const missingKey = ['testProbe', 'missingEverywhere'].join('.')
    i18next.addResourceBundle(
      'en',
      'translation',
      { testProbe: { onlyEnglish: 'English only' } },
      true,
      false,
    )
    try {
      await i18next.changeLanguage('de')
      expect(i18next.t(onlyEnglishKey)).toBe('English only')
      expect(i18next.t(missingKey)).toBe(missingKey)
    } finally {
      i18next.removeResourceBundle('en', 'translation')
      await i18next.changeLanguage('en')
    }
  })

  test('setLocale persists, applies instantly and updates html lang', async () => {
    await initI18n()
    await setLocale('de')
    expect(localStorage.getItem('ca-locale')).toBe('de')
    expect(i18next.resolvedLanguage).toBe('de')
    expect(i18next.t('settings.tabs.general')).toBe('Allgemein')
    expect(document.documentElement.lang).toBe('de')
    await setLocale('el')
    expect(document.documentElement.lang).toBe('el')
    expect(i18next.t('settings.tabs.general')).toBe('Γενικά')
    await setLocale('en')
    expect(document.documentElement.lang).toBe('en')
    localStorage.removeItem('ca-locale')
  })
})
