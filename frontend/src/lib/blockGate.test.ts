import { describe, expect, test, vi } from 'vitest'

import {
  extractBlock,
  gateResult,
  validateMathSource,
} from './blockGate'

vi.mock('mermaid', () => ({
  default: {
    parse: vi.fn(async (code: string) => {
      if (code.includes('BAD')) {
        throw new Error('Parse error on line 2')
      }
      return { diagramType: {} }
    }),
  },
}))

describe('blockGate', () => {
  test('extractBlock finds a mermaid fence and returns its source', () => {
    const md = 'intro\n\n```mermaid\nflowchart TD\n  A --> B\n```\n\ntail'
    expect(extractBlock('mermaid', md)).toEqual({
      source: 'flowchart TD\n  A --> B',
      display: false,
    })
  })

  test('extractBlock ignores mermaid-ish content inside other fences', () => {
    const md = '```\n```mermaid\nnot one\n```\n```'
    expect(extractBlock('mermaid', md)).toBeNull()
  })

  test('extractBlock finds inline and display math spans', () => {
    expect(extractBlock('math', 'value $\\frac{1}{2}$ here')).toEqual({
      source: '\\frac{1}{2}',
      display: false,
    })
    expect(extractBlock('math', '$$\n\\int_0^1\n$$')).toEqual({
      source: '\n\\int_0^1\n',
      display: true,
    })
  })

  test('extractBlock skips dollars inside code fences', () => {
    expect(extractBlock('math', '```\n$\\alpha$\n```')).toBeNull()
  })

  test('validateMathSource accepts valid latex and reports katex errors', async () => {
    const ok = validateMathSource('\\frac{1}{2}')
    expect(ok.ok).toBe(true)
    const bad = validateMathSource('\\frac{1}')
    expect(bad.ok).toBe(false)
    expect(bad.error).toContain('\\frac')
  })

  test('gateResult validates the extracted block source', async () => {
    const ok = await gateResult('mermaid', '```mermaid\nflowchart TD\n  A --> B\n```')
    expect(ok.ok).toBe(true)
    const failed = await gateResult('mermaid', '```mermaid\nBAD line\n```')
    expect(failed.ok).toBe(false)
    expect(failed.error).toContain('Parse error')
    const missing = await gateResult('mermaid', 'plain text only')
    expect(missing).toEqual({ ok: false, error: 'block-not-found' })
  })

  test('gateResult enforces the math span delimiters it finds', async () => {
    const ok = await gateResult('math', '$$\\frac{1}{2}$$')
    expect(ok.ok).toBe(true)
    const failed = await gateResult('math', '$\\frac{1}$')
    expect(failed.ok).toBe(false)
  })
})
