import { useLocation, useNavigate, useParams, useSearch } from '@tanstack/react-router'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { MaterialDetailDrawer } from '@/features/library/MaterialDetailDrawer'
import { LazyNoteEditor } from '@/features/notes/LazyNoteEditor'
import { MaterialPickerDialog } from '@/features/courses/MaterialPickerDialog'
import { useFocusContext } from './FocusShell'
import { useDockStore, useRailLayout, useRailResize } from '@/lib/dock-store'
import {
  navigateWorkspaceSearch,
  type WorkspaceSearchState,
} from '@/lib/workspace-search'

export function fileDockOpen(
  search: Pick<WorkspaceSearchState, 'material' | 'note' | 'study'>
): boolean {
  return (
    (search.material !== undefined || search.note !== undefined) &&
    search.study === undefined
  )
}

export function FileDock() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const params = useParams({ strict: false }) as { courseId?: string; nodeId?: string }
  const search = useSearch({ strict: false }) as WorkspaceSearchState
  const open = fileDockOpen(search)
  const rail = useRailLayout(open)
  const fileWidth = useDockStore((state) => state.fileWidth)
  const setFileWidth = useDockStore((state) => state.setFileWidth)
  const persistFileWidth = useDockStore((state) => state.persistFileWidth)
  const [alongsidePicker, setAlongsidePicker] = useState(false)
  const courseIdNumber = params.courseId !== undefined ? Number(params.courseId) : null
  const nodeNumber = params.nodeId !== undefined ? Number(params.nodeId) : null
  const context = useFocusContext(
    search.note !== undefined ? courseIdNumber : null,
    search.note !== undefined ? nodeNumber : null
  )
  const resize = useRailResize({
    width: rail.fileWidth ?? fileWidth,
    setWidth: setFileWidth,
    persist: persistFileWidth,
  })

  if (!open || rail.fileWidth === null) {
    return null
  }

  const toWorkspace = (next: WorkspaceSearchState | ((prev: WorkspaceSearchState) => WorkspaceSearchState)) => {
    navigateWorkspaceSearch(navigate, params, next)
  }

  const closeFile = () => {
    toWorkspace((prev) => {
      const rest = { ...prev }
      delete rest.material
      delete rest.note
      return rest
    })
  }

  const expandMaterial = () => {
    if (search.material === undefined) {
      return
    }
    void navigate({
      to: '/library/$materialId',
      params: { materialId: String(search.material) },
      search: { from: location.href },
    })
  }

  const expandNote = () => {
    if (search.note === undefined) {
      return
    }
    void navigate({
      to: '/note/$noteId',
      params: { noteId: String(search.note) },
      search: { from: location.href },
    })
  }

  return (
    <div
      className="bg-surface relative flex h-full shrink-0 flex-col transition-[width] duration-200 ease-out motion-reduce:transition-none"
      style={{ width: rail.fileWidth }}
    >
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label={t('dock.resize')}
        title={t('dock.resize')}
        className="hover:bg-primary/40 active:bg-primary/60 absolute top-0 -left-0.5 z-10 h-full w-1 cursor-col-resize transition-colors"
        onPointerDown={resize.onResizeStart}
        onPointerMove={resize.onResizeMove}
        onPointerUp={resize.onResizeEnd}
        onPointerCancel={resize.onResizeEnd}
      />
      {search.material !== undefined ? (
        <MaterialDetailDrawer
          materialId={search.material}
          docked
          onClose={closeFile}
          onTakeNotes={() =>
            toWorkspace((prev) => ({ ...prev, material: search.material, study: 'new' }))
          }
          onExpand={expandMaterial}
        />
      ) : search.note !== undefined ? (
        <>
          <LazyNoteEditor
            noteId={search.note}
            docked
            onClose={closeFile}
            onStudyAlongside={search.study === undefined ? () => setAlongsidePicker(true) : undefined}
            onExpand={expandNote}
          />
          {alongsidePicker && courseIdNumber !== null ? (
            <MaterialPickerDialog
              courseId={courseIdNumber}
              nodeId={nodeNumber}
              nodeTitle={context?.nodeTitle}
              assignedIds={new Set<number>()}
              mode="select"
              onClose={() => setAlongsidePicker(false)}
              onSelect={(ids) => {
                const picked = ids[0]
                setAlongsidePicker(false)
                if (picked !== undefined && search.note !== undefined) {
                  toWorkspace((prev) => {
                    const rest = { ...prev }
                    delete rest.note
                    return { ...rest, material: picked, study: search.note }
                  })
                }
              }}
            />
          ) : null}
        </>
      ) : null}
    </div>
  )
}
