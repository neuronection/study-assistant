import { describe, expect, test } from 'vitest'

import { messagesToMarkdown } from './exportSessionMarkdown'
import type { ChatMessage } from '@/lib/api'

function message(overrides: Partial<ChatMessage>): ChatMessage {
  return {
    id: 1,
    role: 'user',
    markdown: '',
    citations: [],
    mentions: [],
    reads: [],
    tool_calls: [],
    proposals: [],
    grounded: null,
    ...overrides,
  }
}

describe('exportSessionMarkdown', () => {
  test('builds a markdown document with role headings and citations', () => {
    const markdown = messagesToMarkdown('Derivatives', [
      message({ markdown: 'What is the derivative of x^2?' }),
      message({
        id: 2,
        role: 'assistant',
        markdown: 'The derivative is 2x [1].',
        citations: [
          {
            index: 1,
            chunk_id: 3,
            material_id: 4,
            title: 'rules.md',
            quote: 'power rule',
          },
        ],
      }),
    ])
    expect(markdown).toContain('# Derivatives')
    expect(markdown).toContain('### 🙋 Question')
    expect(markdown).toContain('What is the derivative of x^2?')
    expect(markdown).toContain('### 🤖 Tutor')
    expect(markdown).toContain('The derivative is 2x [1].')
    expect(markdown).toContain('> [1] rules.md — “power rule”')
  })
})
