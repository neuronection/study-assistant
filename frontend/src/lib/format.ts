import i18next from 'i18next'

export type DateInput = string | number | Date

const DATE_ONLY_RE = /^\d{4}-\d{2}-\d{2}$/

function currentLocale(): string {
  return i18next.resolvedLanguage ?? 'en'
}

function toDate(value: DateInput): Date {
  if (value instanceof Date) return value
  if (typeof value === 'string' && DATE_ONLY_RE.test(value)) {
    return new Date(`${value}T00:00:00`)
  }
  return new Date(value)
}

export function formatDate(value: DateInput): string {
  return new Intl.DateTimeFormat(currentLocale(), {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(toDate(value))
}

export function formatDateTime(value: DateInput): string {
  return new Intl.DateTimeFormat(currentLocale(), {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(toDate(value))
}

export function formatWeekdayLong(value: DateInput): string {
  return new Intl.DateTimeFormat(currentLocale(), {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  }).format(toDate(value))
}

export function formatRelativeTime(timestamp: number): string {
  const formatter = new Intl.RelativeTimeFormat(currentLocale(), { numeric: 'auto' })
  const deltaMinutes = Math.round((timestamp - Date.now()) / 60000)
  if (Math.abs(deltaMinutes) < 60) {
    return formatter.format(deltaMinutes, 'minute')
  }
  const deltaHours = Math.round(deltaMinutes / 60)
  if (Math.abs(deltaHours) < 24) {
    return formatter.format(deltaHours, 'hour')
  }
  const deltaDays = Math.round(deltaHours / 24)
  if (Math.abs(deltaDays) < 7) {
    return formatter.format(deltaDays, 'day')
  }
  return formatDate(timestamp)
}

export function formatMonth(month: string): string {
  const [year, part] = month.split('-')
  const date = new Date(Number(year), Number(part) - 1, 1)
  return new Intl.DateTimeFormat(currentLocale(), {
    year: 'numeric',
    month: 'long',
  }).format(date)
}

export function formatNumber(value: number, fractionDigits = 0): string {
  return new Intl.NumberFormat(currentLocale(), {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value)
}

export function formatPercent(value: number, fractionDigits = 0): string {
  return new Intl.NumberFormat(currentLocale(), {
    style: 'percent',
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value)
}
