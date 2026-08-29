import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  BookOpen,
  FileDown,
  History,
  Layers,
  Loader2,
  MoreHorizontal,
  Printer,
  Save,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { FocusShell, useFocusContext } from '@/components/layout/FocusShell'
import { MarkdownEditor, type DrawingAdapter, type MarkdownEditorApi } from '@/components/editor/MarkdownEditor'
import { exportMarkdownWithDrawings } from '@/components/materials/exportMarkdown'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { ErrorBanner } from '@/components/ui/error-banner'
import { PopoverMenu } from '@/components/ui/popover-menu'
import {
  addDrawing,
  deleteDrawing,
  deleteNote,
  generateFlashcards,
  getNote,
  reocrDrawing,
  runNoteAction,
  updateDrawing,
  updateNote,
} from '@/lib/api'
import { useDrawingOcrSync } from '@/lib/useDrawingOcrSync'

import { NoteHistoryDialog } from './NoteHistoryDialog'
import { noteBodyMd, useNoteAutosave } from './useNoteAutosave'

const ACTIONS = ['summarize', 'cleanup', 'explain', 'expand'] as const

export type NoteInsertApi = {
  insertQuote: (text: string, source: { title: string; materialId: number } | null) => void
}

export function NoteEditor({
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
  const queryClient = useQueryClient()
  const note = useQuery({ queryKey: ['note', noteId], queryFn: () => getNote(noteId) })
  const context = useFocusContext(note.data?.course_id ?? null, note.data?.node_id ?? null)
  const [draft, setDraft] = useState<string | null>(null)
  const [showHistory, setShowHistory] = useState(false)
  const editorApi = useRef<MarkdownEditorApi | null>(null)

  useEffect(() => {
    if (!insertRef) {
      return
    }
    insertRef.current = {
      insertQuote: (text, source) => editorApi.current?.insertQuote(text, source),
    }
    return () => {
      insertRef.current = null
    }
  })
  const [actionResult, setActionResult] = useState<string | null>(null)
  const [infoResult, setInfoResult] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tagDraft, setTagDraft] = useState<string | null>(null)
  const [titleDraft, setTitleDraft] = useState<string | null>(null)

  const autosave = useNoteAutosave({
    noteId,
    note: note.data,
    draft,
    setDraft,
    onSaved: (updated) => {
      queryClient.setQueryData(['note', noteId], updated)
      void queryClient.invalidateQueries({ queryKey: ['notes'] })
    },
    onError: setError,
    reload: () => void note.refetch(),
  })

  const saveTitle = useMutation({
    mutationFn: (title: string) => updateNote(noteId, { title }),
    onSuccess: async () => {
      setTitleDraft(null)
      setError(null)
      await queryClient.invalidateQueries({ queryKey: ['note', noteId] })
      await queryClient.invalidateQueries({ queryKey: ['notes'] })
    },
    onError: (err: Error) => setError(err.message),
  })

  const saveTags = useMutation({
    mutationFn: (tags: string[]) => updateNote(noteId, { tags }),
    onSuccess: async () => {
      setTagDraft(null)
      await queryClient.invalidateQueries({ queryKey: ['note', noteId] })
      await queryClient.invalidateQueries({ queryKey: ['notes'] })
      await queryClient.invalidateQueries({ queryKey: ['note-tags'] })
    },
    onError: (err: Error) => setError(err.message),
  })

  const drawingAdapter = useMemo<DrawingAdapter>(
    () => ({
      create: async (newStrokes, pngBase64, ocr, view) => {
        const updated = await addDrawing(noteId, newStrokes, pngBase64, ocr, view)
        setError(null)
        const known = new Set((note.data?.drawings ?? []).map((entry) => entry.id))
        const fresh = updated.drawings.find((entry) => !known.has(entry.id))
        await queryClient.setQueryData(['note', noteId], updated)
        await queryClient.invalidateQueries({ queryKey: ['note', noteId] })
        await queryClient.invalidateQueries({ queryKey: ['notes'] })
        return fresh?.id ?? null
      },
      update: async (drawingId, newStrokes, pngBase64, ocr, view) => {
        const updated = await updateDrawing(noteId, drawingId, newStrokes, pngBase64, ocr, view)
        setError(null)
        await queryClient.setQueryData(['note', noteId], updated)
        await queryClient.invalidateQueries({ queryKey: ['note', noteId] })
        await queryClient.invalidateQueries({ queryKey: ['notes'] })
      },
      reocr: async (drawingId) => {
        await reocrDrawing(noteId, drawingId)
        await queryClient.invalidateQueries({ queryKey: ['note', noteId] })
      },
      remove: async (drawingId) => {
        const updated = await deleteDrawing(noteId, drawingId)
        setError(null)
        await queryClient.setQueryData(['note', noteId], updated)
        await queryClient.invalidateQueries({ queryKey: ['note', noteId] })
        await queryClient.invalidateQueries({ queryKey: ['notes'] })
      },
    }),
    [noteId, note.data, queryClient]
  )
  useDrawingOcrSync(note.data?.drawings, () => {
    void queryClient.invalidateQueries({ queryKey: ['note', noteId] })
    void queryClient.invalidateQueries({ queryKey: ['notes'] })
  })
  const exportMd = useMutation({
    mutationFn: async () => {
      const current = note.data
      if (current === undefined) {
        return
      }
      const body = draft ?? noteBodyMd(current)
      const resolved = await exportMarkdownWithDrawings(body, current.drawings)
      const safeTitle = current.title.replace(/[^\w\s-]/g, '').trim() || 'note'
      const blob = new Blob([`# ${current.title}\n\n${resolved}\n`], {
        type: 'text/markdown',
      })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `${safeTitle}.md`
      anchor.click()
      URL.revokeObjectURL(url)
    },
    onError: (err: Error) => setError(err.message),
  })

  const action = useMutation({
    mutationFn: (kind: (typeof ACTIONS)[number]) => runNoteAction(noteId, kind),
    onSuccess: (result) => {
      setError(null)
      setInfoResult(null)
      setActionResult(result.markdown)
    },
    onError: (err: Error) => setError(err.message),
  })

  const makeFlashcards = useMutation({
    mutationFn: (courseIdForBody: number) =>
      generateFlashcards({
        source: 'note',
        note_id: noteId,
        course_id: courseIdForBody,
        count: 8,
      }),
    onSuccess: async (cards) => {
      setError(null)
      setActionResult(null)
      setInfoResult(t('notes.flashcardsMade', { count: cards.length }))
      await queryClient.invalidateQueries({ queryKey: ['cards'] })
      await queryClient.invalidateQueries({ queryKey: ['cards-due'] })
    },
    onError: (err: Error) => setError(err.message),
  })

  const remove = useMutation({
    mutationFn: () => deleteNote(noteId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['notes'] })
      await queryClient.invalidateQueries({ queryKey: ['note-tags'] })
      await queryClient.invalidateQueries({ queryKey: ['tree'] })
      onClose?.()
    },
    onError: (err: Error) => setError(err.message),
  })

  if (note.isLoading) {
    return <Loader2 className="animate-spin" aria-label={t('library.loading')} />
  }
  const data = note.data!
  const markdown = draft ?? noteBodyMd(data)
  const noteCourseId = data.course_id

  return (
    <FocusShell
      overlay={onClose !== undefined}
      ariaLabel={t('notes.drawerLabel')}
      contentClassName="max-w-3xl"
      context={context}
      title={
        <form
          className="min-w-0 flex-1"
          onSubmit={(event) => {
            event.preventDefault()
            const next = titleDraft?.trim()
            if (next && next !== data.title) {
              saveTitle.mutate(next)
            } else {
              setTitleDraft(null)
            }
          }}
        >
          <input
            className="bg-transparent w-full text-lg font-semibold outline-none focus:border-b focus:border-border"
            aria-label={t('notes.titleLabel')}
            value={titleDraft ?? data.title}
            onChange={(event) => setTitleDraft(event.target.value)}
            onBlur={(event) => {
              const next = event.target.value.trim()
              if (next && next !== data.title) {
                saveTitle.mutate(next)
              } else if (next !== data.title) {
                setTitleDraft(null)
              }
            }}
          />
        </form>
      }
      onClose={onClose}
    >
      <div className="space-y-4">
      {autosave.recovery !== null ? (
        <Card>
          <CardContent className="flex flex-wrap items-center justify-between gap-2 p-3">
            <p className="text-sm">{t('notes.recoveryFound')}</p>
            <div className="flex gap-2">
              <Button size="sm" onClick={autosave.restoreRecovery}>
                {t('notes.recoveryRestore')}
              </Button>
              <Button variant="outline" size="sm" onClick={autosave.discardRecovery}>
                {t('notes.recoveryDiscard')}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {autosave.conflict ? (
        <Card>
          <CardContent className="space-y-2 p-3">
            <p className="flex items-center gap-2 text-sm">
              <AlertTriangle className="size-4 text-warning" aria-hidden />
              {t('notes.conflictTitle')}
            </p>
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={autosave.resolveConflictReload}>
                {t('notes.conflictReload')}
              </Button>
              <Button size="sm" onClick={() => autosave.saveNow({ force: true })}>
                {t('notes.conflictOverwrite')}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-2">
        <span
          className="text-muted-foreground text-[11px]"
          role="status"
          aria-live="polite"
        >
          {autosave.status !== 'idle' ? t(`notes.autosave.${autosave.status}`) : ''}
        </span>
        <div className="flex flex-wrap gap-2">
          <PopoverMenu
            label={t('notes.aiMenuLabel')}
            triggerClassName="border-border bg-surface text-foreground hover:bg-subtle h-8 gap-1.5 border px-3 text-sm font-medium"
            trigger={
              <span className="flex items-center gap-1.5">
                {action.isPending ? (
                  <Loader2 className="animate-spin size-4" aria-hidden />
                ) : (
                  <Sparkles className="size-4" aria-hidden />
                )}
                {t('notes.aiMenu')}
              </span>
            }
            items={ACTIONS.map((kind) => ({
              key: kind,
              label: t(`notes.action.${kind}`),
              icon: Sparkles,
              pending: action.isPending && action.variables === kind,
              onSelect: () => action.mutate(kind),
            }))}
          />
          <Button
            variant="outline"
            size="sm"
            disabled={makeFlashcards.isPending || noteCourseId === null}
            onClick={() => {
              if (noteCourseId !== null) {
                makeFlashcards.mutate(noteCourseId)
              }
            }}
          >
            {makeFlashcards.isPending ? (
              <Loader2 className="animate-spin" aria-hidden />
            ) : (
              <Layers aria-hidden />
            )}
            {t('notes.makeFlashcards')}
          </Button>
          {onStudyAlongside ? (
            <Button variant="outline" size="sm" onClick={onStudyAlongside}>
              <BookOpen aria-hidden />
              {t('notes.studyAlongside')}
            </Button>
          ) : null}
          <PopoverMenu
            label={t('notes.moreActions')}
            trigger={<MoreHorizontal className="size-4" aria-hidden />}
            items={[
              {
                key: 'print',
                label: t('notes.print'),
                icon: Printer,
                onSelect: () => {
                  const current = window.location.pathname + window.location.search
                  window.location.assign(
                    `/note/${noteId}?print=1&from=${encodeURIComponent(current)}`
                  )
                },
              },
              {
                key: 'export',
                label: t('notes.exportMd'),
                icon: FileDown,
                pending: exportMd.isPending,
                onSelect: () => exportMd.mutate(),
              },
              {
                key: 'history',
                label: t('notes.history'),
                icon: History,
                onSelect: () => setShowHistory(true),
              },
              {
                key: 'delete',
                label: t('notes.delete'),
                icon: Trash2,
                danger: true,
                pending: remove.isPending,
                onSelect: () => {
                  if (window.confirm(t('notes.confirmDelete', { title: data.title }))) {
                    remove.mutate()
                  }
                },
              },
            ]}
          />
          <Button
            size="sm"
            disabled={!autosave.dirty || autosave.status === 'saving'}
            onClick={() => autosave.saveNow()}
          >
            {autosave.status === 'saving' ? (
              <Loader2 className="animate-spin" aria-hidden />
            ) : (
              <Save aria-hidden />
            )}
            {t('notes.save')}
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-1" aria-label={t('notes.tagsLabel')}>
        {data.tags.map((tag) => (
          <span
            key={tag}
            className="bg-subtle text-muted-foreground group flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px]"
          >
            {tag}
            <button
              type="button"
              className="opacity-60 group-hover:opacity-100"
              title={t('notes.removeTag')}
              onClick={() => saveTags.mutate(data.tags.filter((entry) => entry !== tag))}
            >
              <X className="size-3" aria-hidden />
            </button>
          </span>
        ))}
        {tagDraft === null ? (
          <button
            type="button"
            className="text-muted-foreground hover:text-foreground text-[11px] underline"
            onClick={() => setTagDraft('')}
          >
            {t('notes.addTag')}
          </button>
        ) : (
          <form
            onSubmit={(event) => {
              event.preventDefault()
              const next = tagDraft.trim().toLowerCase()
              if (next && !data.tags.includes(next)) {
                saveTags.mutate([...data.tags, next])
              } else {
                setTagDraft(null)
              }
            }}
          >
            <input
              autoFocus
              className="bg-surface border-border w-28 rounded-full border px-2 py-0.5 text-[11px]"
              value={tagDraft}
              placeholder={t('notes.addTag')}
              onChange={(event) => setTagDraft(event.target.value)}
              onBlur={() => setTagDraft(null)}
            />
          </form>
        )}
      </div>

      {actionResult !== null ? (
        <Card>
          <CardContent className="space-y-2 p-4">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground text-xs">
                {t('notes.aiResultTitle')}
              </span>
              <Button
                variant="ghost"
                size="sm"
                aria-label={t('notes.closeResult')}
                title={t('notes.closeResult')}
                onClick={() => setActionResult(null)}
              >
                <X aria-hidden />
              </Button>
            </div>
            <textarea
              className="bg-surface border-border focus:border-ring w-full resize-y rounded-md border p-2 font-mono text-xs outline-none"
              rows={10}
              aria-label={t('notes.aiResultTitle')}
              value={actionResult}
              onChange={(event) => setActionResult(event.target.value)}
            />
            <div className="flex justify-end">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  const current = draft ?? noteBodyMd(data)
                  const next = actionResult.trim()
                  setDraft(current === '' ? next : `${current}\n\n---\n\n${next}`)
                  setActionResult(null)
                }}
              >
                {t('notes.appendResult')}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {infoResult !== null ? (
        <Card>
          <CardContent className="flex items-center justify-between gap-2 p-3">
            <p className="text-sm">{infoResult}</p>
            <Button
              variant="ghost"
              size="sm"
              aria-label={t('notes.closeResult')}
              title={t('notes.closeResult')}
              onClick={() => setInfoResult(null)}
            >
              <X aria-hidden />
            </Button>
          </CardContent>
        </Card>
      ) : null}

      <MarkdownEditor
        value={markdown}
        onChange={setDraft}
        ariaLabel={t('notes.bodyLabel')}
        drawings={data.drawings}
        drawingAdapter={drawingAdapter}
        apiRef={editorApi}
        aiHelper={{
          courseId: data.course_id ?? undefined,
          nodeId: data.node_id ?? undefined,
          title: data.title,
        }}
      />

      {error ? <ErrorBanner message={error} /> : null}
      </div>
      {showHistory ? (
        <NoteHistoryDialog
          noteId={noteId}
          dirty={autosave.dirty}
          onSaveVersion={async () => {
            const body = draft ?? noteBodyMd(data)
            await updateNote(noteId, { body_md: body })
            return updateNote(noteId, { body_md: body, force_version: true })
          }}
          onRestored={() => setDraft(null)}
          onClose={() => setShowHistory(false)}
        />
      ) : null}
    </FocusShell>
  )
}
