import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { FileOutput, Pencil, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { BlockRenderer } from '@/components/blocks/BlockRenderer'
import type { Block } from '@/components/blocks/types'
import type { DrawingAdapter } from '@/components/editor/MarkdownEditor'
import { LazyMarkdownEditor } from '@/components/editor/LazyMarkdownEditor'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import {
  addMaterialDrawing,
  deleteMaterialDrawing,
  deriveMaterial,
  editExtraction,
  getMaterial,
  reocrMaterialDrawing,
  updateMaterialDrawing,
} from '@/lib/api'
import { useDrawingOcrSync } from '@/lib/useDrawingOcrSync'
import { MindmapViewer } from './MindmapViewer'

export function ExtractionView({
  materialId,
  scopeNodeId,
}: {
  materialId: number
  scopeNodeId?: number
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [derived, setDerived] = useState<{
    id: number
    title: string
    deduped: boolean
  } | null>(null)
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
    mutationFn: () => editExtraction(materialId, draft),
    onSuccess: async () => {
      setEditing(false)
      setDerived(null)
      await queryClient.invalidateQueries({ queryKey: ['material', materialId] })
      await queryClient.invalidateQueries({ queryKey: ['materials'] })
    },
  })

  const derive = useMutation({
    mutationFn: () => deriveMaterial(materialId, { nodeId: scopeNodeId ?? null }),
    onSuccess: async (result) => {
      setDerived({
        id: result.material.id,
        title: result.material.title,
        deduped: result.deduped,
      })
      await queryClient.invalidateQueries({ queryKey: ['materials'] })
      await queryClient.invalidateQueries({ queryKey: ['tree'] })
      await queryClient.invalidateQueries({ queryKey: ['node-workspace'] })
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
  if (editing) {
    return (
      <div className="space-y-2">
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

  const deriveButton = (
    <Button
      variant="outline"
      size="sm"
      disabled={derive.isPending}
      onClick={() => derive.mutate()}
    >
      {derive.isPending ? (
        <Spinner />
      ) : (
        <FileOutput aria-hidden />
      )}
      {t('library.deriveMaterial')}
    </Button>
  )
  const deriveFeedback = derived ? (
    <div className="bg-subtle border-border flex items-center justify-between gap-2 rounded-md border p-2 text-xs">
      <p>
        {derived.deduped
          ? t('library.deriveDuplicate')
          : t('library.deriveSuccess', { title: derived.title })}
      </p>
      <div className="flex items-center gap-1">
        <Button
          variant="ghost"
          size="sm"
          onClick={() =>
            navigate({
              to: '/library/$materialId',
              params: { materialId: String(derived.id) },
            })
          }
        >
          {t('library.deriveOpen')}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          aria-label={t('library.deriveDismiss')}
          onClick={() => setDerived(null)}
        >
          <X aria-hidden />
        </Button>
      </div>
    </div>
  ) : derive.isError ? (
    <p className="text-warning text-xs" role="alert">
      {t('library.deriveFailed')}
    </p>
  ) : null

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
          <div className="flex items-center gap-2">
            {deriveButton}
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setDraft(data.extraction?.markdown ?? '')
                setEditing(true)
              }}
            >
              <Pencil aria-hidden />
              {t('library.editExtraction')}
            </Button>
          </div>
        </div>
        {deriveFeedback}
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
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-muted-foreground text-xs">
          {t('library.extractionMeta', {
            version: data.extraction.version,
            extractor: data.extraction.extractor,
          })}
        </p>
        <div className="flex items-center gap-2">
          {deriveButton}
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setDraft(data.extraction?.markdown ?? '')
              setEditing(true)
            }}
          >
            <Pencil aria-hidden />
            {t('library.editExtraction')}
          </Button>
        </div>
      </div>
      {deriveFeedback}
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
  )
}
