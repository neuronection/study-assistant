import { describe, expect, test, vi } from 'vitest'

import { parseMindmap } from './mindmapTree'
import { createMindmapSource } from './mindmapSource'

const MD = '# Limits\n\n- Definition\n  - epsilon-delta\n- Limit laws\n'

describe('createMindmapSource', () => {
  test('maps a node to entity + context', () => {
    const source = createMindmapSource({
      markdown: MD,
      courseId: 3,
      scopeNodeId: 5,
      save: vi.fn(),
    })
    const { roots } = parseMindmap(MD)
    expect(source.toEntity(roots[1])).toEqual({ id: '4', label: 'Limit laws' })
    expect(source.toContext(roots[1])).toEqual({ courseId: 3, scopeNodeId: 5 })
  })

  test('builds an llm hint naming the selected node and the full map', () => {
    const source = createMindmapSource({
      markdown: MD,
      courseId: 3,
      scopeNodeId: 5,
      save: vi.fn(),
    })
    const { roots } = parseMindmap(MD)
    const hint = source.llmHint?.(roots[1])
    expect(hint).toContain('Selected node: "Limit laws"')
    expect(hint).toContain('# Limits')
  })

  test('edit rewrites the label and saves', () => {
    const save = vi.fn()
    const source = createMindmapSource({ markdown: MD, courseId: 3, scopeNodeId: 5, save })
    const { roots } = parseMindmap(MD)
    source.edit?.(roots[0], 'Renamed')
    expect(save).toHaveBeenCalledTimes(1)
    expect(save.mock.calls[0][0]).toContain('- Renamed')
    expect(save.mock.calls[0][0]).not.toContain('- Definition')
  })

  test('remove drops the node and its subtree', () => {
    const save = vi.fn()
    const source = createMindmapSource({ markdown: MD, courseId: 3, scopeNodeId: 5, save })
    const { roots } = parseMindmap(MD)
    source.remove?.(roots[0])
    const saved = save.mock.calls[0][0]
    expect(saved).not.toContain('Definition')
    expect(saved).not.toContain('epsilon-delta')
    expect(saved).toContain('Limit laws')
  })

  test('addChild inserts a bullet under the node', () => {
    const save = vi.fn()
    const source = createMindmapSource({ markdown: MD, courseId: 3, scopeNodeId: 5, save })
    const { roots } = parseMindmap(MD)
    source.addChild?.(roots[1], 'product rule')
    const saved = save.mock.calls[0][0]
    expect(saved).toContain('  - product rule')
  })
})
