import type {
  EntityContext,
  EntityNode,
  NodeSource,
} from '@/components/entity-menu/types'
import type { NodeInfo } from '@/lib/api'

export function createCourseNodeSource(courseId: number): NodeSource<NodeInfo> {
  return {
    kind: 'course-tree',
    toEntity: (node: NodeInfo): EntityNode => ({
      id: `node:${node.id}`,
      label: node.title,
    }),
    toContext: (node: NodeInfo): EntityContext => ({
      courseId,
      scopeNodeId: node.id,
    }),
  }
}
