import { beforeEach, describe, expect, test } from 'vitest'

import { storageKeys } from './constants'
import { getRecentNodes, recordRecentNode, resolveRecentNodes } from './recent-nodes'
import type { NodeInfo } from '@/lib/api'

const KEY = 'ca-recent-nodes.default'

function setProfile(id: string | null): void {
  if (id === null) {
    window.localStorage.removeItem(storageKeys.profileId)
  } else {
    window.localStorage.setItem(storageKeys.profileId, id)
  }
}

beforeEach(() => {
  setProfile(null)
  window.localStorage.clear()
})

describe('recent-nodes store', () => {
  test('records visits most-recent-first', () => {
    recordRecentNode(3, 5)
    recordRecentNode(3, 11)
    expect(getRecentNodes()).toEqual([
      { courseId: 3, nodeId: 11, at: expect.any(Number) },
      { courseId: 3, nodeId: 5, at: expect.any(Number) },
    ])
  })

  test('re-visiting a node moves it to the front instead of duplicating', () => {
    recordRecentNode(3, 5)
    recordRecentNode(3, 11)
    recordRecentNode(3, 5)
    const entries = getRecentNodes()
    expect(entries).toHaveLength(2)
    expect(entries[0]).toMatchObject({ courseId: 3, nodeId: 5 })
  })

  test('caps the history at 20 entries', () => {
    for (let nodeId = 1; nodeId <= 25; nodeId += 1) {
      recordRecentNode(3, nodeId)
    }
    const entries = getRecentNodes()
    expect(entries).toHaveLength(20)
    expect(entries[0]).toMatchObject({ courseId: 3, nodeId: 25 })
    expect(entries[19]).toMatchObject({ courseId: 3, nodeId: 6 })
  })

  test('namespaces history per profile', () => {
    setProfile('2')
    recordRecentNode(3, 5)
    expect(getRecentNodes()).toHaveLength(1)
    setProfile('1')
    expect(getRecentNodes()).toEqual([])
    recordRecentNode(4, 9)
    expect(window.localStorage.getItem('ca-recent-nodes.1')).not.toBeNull()
    setProfile('2')
    expect(getRecentNodes()[0]).toMatchObject({ courseId: 3, nodeId: 5 })
  })

  test('tolerates corrupt JSON and malformed entries', () => {
    window.localStorage.setItem(KEY, 'not json at all')
    expect(getRecentNodes()).toEqual([])
    window.localStorage.setItem(
      KEY,
      JSON.stringify([{ courseId: 3, nodeId: 5, at: 1 }, 'junk', null, { courseId: 'x' }, 42])
    )
    expect(getRecentNodes()).toEqual([{ courseId: 3, nodeId: 5, at: 1 }])
  })
})

describe('resolveRecentNodes', () => {
  const tree: NodeInfo[] = [
    {
      id: 1,
      title: 'Calculus I',
      summary: null,
      objectives: [],
      order_idx: 0,
      depth: 0,
      is_root: true,
      children: [
        {
          id: 5,
          title: 'Derivatives',
          summary: null,
          objectives: [],
          order_idx: 0,
          depth: 1,
          is_root: false,
          children: [
            {
              id: 11,
              title: 'Chain rule',
              summary: null,
              objectives: [],
              order_idx: 0,
              depth: 2,
              is_root: false,
              children: [],
              materials: [],
            },
          ],
          materials: [],
        },
      ],
      materials: [],
    },
  ]
  const trees = new Map([[3, tree]])
  const titles = new Map([[3, 'Calculus I']])
  const entry = (nodeId: number, at = 1000) => ({ courseId: 3, nodeId, at })

  test('resolves title and breadcrumb from the tree', () => {
    expect(resolveRecentNodes([entry(11)], trees, titles)).toEqual([
      {
        courseId: 3,
        nodeId: 11,
        at: 1000,
        title: 'Chain rule',
        breadcrumb: 'Calculus I › Derivatives',
      },
    ])
    expect(resolveRecentNodes([entry(5)], trees, titles)).toEqual([
      {
        courseId: 3,
        nodeId: 5,
        at: 1000,
        title: 'Derivatives',
        breadcrumb: 'Calculus I',
      },
    ])
  })

  test('falls back to the root node title when the course list lacks the course', () => {
    const fallback = new Map<number, string>()
    const rows = resolveRecentNodes([entry(5)], trees, fallback)
    expect(rows[0]?.breadcrumb).toBe('Calculus I')
  })

  test('silently drops entries whose node or tree is gone', () => {
    expect(resolveRecentNodes([entry(999), entry(5)], trees, titles)).toHaveLength(1)
    expect(resolveRecentNodes([entry(5)], new Map(), titles)).toEqual([])
  })
})
