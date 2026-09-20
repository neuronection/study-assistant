import { storageKeys } from '@/lib/constants'
import type { NodeInfo } from '@/lib/api'

export interface RecentNodeEntry {
  courseId: number
  nodeId: number
  at: number
}

export interface ResolvedRecentNode {
  courseId: number
  nodeId: number
  at: number
  title: string
  breadcrumb: string
}

const KEY_PREFIX = `${storageKeys.recentNodesPrefix}.`
const CAP = 20

function storageKey(): string {
  let profile = 'default'
  try {
    const raw = window.localStorage.getItem(storageKeys.profileId)
    if (raw !== null && raw.length > 0) {
      profile = raw
    }
  } catch {
    profile = 'default'
  }
  return `${KEY_PREFIX}${profile}`
}

export function getRecentNodes(): RecentNodeEntry[] {
  let raw: string
  try {
    raw = window.localStorage.getItem(storageKey()) ?? ''
  } catch {
    return []
  }
  if (raw === '') {
    return []
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return []
  }
  if (!Array.isArray(parsed)) {
    return []
  }
  const entries: RecentNodeEntry[] = []
  for (const item of parsed) {
    if (
      typeof item === 'object' &&
      item !== null &&
      typeof (item as RecentNodeEntry).courseId === 'number' &&
      typeof (item as RecentNodeEntry).nodeId === 'number' &&
      typeof (item as RecentNodeEntry).at === 'number'
    ) {
      entries.push(item as RecentNodeEntry)
    }
  }
  return entries
}

export function recordRecentNode(courseId: number, nodeId: number): void {
  const rest = getRecentNodes().filter(
    (entry) => entry.courseId !== courseId || entry.nodeId !== nodeId
  )
  const next: RecentNodeEntry[] = [
    { courseId, nodeId, at: Date.now() },
    ...rest,
  ].slice(0, CAP)
  try {
    window.localStorage.setItem(storageKey(), JSON.stringify(next))
  } catch {
    return
  }
}

function findTrail(
  nodes: NodeInfo[],
  nodeId: number,
  trail: NodeInfo[]
): NodeInfo[] | null {
  for (const entry of nodes) {
    if (entry.id === nodeId) {
      return [...trail, entry]
    }
    const found = findTrail(entry.children, nodeId, [...trail, entry])
    if (found !== null) {
      return found
    }
  }
  return null
}

export function resolveRecentNodes(
  entries: RecentNodeEntry[],
  trees: Map<number, NodeInfo[] | undefined>,
  courseTitles: Map<number, string>
): ResolvedRecentNode[] {
  const resolved: ResolvedRecentNode[] = []
  for (const entry of entries) {
    const tree = trees.get(entry.courseId)
    if (tree === undefined || tree.length === 0) {
      continue
    }
    const trail = findTrail(tree, entry.nodeId, [])
    if (trail === null || trail.length === 0) {
      continue
    }
    const courseTitle =
      courseTitles.get(entry.courseId) ?? trail[0]!.title
    const ancestors = trail.slice(1, -1).map((node) => node.title)
    resolved.push({
      courseId: entry.courseId,
      nodeId: entry.nodeId,
      at: entry.at,
      title: trail[trail.length - 1]!.title,
      breadcrumb: [courseTitle, ...ancestors].join(' › '),
    })
  }
  return resolved
}
