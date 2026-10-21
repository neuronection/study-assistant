import {
  CalendarClock,
  Dumbbell,
  FolderClosed,
  GitBranch,
  LayoutDashboard,
  MessageSquare,
  NotebookPen,
  Settings,
} from 'lucide-react'

import type { NodeCounts, NodeInfo } from '@/lib/api'


export const TABS = [
  'overview',
  'materials',
  'notes',
  'concepts',
  'practice',
  'planner',
  'tutor',
  'settings',
] as const

export type WorkspaceTab = (typeof TABS)[number]

export function parseTab(
  value: string | undefined
): { tab: WorkspaceTab; cardsSegment?: boolean } {
  if (value === 'cards') {
    return { tab: 'practice', cardsSegment: true }
  }
  if (value !== undefined && (TABS as readonly string[]).includes(value)) {
    return { tab: value as WorkspaceTab }
  }
  return { tab: 'overview' }
}

export const TAB_META: Record<WorkspaceTab, { icon: typeof LayoutDashboard }> = {
  overview: { icon: LayoutDashboard },
  materials: { icon: FolderClosed },
  notes: { icon: NotebookPen },
  concepts: { icon: GitBranch },
  practice: { icon: Dumbbell },
  planner: { icon: CalendarClock },
  tutor: { icon: MessageSquare },
  settings: { icon: Settings },
}

export function findNodeCounts(nodes: NodeInfo[], nodeId: string): NodeCounts | undefined {
  const walk = (entries: NodeInfo[]): NodeCounts | undefined => {
    for (const entry of entries) {
      if (entry.id === nodeId) {
        return entry.counts
      }
      const found = walk(entry.children)
      if (found !== undefined) {
        return found
      }
    }
    return undefined
  }
  return walk(nodes)
}

export function tabCount(tab: WorkspaceTab, counts: NodeCounts | undefined): number | null {
  if (counts === undefined) {
    return null
  }
  switch (tab) {
    case 'materials':
      return counts.materials
    case 'notes':
      return counts.notes
    case 'practice':
      return counts.quizzes + counts.exercises
    default:
      return null
  }
}

export function buildTitleMap(nodes: { id: string; title: string; children: unknown[] }[]): Map<string, string> {
  const map = new Map<string, string>()
  const walk = (entries: { id: string; title: string; children: unknown[] }[]) => {
    for (const entry of entries) {
      map.set(entry.id, entry.title)
      walk(entry.children as { id: string; title: string; children: unknown[] }[])
    }
  }
  walk(nodes)
  return map
}


