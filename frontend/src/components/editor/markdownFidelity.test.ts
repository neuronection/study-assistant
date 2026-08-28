import { describe, expect, test } from 'vitest'

import { decodeMarkdownFromSerialize, encodeMarkdownForParse } from './markdownFidelity'

const NBSP = '\u00A0'

describe('markdownFidelity', () => {
  test('encode/decode are identity for plain content', () => {
    const md = 'para one\n\npara two'
    expect(encodeMarkdownForParse(md)).toBe(md)
    expect(decodeMarkdownFromSerialize(md)).toBe(md)
  })

  test('blank-line stuffing never touches fenced code bodies', () => {
    const md = 'para\n\n\n\n```mermaid\nflowchart TD\n\n\n    A-->B\n```\n\ntail'
    expect(encodeMarkdownForParse(md)).toBe(
      `para\n\n${'&nbsp;'}\n\n${'&nbsp;'}\n\n\`\`\`mermaid\nflowchart TD\n\n\n    A-->B\n\`\`\`\n\ntail`
    )
  })

  test('interior blank-line runs encode to nbsp paragraphs', () => {
    expect(encodeMarkdownForParse('a\n\n\nb')).toBe('a\n\n&nbsp;\n\nb')
    expect(encodeMarkdownForParse('a\n\n\n\n\nb')).toBe(
      'a\n\n&nbsp;\n\n&nbsp;\n\n&nbsp;\n\nb'
    )
    expect(encodeMarkdownForParse('a\n\nb')).toBe('a\n\nb')
  })

  test('leading and trailing empty lines are deleted on encode', () => {
    expect(encodeMarkdownForParse('\n\n\nfirst\n\n')).toBe('first')
    expect(encodeMarkdownForParse('\nfirst\n')).toBe('first')
    expect(encodeMarkdownForParse('\n\n\na\n\n\n\nb\n\n\n')).toBe(
      'a\n\n&nbsp;\n\n&nbsp;\n\nb'
    )
  })

  test('interior serialized nbsp paragraphs decode back to blank runs', () => {
    expect(decodeMarkdownFromSerialize(`a\n\n${NBSP}\n\nb`)).toBe('a\n\n\nb')
    expect(decodeMarkdownFromSerialize(`a\n\n${NBSP}\n\n${NBSP}\n\nb`)).toBe(
      'a\n\n\n\nb'
    )
    expect(decodeMarkdownFromSerialize(`a\n\n${NBSP}\n\n${NBSP}\n\n${NBSP}\n\nb`)).toBe(
      'a\n\n\n\n\nb'
    )
  })

  test('leading and trailing empty paragraphs are deleted on decode', () => {
    expect(decodeMarkdownFromSerialize(`${NBSP}\n\nleading`)).toBe('leading')
    expect(decodeMarkdownFromSerialize(`${NBSP}\n\n${NBSP}\n\nleading`)).toBe('leading')
    expect(decodeMarkdownFromSerialize('trailing\n\n' + NBSP)).toBe('trailing')
    expect(decodeMarkdownFromSerialize(`trailing\n\n${NBSP}\n\n${NBSP}`)).toBe('trailing')
    expect(decodeMarkdownFromSerialize(NBSP)).toBe('')
  })

  test('in-paragraph hard breaks and single blank lines are untouched', () => {
    expect(decodeMarkdownFromSerialize('line1\\\nline2\n\npara two')).toBe(
      'line1\\\nline2\n\npara two'
    )
    expect(encodeMarkdownForParse('a\n\nb')).toBe('a\n\nb')
    expect(decodeMarkdownFromSerialize('a\n\nb')).toBe('a\n\nb')
  })

  test('inline math backslashes are doubled on encode; decode is passthrough', () => {
    expect(encodeMarkdownForParse('value $\\frac{1}{2}$ and $\\alpha$')).toBe(
      'value $\\\\frac{1}{2}$ and $\\\\alpha$'
    )
    expect(decodeMarkdownFromSerialize('value $\\\\frac{1}{2}$ and $\\\\alpha$')).toBe(
      'value $\\\\frac{1}{2}$ and $\\\\alpha$'
    )
  })

  test('display math backslashes are doubled and newlines cloaked on encode', () => {
    expect(encodeMarkdownForParse('$$\\int_0^1 f(x)\\,dx$$')).toBe(
      '$$\\\\int_0^1 f(x)\\\\,dx$$'
    )
    expect(encodeMarkdownForParse('$$\n\\int_0^1 f(x)\\,dx\n$$')).toBe(
      `$$${'\u2063'}\\\\int_0^1 f(x)\\\\,dx${'\u2063'}$$`
    )
  })

  test('genuine latex line breaks are doubled on encode', () => {
    expect(encodeMarkdownForParse('$$a \\\\ b$$')).toBe('$$a \\\\\\\\ b$$')
  })

  test('escaped pipes inside math stay escaped on encode so tables keep one cell', () => {
    expect(encodeMarkdownForParse('$a\\|b$')).toBe('$a\\|b$')
    expect(encodeMarkdownForParse('$\\frac{a}{b}$')).toBe('$\\\\frac{a}{b}$')
  })

  test('currency dollars without a closing delimiter stay literal', () => {
    const md = 'costs $5 and $10 total'
    expect(encodeMarkdownForParse(md)).toBe(md)
    expect(decodeMarkdownFromSerialize(md)).toBe(md)
    const spaced = 'price of $5 and $ down'
    expect(encodeMarkdownForParse(spaced)).toBe(spaced)
  })

  test('math inside code spans and fences is untouched', () => {
    const fenced = 'text\n\n```\n$x^2$ and \\int\n```\n\nafter'
    expect(encodeMarkdownForParse(fenced)).toBe(fenced)
    expect(decodeMarkdownFromSerialize(fenced)).toBe(fenced)
    const inline = 'run `$\\alpha$` now'
    expect(encodeMarkdownForParse(inline)).toBe(inline)
    expect(decodeMarkdownFromSerialize(inline)).toBe(inline)
  })

  test('escaped dollars do not open math spans', () => {
    const md = 'paid \\$5 and \\$10 here'
    expect(encodeMarkdownForParse(md)).toBe(md)
    expect(decodeMarkdownFromSerialize(md)).toBe(md)
  })

  test('unterminated display math stays literal', () => {
    const md = 'odd $$ amount'
    expect(encodeMarkdownForParse(md)).toBe(md)
    expect(decodeMarkdownFromSerialize(md)).toBe(md)
  })
})
