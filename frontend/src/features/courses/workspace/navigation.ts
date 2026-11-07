import { useNavigate } from '@tanstack/react-router'

import { openNote } from '@/features/notes/NoteEditorDrawer'

import type { WorkspaceTab } from './tabs'

export function useWorkspaceNavigation(courseId: string, nodeId: string | undefined) {
  const navigate = useNavigate()

  const setTab = (next: WorkspaceTab) => {
    const nextSearch = { tab: next === 'overview' ? undefined : next }
    if (nodeId !== undefined) {
      void navigate({
        to: '/courses/$courseId/n/$nodeId',
        params: { courseId, nodeId },
        search: nextSearch,
      })
    } else {
      void navigate({ to: '/courses/$courseId', params: { courseId }, search: nextSearch })
    }
  }

  const openNoteAt = (noteId: string) => {
    const nextSearch = openNote(noteId)
    if (nodeId !== undefined) {
      void navigate({
        to: '/courses/$courseId/n/$nodeId',
        params: { courseId, nodeId },
        search: nextSearch,
      })
    } else {
      void navigate({ to: '/courses/$courseId', params: { courseId }, search: nextSearch })
    }
  }

  const openMaterialAt = (materialId: string) => {
    const nextSearch = (prev: { tab?: string; note?: string; material?: string; study?: string }) => ({
      ...prev,
      material: materialId,
    })
    if (nodeId !== undefined) {
      void navigate({
        to: '/courses/$courseId/n/$nodeId',
        params: { courseId, nodeId },
        search: nextSearch,
      })
    } else {
      void navigate({ to: '/courses/$courseId', params: { courseId }, search: nextSearch })
    }
  }

  const openFolderInView = (folderId: string) => {
    const nextSearch = (
      prev: {
        tab?: string
        note?: string
        material?: string
        study?: string
        folder?: string
      },
    ) => ({ ...prev, tab: 'materials' as const, folder: folderId })
    if (nodeId !== undefined) {
      void navigate({
        to: '/courses/$courseId/n/$nodeId',
        params: { courseId, nodeId },
        search: nextSearch,
      })
    } else {
      void navigate({ to: '/courses/$courseId', params: { courseId }, search: nextSearch })
    }
  }

  const closeFolderView = () => {
    const nextSearch = (
      prev: {
        tab?: string
        note?: string
        material?: string
        study?: string
        folder?: string
      },
    ) => {
      const rest = { ...prev }
      delete rest.folder
      return rest
    }
    if (nodeId !== undefined) {
      void navigate({
        to: '/courses/$courseId/n/$nodeId',
        params: { courseId, nodeId },
        search: nextSearch,
      })
    } else {
      void navigate({ to: '/courses/$courseId', params: { courseId }, search: nextSearch })
    }
  }

  const studyNoteCreated = (noteId: string) => {
    const nextSearch = (prev: { tab?: string; note?: string; material?: string; study?: string }) => ({
      ...prev,
      study: noteId,
    })
    if (nodeId !== undefined) {
      void navigate({
        to: '/courses/$courseId/n/$nodeId',
        params: { courseId, nodeId },
        search: nextSearch,
      })
    } else {
      void navigate({ to: '/courses/$courseId', params: { courseId }, search: nextSearch })
    }
  }

  const closeStudy = () => {
    const nextSearch = (prev: { tab?: string; note?: string; material?: string; study?: string }) => {
      const rest = { ...prev }
      delete rest.material
      delete rest.study
      return rest
    }
    if (nodeId !== undefined) {
      void navigate({
        to: '/courses/$courseId/n/$nodeId',
        params: { courseId, nodeId },
        search: nextSearch,
      })
    } else {
      void navigate({ to: '/courses/$courseId', params: { courseId }, search: nextSearch })
    }
  }

  const closeNotes = () => {
    const nextSearch = (prev: { tab?: string; note?: string; material?: string; study?: string }) => {
      const rest = { ...prev }
      delete rest.study
      return rest
    }
    if (nodeId !== undefined) {
      void navigate({
        to: '/courses/$courseId/n/$nodeId',
        params: { courseId, nodeId },
        search: nextSearch,
      })
    } else {
      void navigate({ to: '/courses/$courseId', params: { courseId }, search: nextSearch })
    }
  }


  return {
    setTab,
    openNoteAt,
    openMaterialAt,
    openFolderInView,
    closeFolderView,
    studyNoteCreated,
    closeStudy,
    closeNotes,
  }
}
