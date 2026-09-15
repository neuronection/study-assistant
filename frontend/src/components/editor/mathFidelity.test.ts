import { describe, expect, test } from 'vitest'

import { normalizeMathFences } from './markdownFidelity'

describe('normalizeMathFences', () => {
  test('canonical fenced blocks pass through unchanged', () => {
    const md = '$$\nI=\\int x\\,dx\n$$'
    expect(normalizeMathFences(md)).toBe(md)
  })

  test('multi-line display math with content on the fence lines is canonicalized', () => {
    const md =
      '$$I=\\int \\frac{e^x}{e^x(e^{2x}-1)}\\,dx\n\\overset{(1),(2)}{\\Rightarrow}\nI=\\int \\frac{du}{u(u^2-1)}$$'
    expect(normalizeMathFences(md)).toBe(
      '$$\nI=\\int \\frac{e^x}{e^x(e^{2x}-1)}\\,dx\n\\overset{(1),(2)}{\\Rightarrow}\nI=\\int \\frac{du}{u(u^2-1)}\n$$'
    )
  })

  test('multi-line display math with content only after the opener is canonicalized', () => {
    expect(normalizeMathFences('$$I=\\int x\\,dx\n=\\frac{x^2}2\n$$')).toBe(
      '$$\nI=\\int x\\,dx\n=\\frac{x^2}2\n$$'
    )
  })

  test('single-line display math alone on its line is canonicalized for display parity', () => {
    expect(normalizeMathFences('$$I=\\arctan(2x)+C$$')).toBe('$$\nI=\\arctan(2x)+C\n$$')
  })

  test('single-line display math inside a sentence stays inline', () => {
    const md = 'text $$x^2$$ more text'
    expect(normalizeMathFences(md)).toBe(md)
  })

  test('inline math is untouched', () => {
    const md = 'Θέτω $u=e^x \\Rightarrow du=e^x\\,dx$'
    expect(normalizeMathFences(md)).toBe(md)
  })

  test('display spans spanning a blank line are refused', () => {
    const md = '$$\n\n$$\n=\\frac12\\int x\\,dx'
    expect(normalizeMathFences(md)).toBe(md)
  })

  test('code fences and inline code are untouched', () => {
    const md = '```math\n$$x^2$$\n```\n\n`$$y^2$$`'
    expect(normalizeMathFences(md)).toBe(md)
  })

  test('escaped dollars are untouched', () => {
    const md = 'costs \\$\\$5\\$\\$ total'
    expect(normalizeMathFences(md)).toBe(md)
  })

  test('math newline separators become real newlines in canonical output', () => {
    expect(normalizeMathFences('$$a\u2063b$$')).toBe('$$\na\nb\n$$')
  })

  test('multi-line opener not at line start stays inline text', () => {
    const md = 'see: $$x\ny$$ here'
    expect(normalizeMathFences(md)).toBe(md)
  })

  test('indented single-line display math keeps its indent when canonicalized', () => {
    expect(normalizeMathFences('* item:\n  $$f(x)=1$$\n  tail')).toBe(
      '* item:\n  $$\n  f(x)=1\n  $$\n  tail'
    )
  })

  test('indented multi-line display math keeps its indent when canonicalized', () => {
    expect(normalizeMathFences('* item:\n  $$f(x)=1\n  g(x)=2$$')).toBe(
      '* item:\n  $$\n  f(x)=1\n  g(x)=2\n  $$'
    )
  })

  test('non-whitespace line prefix (blockquote) leaves the span untouched', () => {
    const md = '> $$f(x)=1$$ tail'
    expect(normalizeMathFences(md)).toBe(md)
  })
})
