import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, X } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { BlockRenderer } from '@/components/blocks/BlockRenderer'
import type { Block } from '@/components/blocks/types'
import type { DrawingAdapter } from '@/components/editor/MarkdownEditor'
import { LazyMarkdownEditor } from '@/components/editor/LazyMarkdownEditor'
import { ReadAloudButton } from '@/components/read-aloud/ReadAloudButton'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import {
  addMaterialDrawing,
  deleteMaterialDrawing,
  editExtraction,
  getMaterial,
  reocrMaterialDrawing,
  setMaterialDescription,
  updateMaterialDrawing,
} from '@/lib/api'
import { useTextSelection } from '@/lib/useTextSelection'
import { useDrawingOcrSync } from '@/lib/useDrawingOcrSync'
import { askMaterial } from '@/features/chat/useMaterialAsk'
import { MindmapViewer } from './MindmapViewer'
import { SelectionToolbar } from './SelectionToolbar'
import { isTextMaterial } from './textMaterial'
import { SegmentedControl } from '@/components/motion/SegmentedControl'

type EditTab = 'content' | 'description'

export function ExtractionView({
  materialId,
  scopeNodeId,
  onQuoteSelection,
}: {
  materialId: number
  scopeNodeId?: number
  onQuoteSelection?: (text: string) => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [draftDescription, setDraftDescription] = useState('')
  const [editTab, setEditTab] = useState<EditTab>('content')
  const contentRef = useRef<HTMLDivElement>(null)
  const { capture, clear } = useTextSelection(contentRef)
  const { data, isLoading } = useQuery({
    queryKey: ['material', materialId],
    queryFn: () => getMaterial(materialId),
  })

  const drawingAdapter = useMemo<DrawingAdapter>(
    () => ({
      create: async (strokes, pngBase64, ocr, view) => {
        const updated = await addMaterialDrawing(materialId, strokes, pngBase64, ocr, view)
        const known = new Set((data?.drawings ?? []).map((entry) => entry.id))
        const fresh = updated.drawings.find((entry) => !known.has(entry.id))
        await queryClient.setQueryData(['material', materialId], updated)
        await queryClient.invalidateQueries({ queryKey: ['material', materialId] })
        await queryClient.invalidateQueries({ queryKey: ['materials'] })
        return fresh?.id ?? null
      },
      update: async (drawingId, strokes, pngBase64, ocr, view) => {
        const updated = await updateMaterialDrawing(
          materialId,
          drawingId,
          strokes,
          pngBase64,
          ocr,
          view
        )
        await queryClient.setQueryData(['material', materialId], updated)
        await queryClient.invalidateQueries({ queryKey: ['material', materialId] })
        await queryClient.invalidateQueries({ queryKey: ['materials'] })
      },
      reocr: async (drawingId) => {
        await reocrMaterialDrawing(materialId, drawingId)
        await queryClient.invalidateQueries({ queryKey: ['material', materialId] })
      },
      remove: async (drawingId) => {
        const updated = await deleteMaterialDrawing(materialId, drawingId)
        await queryClient.setQueryData(['material', materialId], updated)
        await queryClient.invalidateQueries({ queryKey: ['material', materialId] })
        await queryClient.invalidateQueries({ queryKey: ['materials'] })
      },
    }),
    [materialId, data, queryClient]
  )
  useDrawingOcrSync(data?.drawings, () => {
    void queryClient.invalidateQueries({ queryKey: ['material', materialId] })
    void queryClient.invalidateQueries({ queryKey: ['materials'] })
  })

  const save = useMutation({
    mutationFn: async () => {
      await editExtraction(materialId, draft)
      if (
        data !== undefined &&
        isTextMaterial(data.material) &&
        draftDescription !== (data.material.description ?? '')
      ) {
        await setMaterialDescription(materialId, draftDescription)
      }
    },
    onSuccess: async () => {
      setEditing(false)
      await queryClient.invalidateQueries({ queryKey: ['material', materialId] })
      await queryClient.invalidateQueries({ queryKey: ['materials'] })
    },
  })

  if (isLoading) {
    return <Spinner label={t('library.loading')} />
  }
  if (!data?.extraction) {
    return (
      <p className="text-muted-foreground text-sm">
        {t('library.noExtraction', { status: data?.material.status ?? '' })}
      </p>
    )
  }
  const textMaterial = isTextMaterial(data.material)
  const startEditing = () => {
    setDraft(data.extraction?.markdown ?? '')
    setDraftDescription(data.material.description ?? '')
    setEditTab('content')
    setEditing(true)
  }
  if (editing) {
    const editTabs: EditTab[] = ['content', 'description']
    return (
      <div className="flex min-h-0 flex-1 flex-col space-y-2">
        {textMaterial ? (
          <SegmentedControl
            variant="underline"
            items={editTabs.map((entry) => ({
              value: entry,
              label: t(
                entry === 'content'
                  ? 'library.editTabContent'
                  : 'library.editTabDescription'
              ),
            }))}
            value={editTab}
            onChange={(next) => setEditTab(next as EditTab)}
          />
        ) : null}
        {editTab === 'description' && textMaterial ? (
          <textarea
            aria-label={t('library.descriptionLabel')}
            placeholder={t('library.descriptionPlaceholder')}
            value={draftDescription}
            onChange={(event) => setDraftDescription(event.target.value)}
            rows={6}
            className="bg-surface border-border min-h-24 w-full rounded-md border p-3 text-sm"
          />
        ) : (
          <LazyMarkdownEditor
            ariaLabel={t('library.editMarkdown')}
            value={draft}
            onChange={setDraft}
            drawings={data.drawings}
            drawingAdapter={drawingAdapter}
            aiHelper={{
              courseId: data.material.course_id,
              title: data.material.title,
            }}
          />
        )}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>
            <X aria-hidden />
            {t('library.cancelEdit')}
          </Button>
          <Button
            size="sm"
            disabled={save.isPending || !draft.trim()}
            onClick={() => save.mutate()}
          >
            {save.isPending ? <Spinner /> : null}
            {t('library.saveEdit')}
          </Button>
        </div>
      </div>
    )
  }
  if (data.material.provenance?.kind === 'mindmap') {
    return (
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <p className="text-muted-foreground text-xs">
            {t('library.extractionMeta', {
              version: data.extraction.version,
              extractor: data.extraction.extractor,
            })}
          </p>
          <div className="flex items-center gap-1">
            <ReadAloudButton markdown={data.extraction.markdown} />
            <Button
              variant="ghost"
              size="icon"
              title={t('library.editExtraction')}
              aria-label={t('library.editExtraction')}
              onClick={startEditing}
            >
              <Pencil aria-hidden />
            </Button>
          </div>
        </div>
        <MindmapViewer
          markdown={data.extraction.markdown}
          materialId={materialId}
          materialTitle={data.material.title}
          courseId={data.material.course_id}
          scopeNodeId={scopeNodeId ?? null}
        />
      </div>
    )
  }
  const askAboutSelection = () => {
    if (capture === null || data === undefined) {
      return
    }
    void askMaterial({
      material: data.material,
      scopeNodeId,
      content: '',
      selection: capture.text,
      attachments: [{ kind: 'material', id: materialId, title: data.material.title }],
      mode: 'prefill',
    })
    clear()
  }

  const quoteSelectionToNote = () => {
    if (capture === null) {
      return
    }
    onQuoteSelection?.(capture.text)
    clear()
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-muted-foreground text-xs">
          {t('library.extractionMeta', {
            version: data.extraction.version,
            extractor: data.extraction.extractor,
          })}
        </p>
        <div className="flex items-center gap-1">
          <ReadAloudButton markdown={data.extraction.markdown} />
          <Button
            variant="ghost"
            size="icon"
            title={t('library.editExtraction')}
            aria-label={t('library.editExtraction')}
            onClick={startEditing}
          >
            <Pencil aria-hidden />
          </Button>
        </div>
      </div>
      <div ref={contentRef}>
        {data.index_card?.summary ? (
          <p className="bg-subtle text-muted-foreground rounded-md p-3 text-xs">
            {data.index_card.summary}
          </p>
        ) : null}
        <BlockRenderer
          blocks={data.extraction.blocks as Block[]}
          resolveDrawing={(id) => data.drawings.find((entry) => entry.id === id)}
          resolveImage={(id) => data.images.find((entry) => entry.id === id)}
        />
      </div>
      {capture !== null ? (
        <SelectionToolbar
          capture={capture}
          onAsk={askAboutSelection}
          onQuote={onQuoteSelection === undefined ? undefined : quoteSelectionToNote}
        />
      ) : null}
    </div>
  )
}
