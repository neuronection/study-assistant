import { describe, expect, test } from 'vitest'

import { fuzzyFilter, fuzzyScore } from './fuzzy'

describe('fuzzyScore', () => {
  test('empty query matches everything with score 0', () => {
    expect(fuzzyScore('', 'gemini-2.5-flash')).toBe(0)
  })

  test('exact substring scores and case is ignored', () => {
    expect(fuzzyScore('flash', 'gemini-2.5-FLASH')).not.toBeNull()
    expect(fuzzyScore('GEMINI', 'gemini-2.5-flash')).not.toBeNull()
  })

  test('subsequence matches out of order characters in sequence', () => {
    expect(fuzzyScore('g25f', 'gemini-2.5-flash')).not.toBeNull()
  })

  test('missing characters never match', () => {
    expect(fuzzyScore('gpt', 'gemini-2.5-flash')).toBeNull()
    expect(fuzzyScore('flashx', 'gemini-2.5-flash')).toBeNull()
  })

  test('boundary and consecutive bonuses rank better matches higher', () => {
    const startMatch = fuzzyScore('pro', 'pro-vision')!
    const insideMatch = fuzzyScore('pro', 'hypervisor')!
    const consecutive = fuzzyScore('pro', 'pro')!
    const scattered = fuzzyScore('pro', 'porous')!
    expect(startMatch).toBeGreaterThan(insideMatch)
    expect(consecutive).toBeGreaterThan(startMatch)
    expect(startMatch).toBeGreaterThan(scattered)
  })

  test('exact match outscores any longer target', () => {
    expect(fuzzyScore('pro', 'pro')!).toBeGreaterThan(fuzzyScore('pro', 'pro-vision')!)
  })

  test('word-start bonus after separators', () => {
    const afterDash = fuzzyScore('vi', 'flash-vision')!
    const midWord = fuzzyScore('vi', 'vision')!
    expect(afterDash).toBeGreaterThan(0)
    expect(midWord).toBeGreaterThan(0)
  })
})

describe('fuzzyFilter', () => {
  const items = [
    'gemini-2.5-flash',
    'gemini-2.5-pro',
    'gemini-2.5-flash-lite',
    'text-embedding-004',
    'claude-sonnet-4',
  ]

  test('empty query returns items unchanged', () => {
    expect(fuzzyFilter(items, '', (entry) => entry)).toEqual(items)
    expect(fuzzyFilter(items, '   ', (entry) => entry)).toEqual(items)
  })

  test('filters to subsequence matches only', () => {
    expect(fuzzyFilter(items, 'g25p', (entry) => entry)).toEqual(['gemini-2.5-pro'])
    expect(fuzzyFilter(items, 'flash', (entry) => entry)).toEqual([
      'gemini-2.5-flash',
      'gemini-2.5-flash-lite',
    ])
  })

  test('ranks by score then length then alphabetically', () => {
    expect(fuzzyFilter(items, 'pro', (entry) => entry)).toEqual(['gemini-2.5-pro'])

    const byLength = fuzzyFilter(items, '2.5', (entry) => entry)
    expect(byLength).toEqual([
      'gemini-2.5-pro',
      'gemini-2.5-flash',
      'gemini-2.5-flash-lite',
    ])

    const tie = fuzzyFilter(['b-model', 'a-model'], 'model', (entry) => entry)
    expect(tie).toEqual(['a-model', 'b-model'])
  })

  test('no match yields empty list', () => {
    expect(fuzzyFilter(items, 'zzz', (entry) => entry)).toEqual([])
  })

  test('works with object items via getText', () => {
    const objects = [{ id: 'gpt-4o' }, { id: 'llama-3' }]
    expect(fuzzyFilter(objects, '4o', (entry) => entry.id)).toEqual([{ id: 'gpt-4o' }])
  })
})
