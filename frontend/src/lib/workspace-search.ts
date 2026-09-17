import type { useNavigate } from '@tanstack/react-router'

export interface WorkspaceSearchState {
  tab?: string
  note?: number
  material?: number
  study?: number | 'new'
  folder?: number
}

export type WorkspaceSearchUpdater = (
  prev: WorkspaceSearchState
) => WorkspaceSearchState

export function stripFileParams(prev: WorkspaceSearchState): WorkspaceSearchState {
  const rest = { ...prev }
  delete rest.material
  delete rest.note
  delete rest.study
  return rest
}

export function navigateWorkspaceSearch(
  navigate: ReturnType<typeof useNavigate>,
  params: { courseId?: string; nodeId?: string },
  search: WorkspaceSearchState | WorkspaceSearchUpdater
): void {
  if (params.nodeId !== undefined) {
    void navigate({
      to: '/courses/$courseId/n/$nodeId',
      params: { courseId: params.courseId ?? '', nodeId: params.nodeId },
      search,
    })
  } else {
    void navigate({
      to: '/courses/$courseId',
      params: { courseId: params.courseId ?? '' },
      search,
    })
  }
}
