import { useParams } from '@tanstack/react-router'

import { NodeWorkspace } from './NodeWorkspace'

export function CourseDetailPage() {
  const { courseId } = useParams({ from: '/courses/$courseId' })
  return <NodeWorkspace courseId={courseId} />
}
