import { useQuery } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useParams, useSearch } from '@tanstack/react-router'

import { getNote } from '@/lib/api'
import { useOriginBack } from '@/lib/origin'

import { LazyNoteEditor } from './LazyNoteEditor'

export function NoteFocusPage() {
  const { noteId } = useParams({ from: '/note/$noteId' })
  const { from, print } = useSearch({ from: '/note/$noteId' })
  const id = Number(noteId)
  const note = useQuery({
    queryKey: ['note', id],
    queryFn: () => getNote(id),
  })
  const courseId = note.data?.course_id ?? null
  const nodeId = note.data?.node_id ?? null
  const fallback =
    courseId !== null
      ? nodeId !== null
        ? `/courses/${courseId}/n/${nodeId}?tab=notes`
        : `/courses/${courseId}?tab=notes`
      : '/courses'
  const goBack = useOriginBack(from, fallback)

  useEffect(() => {
    if (!print || !note.data) {
      return
    }
    const timer = window.setTimeout(() => window.print(), 600)
    return () => window.clearTimeout(timer)
  }, [print, note.data])

  return <LazyNoteEditor noteId={id} onClose={goBack} />
}
