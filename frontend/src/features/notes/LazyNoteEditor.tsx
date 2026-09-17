import { Loader2 } from 'lucide-react'
import { lazy, Suspense } from 'react'
import { useTranslation } from 'react-i18next'

import type { NoteInsertApi } from './NoteEditor'

const NoteEditor = lazy(() =>
  import('./NoteEditor').then((module) => ({ default: module.NoteEditor }))
)

export function LazyNoteEditor({
  noteId,
  onClose,
  onRequestClose,
  closeLabel,
  insertRef,
  onStudyAlongside,
  onExpand,
  docked = false,
}: {
  noteId: number
  onClose?: () => void
  onRequestClose?: () => void
  closeLabel?: string
  insertRef?: { current: NoteInsertApi | null }
  onStudyAlongside?: () => void
  onExpand?: () => void
  docked?: boolean
}) {
  const { t } = useTranslation()
  return (
    <Suspense fallback={<Loader2 className="animate-spin" aria-label={t('library.loading')} />}>
      <NoteEditor
        noteId={noteId}
        onClose={onClose}
        onRequestClose={onRequestClose}
        closeLabel={closeLabel}
        insertRef={insertRef}
        onStudyAlongside={onStudyAlongside}
        onExpand={onExpand}
        docked={docked}
      />
    </Suspense>
  )
}
