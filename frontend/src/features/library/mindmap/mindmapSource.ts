import type {
  EntityContext,
  EntityNode,
  NodeSource,
} from '@/components/entity-menu/types'
import {
  addChildNode,
  editNodeLabel,
  parseMindmap,
  removeNode,
  serialize,
  type MindmapNode,
} from './mindmapTree'

const HINT_CAP = 1800

export function mindmapLlmHint(markdown: string, focusLabel: string | null): string {
  const capped = markdown.length > HINT_CAP ? `${markdown.slice(0, HINT_CAP)}…` : markdown
  const head = focusLabel
    ? [`The user is studying a mindmap and selected one of its nodes.`, `Selected node: "${focusLabel}".`]
    : ['The user is studying the whole mindmap below.']
  return [...head, 'Full mindmap (truncated):', capped].join('\n')
}

export function createMindmapSource(options: {
  markdown: string
  courseId: number
  scopeNodeId: number | null
  save: (markdown: string) => void
}): NodeSource<MindmapNode> {
  const parsed = parseMindmap(options.markdown)

  const toEntity = (node: MindmapNode): EntityNode => ({
    id: node.id,
    label: node.label,
  })

  const toContext = (): EntityContext => ({
    courseId: options.courseId,
    scopeNodeId: options.scopeNodeId,
  })

  return {
    kind: 'mindmap',
    toEntity,
    toContext,
    llmHint: (node) => mindmapLlmHint(options.markdown, node.label),
    canEdit: true,
    edit: (node, label) => {
      options.save(serialize(editNodeLabel(parsed.lines, node, label)))
    },
    canRemove: true,
    remove: (node) => {
      options.save(serialize(removeNode(parsed.lines, node)))
    },
    canAddChild: true,
    addChild: (node, label) => {
      options.save(serialize(addChildNode(parsed.lines, node, label)))
    },
  }
}
