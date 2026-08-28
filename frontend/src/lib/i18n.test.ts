import i18next from 'i18next'
import { describe, expect, test } from 'vitest'

import en from '@/locales/en.json'

import { initI18n } from './i18n'

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
})
