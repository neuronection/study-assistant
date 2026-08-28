import { describe, expect, test } from 'vitest'

import {
  addChildNode,
  addRootNode,
  editNodeLabel,
  parseMindmap,
  removeNode,
  serialize,
  stripInlineMarkdown,
} from './mindmapTree'

const MD = '# Limits map\n\n- Definition\n  - epsilon-delta\n  - one-sided\n- Limit laws\n  - sum\n  - product\n- L\u0027Hopital\u0027s rule\n  - 0/0 form\n'

describe('mindmapTree', () => {
  test('parses the outline into a tree with line ranges', () => {
    const { titleLine, roots } = parseMindmap(MD)
    expect(titleLine).toBe(0)
    expect(roots.map((node) => node.label)).toEqual([
      'Definition',
      'Limit laws',
      "L'Hopital's rule",
    ])
    const def = roots[0]
    expect(def.children.map((child) => child.label)).toEqual(['epsilon-delta', 'one-sided'])
    expect(def.startLine).toBe(2)
    expect(def.endLine).toBe(5)
  })

  test('edits a label while preserving its marker and indentation', () => {
    const { lines, roots } = parseMindmap(MD)
    const result = editNodeLabel(lines, roots[2], 'Hopital rule')
    expect(result[8]).toBe('- Hopital rule')
  })

  test('removes a node and its subtree', () => {
    const { lines, roots } = parseMindmap(MD)
    const result = removeNode(lines, roots[1])
    expect(result.join('\n')).not.toContain('Limit laws')
    expect(result.join('\n')).not.toContain('  - sum')
    expect(result.join('\n')).toContain("L'Hopital's rule")
  })

  test('adds a child under a node', () => {
    const { lines, roots } = parseMindmap(MD)
    const result = addChildNode(lines, roots[0], 'formal definition')
    const reparsed = parseMindmap(serialize(result))
    expect(reparsed.roots[0].children.map((child) => child.label)).toEqual([
      'epsilon-delta',
      'one-sided',
      'formal definition',
    ])
    expect(result[5]).toBe('  - formal definition')
  })

  test('adds a root bullet after the last content line', () => {
    const { lines } = parseMindmap(MD)
    const result = addRootNode(lines, 'Continuity')
    const reparsed = parseMindmap(serialize(result))
    expect(reparsed.roots.map((node) => node.label)).toContain('Continuity')
    expect(result[result.indexOf('- Continuity') - 1]).not.toBe('')
  })

  test('serialize joins lines back to markdown', () => {
    const { lines } = parseMindmap(MD)
    expect(serialize(lines)).toBe(MD)
  })
})

describe('stripInlineMarkdown', () => {
  test('removes bold, italic, code, links, latex and strikethrough', () => {
    expect(stripInlineMarkdown('**chain rule**')).toBe('chain rule')
    expect(stripInlineMarkdown('*epsilon* delta')).toBe('epsilon delta')
    expect(stripInlineMarkdown('use `sympy` here')).toBe('use sympy here')
    expect(stripInlineMarkdown('[limits](https://x.com)')).toBe('limits')
    expect(stripInlineMarkdown('derivative $f\u0027(x)$')).toBe('derivative f\u0027(x)')
    expect(stripInlineMarkdown('~~wrong~~ answer')).toBe('wrong answer')
  })

  test('keeps plain text intact', () => {
    expect(stripInlineMarkdown("L'Hopital's rule")).toBe("L'Hopital's rule")
  })
})
