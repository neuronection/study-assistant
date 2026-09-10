import { describe, expect, test } from 'vitest'

import { fuzzyFilter, fuzzyScore, searchScore } from './fuzzy'

describe('fuzzy adapter (library searchScore)', () => {
  test('empty query matches everything with score 0', () => {
    expect(fuzzyScore('', 'gemini-2.5-flash')).toBe(0)
    expect(searchScore('', 'anything')).toBe(0)
  })

  test('exact substring scores and case is ignored', () => {
    expect(searchScore('flash', 'gemini-2.5-FLASH')).not.toBeNull()
    expect(searchScore('GEMINI', 'gemini-2.5-flash')).not.toBeNull()
  })

  test('subsequence matches out of order characters in sequence', () => {
    expect(searchScore('g25f', 'gemini-2.5-flash')).not.toBeNull()
  })

  test('missing characters never fuzzy-match', () => {
    expect(searchScore('gpt', 'gemini-2.5-flash')).toBeNull()
  })

  test('typo tolerance: one edit on a long-enough word still matches (library contract)', () => {
    expect(searchScore('flashx', 'gemini-2.5-flash')).not.toBeNull()
    expect(searchScore('flssh', 'flash')).not.toBeNull()
  })

  test('boundary and consecutive bonuses rank better matches higher', () => {
    const startMatch = searchScore('pro', 'pro-vision')!
    const insideMatch = searchScore('pro', 'hypervisor')!
    const scattered = searchScore('pro', 'porous')!
    expect(startMatch).toBeGreaterThan(insideMatch)
    expect(startMatch).toBeGreaterThan(scattered)
  })

  test('exact match outscores any longer target', () => {
    expect(searchScore('pro', 'pro')!).toBeGreaterThan(searchScore('pro', 'pro-vision')!)
  })
})

describe('fuzzyFilter', () => {
  const items = [
    { id: 1, title: 'Chain rule basics' },
    { id: 2, title: 'Integration by parts' },
    { id: 3, title: 'chain-chain-chain' },
  ]

  test('empty query returns all items unfiltered', () => {
    expect(fuzzyFilter(items, '  ', (item) => item.title)).toEqual(items)
  })

  test('filters non-matches and ranks best matches first', () => {
    const result = fuzzyFilter(items, 'chain rule', (item) => item.title)
    expect(result[0]?.id).toBe(1)
    expect(result).toHaveLength(1)
  })

  test('shorter text wins score ties', () => {
    const result = fuzzyFilter(items, 'chain', (item) => item.title)
    expect(result[0]?.id).toBe(1)
  })
})
