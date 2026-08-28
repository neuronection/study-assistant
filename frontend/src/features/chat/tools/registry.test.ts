import { describe, expect, test } from 'vitest'

import { formatDuration, getToolMeta, getToolView } from './registry'

describe('tool registry', () => {
  test('resolves known tool metadata', () => {
    expect(getToolMeta('CALC').labelKey).toBe('chat.tool.calc')
    expect(getToolMeta('SYMPY').labelKey).toBe('chat.tool.sympy')
    expect(getToolMeta('READ').labelKey).toBe('chat.tool.read')
    expect(getToolMeta('STATE').labelKey).toBe('chat.tool.state')
    expect(getToolMeta('PLOT').labelKey).toBe('chat.tool.plot')
  })

  test('falls back to a generic meta for unknown tools', () => {
    const meta = getToolMeta('SOMETHING_ELSE')
    expect(meta.labelKey).toBeNull()
    expect(meta.phase).toBe('computing')
  })

  test('every tool has a view renderer', () => {
    for (const name of ['CALC', 'SYMPY', 'READ', 'STATE', 'PLOT', 'UNKNOWN']) {
      expect(typeof getToolView(name)).toBe('function')
    }
  })
})

describe('formatDuration', () => {
  test('formats sub-second durations in milliseconds', () => {
    expect(formatDuration(0)).toBe('0 ms')
    expect(formatDuration(500)).toBe('500 ms')
    expect(formatDuration(999)).toBe('999 ms')
  })

  test('formats seconds with one decimal below ten seconds', () => {
    expect(formatDuration(1000)).toBe('1.0 s')
    expect(formatDuration(2500)).toBe('2.5 s')
    expect(formatDuration(9999)).toBe('10.0 s')
  })

  test('formats whole seconds above ten seconds', () => {
    expect(formatDuration(12_000)).toBe('12 s')
  })

  test('returns null for missing values', () => {
    expect(formatDuration(null)).toBeNull()
    expect(formatDuration(undefined)).toBeNull()
  })
})
