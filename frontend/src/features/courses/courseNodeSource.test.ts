import { describe, expect, test } from 'vitest'

import { createCourseNodeSource } from './courseNodeSource'
import type { NodeInfo } from '@/lib/api'

const NODE: NodeInfo = {
  id: 12,
  title: 'Chain rule',
  summary: null,
  objectives: [],
  order_idx: 0,
  depth: 2,
  is_root: false,
  children: [],
  materials: [],
}

describe('createCourseNodeSource', () => {
  test('maps a tree node to an entity scoped to itself', () => {
    const source = createCourseNodeSource(3)
    expect(source.toEntity(NODE)).toEqual({ id: 'node:12', label: 'Chain rule' })
    expect(source.toContext(NODE)).toEqual({ courseId: 3, scopeNodeId: 12 })
    expect(source.canEdit).toBeUndefined()
    expect(source.canAiEdit).toBeUndefined()
    expect(source.llmHint).toBeUndefined()
  })
})
