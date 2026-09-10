import { describe, expect, test, vi } from 'vitest'
import type { TFunction } from 'i18next'

const copyText = vi.fn<(value: string) => Promise<boolean>>(async () => true)

vi.mock('@/lib/clipboard', () => ({
  copyText: (value: string) => copyText(value),
}))

import { blockActionItems, fencedCode, mathMarkdown, tableToMarkdown } from './blockCopy'
import type { Block } from './types'

const t = ((key: string) => key) as unknown as TFunction

describe('mathMarkdown', () => {
  test('inline math wraps in single dollars', () => {
    expect(mathMarkdown({ type: 'math', latex: 'x^2' })).toBe('$x^2$')
  })

  test('display math wraps in double dollars', () => {
    expect(mathMarkdown({ type: 'math', latex: 'x^2', display: true })).toBe('$$x^2$$')
  })
})

describe('fencedCode', () => {
  test('uses the language when present', () => {
    expect(fencedCode({ type: 'code', lang: 'python', code: 'print(1)' })).toBe(
      '```python\nprint(1)\n```'
    )
  })

  test('omits the language when absent', () => {
    expect(fencedCode({ type: 'code', code: 'x' })).toBe('```\nx\n```')
  })
})

describe('tableToMarkdown', () => {
  test('serializes header, separator and rows', () => {
    expect(tableToMarkdown([['a', 'b'], ['1', '2']])).toBe('| a | b |\n| --- | --- |\n| 1 | 2 |')
  })

  test('escapes pipes and flattens newlines in cells', () => {
    expect(tableToMarkdown([['x | y'], ['line\nbreak']])).toBe(
      '| x \\| y |\n| --- |\n| line break |'
    )
  })

  test('empty rows yield an empty string', () => {
    expect(tableToMarkdown([])).toBe('')
  })
})

describe('blockActionItems', () => {
  test('math copies raw LaTeX and delimiter-wrapped markdown', async () => {
    const items = blockActionItems({ type: 'math', latex: 'e^x', display: true }, t)
    expect(items?.map((item) => item.key)).toEqual(['copy-latex', 'copy-md'])
    await items?.[0]?.onSelect()
    await items?.[1]?.onSelect()
    expect(copyText).toHaveBeenNthCalledWith(1, 'e^x')
    expect(copyText).toHaveBeenNthCalledWith(2, '$$e^x$$')
  })

  test('inline math markdown uses single dollars', async () => {
    const items = blockActionItems({ type: 'math', latex: 'x^2' }, t)
    await items?.[1]?.onSelect()
    expect(copyText).toHaveBeenLastCalledWith('$x^2$')
  })

  test('code copies a fenced block', async () => {
    const items = blockActionItems({ type: 'code', lang: 'js', code: 'x()' }, t)
    expect(items?.map((item) => item.key)).toEqual(['copy-fenced'])
    await items?.[0]?.onSelect()
    expect(copyText).toHaveBeenLastCalledWith('```js\nx()\n```')
  })

  test('text copies the markdown source', async () => {
    const items = blockActionItems({ type: 'text', md: '**bold**' }, t)
    await items?.[0]?.onSelect()
    expect(copyText).toHaveBeenLastCalledWith('**bold**')
  })

  test('diagram copies the mermaid source', async () => {
    const items = blockActionItems({ type: 'diagram', mermaid: 'graph LR; A-->B' }, t)
    await items?.[0]?.onSelect()
    expect(copyText).toHaveBeenLastCalledWith('graph LR; A-->B')
  })

  test('chart copies pretty-printed figure JSON', async () => {
    const items = blockActionItems({ type: 'chart', plotly: { data: [] } }, t)
    await items?.[0]?.onSelect()
    expect(copyText).toHaveBeenLastCalledWith('{\n  "data": []\n}')
  })

  test('table copies a markdown table', async () => {
    const items = blockActionItems({ type: 'table', rows: [['h'], ['v']] }, t)
    await items?.[0]?.onSelect()
    expect(copyText).toHaveBeenLastCalledWith('| h |\n| --- |\n| v |')
  })

  test('geo copies the JSXGraph script', async () => {
    const items = blockActionItems({ type: 'geo', jsxgraph: 'board.create()' }, t)
    await items?.[0]?.onSelect()
    expect(copyText).toHaveBeenLastCalledWith('board.create()')
  })

  test('non-copyable blocks yield no items', () => {
    const blocks: Block[] = [
      { type: 'mention', ref: 'N1', kind: 'note', id: 1, title: 'Note' },
      { type: 'image' },
      { type: 'image_ref', image_id: 2 },
      { type: 'drawing', drawing_id: 3 },
      { type: 'widget', widget: 'numberline', id: 'w', props: {} },
      { type: 'mystery' },
    ]
    for (const block of blocks) {
      expect(blockActionItems(block, t)).toBeNull()
    }
  })

  test('empty table and blank geo yield no items', () => {
    expect(blockActionItems({ type: 'table', rows: [] }, t)).toBeNull()
    expect(blockActionItems({ type: 'geo', jsxgraph: '  ' }, t)).toBeNull()
  })
})
