import { describe, expect, test } from 'vitest'

import {
  MAX_MISSING_RATIO,
  LOCALES,
  availableLocales,
  missingRatio,
} from './locales'

describe('locale manifest', () => {
  test('English is always the source and always available', () => {
    expect(LOCALES[0]?.code).toBe('en')
    expect(availableLocales().some((locale) => locale.code === 'en')).toBe(true)
  })

  test('missingRatio is 0 for the source locale and 1 for unknown locales', () => {
    expect(missingRatio('en')).toBe(0)
    expect(missingRatio('xx')).toBe(1)
  })

  test('shipped locales stay above the picker threshold', () => {
    expect(missingRatio('el')).toBeLessThanOrEqual(MAX_MISSING_RATIO)
    expect(missingRatio('de')).toBeLessThanOrEqual(MAX_MISSING_RATIO)
    const codes = availableLocales().map((locale) => locale.code)
    expect(codes).toContain('el')
    expect(codes).toContain('de')
  })

  test('native names are not translated', () => {
    const el = LOCALES.find((locale) => locale.code === 'el')
    expect(el?.name).toBe('Ελληνικά')
  })
})
