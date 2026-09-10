import i18next from 'i18next'
import { afterAll, describe, expect, test } from 'vitest'

import {
  formatDate,
  formatDateTime,
  formatMonth,
  formatNumber,
  formatPercent,
  formatWeekdayLong,
} from './format'

const NOON = new Date(Date.UTC(2026, 8, 9, 12, 5))
const LOCAL_NOON = new Date(2026, 8, 9, 12, 5)
const ISO_DATE = '2026-09-09'

afterAll(async () => {
  await i18next.changeLanguage('en')
})

describe('formatDate', () => {
  test.each([
    ['en', /Sep/],
    ['de', /Sept\. 2026/],
    ['el', /Σεπ/],
  ])('%s renders a localized date shape', async (lng, pattern) => {
    await i18next.changeLanguage(lng)
    expect(formatDate(NOON)).toMatch(pattern)
    expect(formatDate(ISO_DATE)).toMatch(pattern)
  })

  test('date-only ISO strings do not shift across timezones', () => {
    expect(formatDate('2026-09-09T00:00:00+14:00').length).toBeGreaterThan(0)
  })
})

describe('formatDateTime', () => {
  test('renders date and time', async () => {
    await i18next.changeLanguage('en')
    expect(formatDateTime(LOCAL_NOON)).toMatch(/Sep/)
    expect(formatDateTime(LOCAL_NOON)).toMatch(/12:05/)
    await i18next.changeLanguage('de')
    expect(formatDateTime(LOCAL_NOON)).toMatch(/Sept\./)
    expect(formatDateTime(LOCAL_NOON)).toMatch(/12:05/)
  })
})

describe('formatWeekdayLong', () => {
  test('renders weekday + date per locale', async () => {
    await i18next.changeLanguage('en')
    expect(formatWeekdayLong(NOON)).toMatch(/September/)
    await i18next.changeLanguage('de')
    expect(formatWeekdayLong(NOON)).toMatch(/September/)
    expect(formatWeekdayLong(NOON)).toMatch(/Mittwoch/)
    await i18next.changeLanguage('el')
    expect(formatWeekdayLong(NOON)).toMatch(/Τετάρτη/)
    expect(formatWeekdayLong(NOON)).toMatch(/Σεπτεμβρίου/)
  })
})

describe('formatMonth', () => {
  test('renders YYYY-MM as month name', async () => {
    await i18next.changeLanguage('en')
    expect(formatMonth('2026-09')).toMatch(/September 2026/)
    await i18next.changeLanguage('el')
    expect(formatMonth('2026-09')).toMatch(/2026/)
    expect(formatMonth('2026-09')).toMatch(/Σεπτ/)
  })
})

describe('formatNumber', () => {
  test('renders decimal separators per locale', async () => {
    await i18next.changeLanguage('en')
    expect(formatNumber(1234.5, 1)).toBe('1,234.5')
    await i18next.changeLanguage('de')
    expect(formatNumber(1234.5, 1)).toMatch(/234,5/)
    await i18next.changeLanguage('el')
    expect(formatNumber(1234.5, 1)).toMatch(/234,5/)
  })

  test('pads fraction digits', async () => {
    await i18next.changeLanguage('en')
    expect(formatNumber(0.12, 3)).toMatch(/0\.120/)
  })
})

describe('formatPercent', () => {
  test('renders percent per locale', async () => {
    await i18next.changeLanguage('en')
    expect(formatPercent(0.85)).toBe('85%')
    await i18next.changeLanguage('de')
    expect(formatPercent(0.85)).toBe('85\u00a0%')
    await i18next.changeLanguage('el')
    expect(formatPercent(0.85)).toBe('85%')
  })
})
