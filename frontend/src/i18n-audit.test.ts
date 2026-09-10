import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, test } from 'vitest'

import de from './locales/de.json'
import el from './locales/el.json'
import catalog from './locales/en.json'

const literals: Record<string, unknown> = catalog

const COVERED_SURFACES = [
  'app',
  'nav',
  'footer',
  'common',
  'theme',
  'courses',
  'library',
  'notes',
  'practice',
  'cards',
  'planner',
  'chat',
  'settings',
  'print',
] as const

const SHIPPED_LOCALES: Record<string, unknown> = { el, de }

function resolveKey(path: string): boolean {
  let current: unknown = literals
  for (const segment of path.split('.')) {
    if (typeof current !== 'object' || current === null) {
      return false
    }
    current = (current as Record<string, unknown>)[segment]
  }
  return current !== undefined
}

function keyExists(key: string): boolean {
  if (resolveKey(key)) {
    return true
  }
  return resolveKey(`${key}_one`) && resolveKey(`${key}_other`)
}

function collectFiles(dir: string): string[] {
  const entries: string[] = []
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) {
      entries.push(...collectFiles(full))
    } else if (/\.(tsx?)$/.test(name)) {
      entries.push(full)
    }
  }
  return entries
}

const tCallPattern = /\bt\(\s*['"]([a-zA-Z0-9_.]+)['"]/g
const srcRoot = join(__dirname)

describe('translation catalog completeness', () => {
  test('every static t() key exists in en.json', () => {
    const missing: string[] = []
    for (const file of collectFiles(srcRoot)) {
      const source = readFileSync(file, 'utf8')
      for (const match of source.matchAll(tCallPattern)) {
        const key = match[1]
        if (!keyExists(key)) {
          missing.push(`${file.replace(srcRoot, '')}: ${key}`)
        }
      }
    }
    expect(missing.sort()).toEqual([])
  })

  test.each(Object.keys(SHIPPED_LOCALES))(
    'covered surfaces are fully translated in %s',
    (locale) => {
      const target = SHIPPED_LOCALES[locale] as Record<string, unknown>
      const missing: string[] = []
      for (const surface of COVERED_SURFACES) {
        const sourceKeys = flatten(catalog[surface] ?? {}, surface)
        const targetKeys = new Set(flatten(target[surface] ?? {}, surface))
        for (const key of sourceKeys) {
          if (!targetKeys.has(key)) missing.push(`${locale}: ${key}`)
        }
      }
      expect(missing.sort()).toEqual([])
    },
  )
})

function flatten(value: unknown, prefix: string): string[] {
  if (typeof value === 'string') return [prefix]
  if (value && typeof value === 'object') {
    return Object.entries(value).flatMap(([key, child]) =>
      flatten(child, `${prefix}.${key}`),
    )
  }
  return []
}
