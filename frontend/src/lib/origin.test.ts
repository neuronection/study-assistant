import { describe, expect, test } from 'vitest'

import { parseOrigin, practiceFallback } from './origin'

describe('parseOrigin', () => {
  test('accepts an in-app path with search', () => {
    expect(parseOrigin('/courses/3/n/7?tab=practice')).toBe('/courses/3/n/7?tab=practice')
  })

  test('rejects non-strings, empties and malformed encoding', () => {
    expect(parseOrigin(undefined)).toBeNull()
    expect(parseOrigin(42)).toBeNull()
    expect(parseOrigin('')).toBeNull()
    expect(parseOrigin('%E0%A4%A')).toBeNull()
  })

  test('rejects non-path targets (absolute urls, protocol-relative, schemes)', () => {
    expect(parseOrigin('https://evil.example')).toBeNull()
    expect(parseOrigin('//evil.example')).toBeNull()
    expect(parseOrigin(encodeURIComponent('//evil.example'))).toBeNull()
    expect(parseOrigin('javascript:alert(1)')).toBeNull()
    expect(parseOrigin('courses/3')).toBeNull()
  })
})

describe('practiceFallback', () => {
  test('derives the node workspace practice tab', () => {
    expect(practiceFallback(3, 7)).toBe('/courses/3/n/7?tab=practice')
  })

  test('root placement falls back to the course workspace', () => {
    expect(practiceFallback(3, null)).toBe('/courses/3?tab=practice')
  })

  test('course-less objects fall back to the courses list', () => {
    expect(practiceFallback(null, null)).toBe('/courses')
    expect(practiceFallback(undefined, undefined)).toBe('/courses')
  })
})
