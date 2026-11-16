import type { WorkspaceSearchState } from '@/lib/workspace-search'

export function fileDockOpen(
  search: Pick<WorkspaceSearchState, 'material' | 'note' | 'study'>
): boolean {
  return (
    (search.material !== undefined || search.note !== undefined) &&
    search.study === undefined
  )
}
