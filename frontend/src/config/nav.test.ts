import { describe, expect, it } from 'vitest'
import { GraduationCap, Home } from 'lucide-react'
import { PRIMARY_NAV, resolveActiveId, type AppNavItem } from './nav'

describe('resolveActiveId', () => {
  it('matches the root only exactly', () => {
    expect(resolveActiveId('/')).toBe('/')
    expect(resolveActiveId('/courses')).not.toBe('/')
  })

  it('matches prefix entries, including nested paths', () => {
    expect(resolveActiveId('/library')).toBe('/library')
    expect(resolveActiveId('/library/imports')).toBe('/library')
    expect(resolveActiveId('/courses/12/materials')).toBe('/courses')
  })

  it('returns null for unknown paths', () => {
    expect(resolveActiveId('/nowhere')).toBeNull()
  })

  it('prefers the longest prefix', () => {
    const nav: AppNavItem[] = [
      { to: '/a', icon: Home, labelKey: 'x', exact: false },
      { to: '/a/b', icon: GraduationCap, labelKey: 'y', exact: false },
    ]
    expect(resolveActiveId('/a/b/x', nav)).toBe('/a/b')
    expect(resolveActiveId('/a/z', nav)).toBe('/a')
  })

  it('respects exact flags over prefix logic', () => {
    const nav: AppNavItem[] = [
      { to: '/a', icon: Home, labelKey: 'x', exact: true },
    ]
    expect(resolveActiveId('/a/b', nav)).toBeNull()
  })

  it('primary registry keeps its shape', () => {
    expect(PRIMARY_NAV.map((item) => item.to)).toEqual([
      '/',
      '/courses',
      '/chat',
      '/library',
      '/scores',
    ])
    expect(PRIMARY_NAV.every((item) => item.labelKey.startsWith('nav.'))).toBe(true)
  })
})
