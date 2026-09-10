import { describe, expect, test } from 'vitest'

import { hasStructuredBlocks, toChatMessageView } from './chatMessages'
import type { ChatMessage } from '@/lib/api'

function message(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: 7,
    role: 'assistant',
    markdown: 'Hello',
    citations: [],
    mentions: [],
    reads: [],
    tool_calls: [],
    proposals: [],
    grounded: null,
    ...overrides,
  }
}

describe('hasStructuredBlocks (plan 60 §5 content rule)', () => {
  test('messages without blocks render through markdown', () => {
    expect(hasStructuredBlocks(message())).toBe(false)
    expect(hasStructuredBlocks(message({ blocks: [] }))).toBe(false)
  })

  test('text, math, diagram and code blocks stay markdown', () => {
    const blocks = [
      { type: 'text', md: 'Hello' },
      { type: 'math', latex: 'x^2' },
      { type: 'diagram', mermaid: 'graph TD' },
      { type: 'code', code: 'x' },
    ] as const
    expect(hasStructuredBlocks(message({ blocks: [...blocks] }))).toBe(false)
  })

  test('structured block types force the BlockRenderer path', () => {
    for (const block of [
      { type: 'chart', plotly: {} },
      { type: 'geo', jsxgraph: '' },
      { type: 'widget', widget: 'checklist', id: 'w1', props: {} },
      { type: 'image', alt: '' },
      { type: 'image_ref', image_id: 1 },
      { type: 'drawing', drawing_id: 1 },
      { type: 'mention', ref: 'M1', kind: 'material', id: 1, title: 'T' },
      { type: 'table', rows: [['a']] },
    ]) {
      expect(hasStructuredBlocks(message({ blocks: [block] }))).toBe(true)
    }
  })
})

describe('toChatMessageView', () => {
  test('maps ids to strings and decorates variants', () => {
    const view = toChatMessageView(
      message({
        id: 30,
        role: 'user',
        parent_id: 12,
        variant_index: 2,
        variant_count: 3,
        sibling_ids: [11, 30, 44],
      }),
    )
    expect(view).toEqual({
      id: '30',
      role: 'user',
      content: 'Hello',
      status: 'done',
      parentId: '12',
      variants: { index: 2, count: 3, siblingIds: ['11', '30', '44'] },
    })
  })

  test('single-variant messages carry no variants decoration', () => {
    const view = toChatMessageView(message({ variant_count: 1 }))
    expect(view.variants).toBeUndefined()
  })

  test('unknown roles map to assistant', () => {
    expect(toChatMessageView(message({ role: 'tool' })).role).toBe('assistant')
  })
})
