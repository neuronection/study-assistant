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
  insertRef,
  onStudyAlongside,
}: {
  noteId: number
  onClose?: () => void
  insertRef?: { current: NoteInsertApi | null }
  onStudyAlongside?: () => void
}) {
  const { t } = useTranslation()
  return (
    <Suspense fallback={<Loader2 className="animate-spin" aria-label={t('library.loading')} />}>
      <NoteEditor
        noteId={noteId}
        onClose={onClose}
        insertRef={insertRef}
        onStudyAlongside={onStudyAlongside}
      />
    </Suspense>
  )
}
