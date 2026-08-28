import { useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { Stroke, ViewBox } from '@/components/canvas/DrawCanvas'
import type { DrawingAdapter, DrawingMeta } from '@/components/editor/MarkdownEditor'
import { LazyMarkdownEditor } from '@/components/editor/LazyMarkdownEditor'
import { Button } from '@/components/ui/button'
import type { PendingDrawing, TextFileEditState } from '@/lib/api'
import { useCloseFloatings } from '@/lib/ui-overlays'

export function NewTextFileDialog({
  defaultKind,
  onCreate,
  onSave,
  onCancel,
  courseId,
}: {
  defaultKind: 'txt' | 'md'
  onCreate: (filename: string, content: string, drawings: PendingDrawing[]) => Promise<TextFileEditState | null>
  onSave: (content: string, drawings: PendingDrawing[], state: TextFileEditState) => Promise<TextFileEditState>
  onCancel: () => void
  courseId?: number
}) {
  useCloseFloatings()
  const { t } = useTranslation()
  const [kind, setKind] = useState<'txt' | 'md'>(defaultKind)
  const [name, setName] = useState('')
  const [content, setContent] = useState('')
  const [pendingDrawings, setPendingDrawings] = useState<PendingDrawing[]>([])
  const [savedState, setSavedState] = useState<TextFileEditState | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const nextRef = useRef(-1)

  const drawingAdapter = useMemo<DrawingAdapter>(
    () => ({
      create: async (strokes: Stroke[], pngBase64: string, ocr: boolean, view?: ViewBox) => {
        const ref = nextRef.current
        nextRef.current -= 1
        setPendingDrawings((prev) => [
          ...prev,
          { ref, strokes, png_base64: pngBase64, ocr, view },
        ])
        return ref
      },
      update: async (
        drawingId: number,
        strokes: Stroke[],
        pngBase64: string,
        ocr: boolean,
        view?: ViewBox
      ) => {
        setPendingDrawings((prev) =>
          prev.map((entry) =>
            entry.ref === drawingId
              ? { ...entry, strokes, png_base64: pngBase64, ocr, view }
              : entry
          )
        )
      },
      reocr: async () => {},
      remove: async (drawingId: number) => {
        setPendingDrawings((prev) => prev.filter((entry) => entry.ref !== drawingId))
      },
    }),
    []
  )

  const drawings: DrawingMeta[] = pendingDrawings.map((entry) => ({
    id: entry.ref,
    png_sha: `data:image/png;base64,${entry.png_base64}`,
    ocr_markdown: null,
    strokes: entry.strokes,
    view: entry.view,
  }))

  const applySavedState = (state: TextFileEditState) => {
    setPendingDrawings((prev) =>
      prev.map((entry) =>
        state.refToReal[entry.ref] !== undefined
          ? { ...entry, ref: state.refToReal[entry.ref] }
          : entry
      )
    )
    setSavedState(state)
    setContent(state.content)
  }

  const create = async () => {
    const trimmed = name.trim()
    if (!trimmed) {
      return
    }
    setBusy(true)
    setError(null)
    try {
      const filename = kind === 'md' ? `${trimmed}.md` : trimmed
      const state = await onCreate(filename, content, pendingDrawings)
      if (state !== null) {
        applySavedState(state)
      } else {
        onCancel()
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  const save = async () => {
    if (savedState === null) {
      return
    }
    setBusy(true)
    setError(null)
    try {
      applySavedState(await onSave(content, pendingDrawings, savedState))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  const changed = savedState === null || content !== savedState.content

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={t('newTextFile.title')}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onCancel()
        }
      }}
    >
      <div className="bg-surface border-border flex max-h-[80vh] w-full max-w-2xl flex-col rounded-lg border shadow-xl">
        <header className="border-border flex items-center justify-between border-b px-4 py-2">
          <h2 className="text-sm font-semibold">{t('newTextFile.title')}</h2>
          {savedState !== null ? (
            <span className="text-muted-foreground text-[11px]">{t('newTextFile.saved')}</span>
          ) : null}
        </header>
        <div className="flex flex-1 flex-col gap-2 overflow-y-auto p-4">
          <div className="flex gap-1" role="group" aria-label={t('newTextFile.kind')}>
            {(['txt', 'md'] as const).map((option) => (
              <button
                key={option}
                type="button"
                className={`rounded-full px-2 py-0.5 text-[11px] ${
                  kind === option
                    ? 'bg-primary/15 text-primary font-medium'
                    : 'text-muted-foreground hover:bg-subtle'
                }`}
                onClick={() => setKind(option)}
              >
                {option === 'txt' ? t('newTextFile.plainText') : t('newTextFile.markdown')}
              </button>
            ))}
          </div>
          <input
            autoFocus
            disabled={savedState !== null}
            className="bg-surface border-border rounded-md border px-2 py-1 text-sm disabled:opacity-60"
            placeholder={t('newTextFile.namePlaceholder')}
            value={name}
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                if (savedState !== null) {
                  void save()
                } else {
                  void create()
                }
              }
            }}
          />
          <LazyMarkdownEditor
            value={content}
            onChange={setContent}
            ariaLabel={t('newTextFile.contentLabel')}
            drawings={drawings}
            drawingAdapter={drawingAdapter}
            aiHelper={{
              courseId: courseId ?? undefined,
              title: name.trim() || t('newTextFile.title'),
            }}
          />
          {error !== null ? <p className="text-destructive text-xs">{error}</p> : null}
        </div>
        <footer className="border-border flex justify-end gap-2 border-t px-4 py-2">
          <Button variant="ghost" size="sm" onClick={onCancel} disabled={busy}>
            {savedState !== null ? t('newTextFile.done') : t('library.cancelEdit')}
          </Button>
          {savedState !== null ? (
            <Button size="sm" onClick={() => void save()} disabled={busy || !changed}>
              {t('newTextFile.save')}
            </Button>
          ) : (
            <Button size="sm" disabled={!name.trim() || busy} onClick={() => void create()}>
              {t('newTextFile.create')}
            </Button>
          )}
        </footer>
      </div>
    </div>
  )
}
