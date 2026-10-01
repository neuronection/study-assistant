import { describe, expect, test } from 'vitest'

import { remapDrawingRefsInMarkdown } from '@/lib/api'

describe('remapDrawingRefsInMarkdown', () => {
  test('remaps placeholder refs to real ids preserving alt text', () => {
    const mapping: Record<number, number> = {}
    mapping[-1] = 11
    mapping[-2] = 12
    const md = 'a ![drawing](sa-drawing://-1) b ![sketch](sa-drawing://-2) c'
    expect(remapDrawingRefsInMarkdown(md, mapping)).toBe(
      'a ![drawing](sa-drawing://11) b ![sketch](sa-drawing://12) c'
    )
  })

  test('leaves refs without a mapping untouched', () => {
    expect(remapDrawingRefsInMarkdown('x ![drawing](sa-drawing://-1)', { '-1': 7 } as Record<number, number>)).toBe(
      'x ![drawing](sa-drawing://7)'
    )
    expect(remapDrawingRefsInMarkdown('x ![drawing](sa-drawing://-9)', { '-1': 7 } as Record<number, number>)).toBe(
      'x ![drawing](sa-drawing://-9)'
    )
  })
})