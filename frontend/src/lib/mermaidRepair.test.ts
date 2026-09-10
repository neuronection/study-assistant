import { describe, expect, test } from 'vitest'

import { repairMermaidSource } from './mermaidRepair'

describe('repairMermaidSource', () => {
  test('quotes unquoted double-circle labels containing parens (material 36 case)', () => {
    const broken = 'flowchart LR\n    O((O)) -->|v| P((v: (a,b)))'
    expect(repairMermaidSource(broken)).toBe(
      'flowchart LR\n    O((O)) -->|v| P(("v: (a,b)"))'
    )
  })

  test('quotes square-bracket labels containing parens', () => {
    expect(repairMermaidSource('A[loop (x)] --> B')).toBe(
      'A["loop (x)"] --> B'
    )
  })

  test('quotes labels containing colons', () => {
    expect(repairMermaidSource('A((x: y))')).toBe('A(("x: y"))')
  })

  test('already-quoted labels are untouched', () => {
    const code = 'A(("v: (a,b)")) --> B["plain"]'
    expect(repairMermaidSource(code)).toBeNull()
  })

  test('labels without risky characters are untouched', () => {
    const code = 'flowchart TB\n    A["Complex plane"] --> B((z))'
    expect(repairMermaidSource(code)).toBeNull()
  })

  test('quoted strings are copied verbatim', () => {
    const code = 'A["say (hi): ok"] --> B'
    expect(repairMermaidSource(code)).toBeNull()
  })

  test('comments and edges are untouched', () => {
    const code = '%% note (with parens)\nA -->|edge: label| B'
    expect(repairMermaidSource(code)).toBeNull()
  })

  test('unbalanced delimiters are left alone', () => {
    const code = 'A((oops\nB --> C'
    expect(repairMermaidSource(code)).toBeNull()
  })
})
