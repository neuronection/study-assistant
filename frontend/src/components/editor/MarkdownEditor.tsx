import type { Editor } from '@tiptap/react'
import { StarterKit } from '@tiptap/starter-kit'
import { TableCell, TableHeader, TableRow } from '@tiptap/extension-table'
import {
  Copy,
  Loader2,
  MoreHorizontal,
  MoveDown,
  PenTool,
  RefreshCw,
  Trash2,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { createPortal } from 'react-dom'
import { Markdown } from 'tiptap-markdown'

import { BlockRenderer } from '@/components/blocks/BlockRenderer'
import type { Block } from '@/components/blocks/types'
import {
  DrawCanvas,
  exportDrawing,
  strokeBounds,
  type Stroke,
  type ViewBox,
} from '@/components/canvas/DrawCanvas'
import { DictationStrip, useDictation } from '@/components/ui/dictation'
import { insertMarkdown, type InsertMarkdownMode } from '@/components/editor/insertMarkdown'
import {
  transcribeViaGateway,
  classifyDictationError,
} from '@/lib/dictation'
import {
  DrawingDiffContext,
  type DrawingDiffStore,
  type DrawingOcrDiff,
} from '@/components/editor/drawingDiffContext'
import {
  createDrawingImage,
  drawingSrc,
  type DrawingAction,
  type DrawingActionHandler,
  type DrawingMeta,
} from '@/components/editor/DrawingImage'

export type { DrawingMeta }
import { CaMath } from '@/components/editor/CaMath'
import { CaMermaid } from '@/components/editor/CaMermaid'
import { MarkdownTable } from '@/components/editor/MarkdownTable'
import { StudyToolbarButtons } from '@/components/editor/StudyToolbarButtons'
import { BlankLineParagraph, decodeMarkdownFromSerialize, encodeMarkdownForParse, stripBlankMarkers } from '@/components/editor/markdownFidelity'
import { RichTextEditor } from '@/components/ui/rich-text-editor'
import { InfoButton } from '@/components/ui/InfoButton'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { PopoverMenu } from '@/components/ui/popover-menu'
import { cn } from '@/lib/utils'
import { useConfirm } from '@/lib/use-confirm'
import type { AiHelperContext } from '@/features/ai/AiHelperPopover'

export interface MarkdownEditorApi {
  insertDrawing: (id: number) => void
  removeDrawing: (id: number) => void
  insertQuote: (text: string, source: { title: string; materialId: number } | null) => void
  insertMarkdown: (markdown: string, mode: InsertMarkdownMode) => void
}

export interface DrawingAdapter {
  create: (strokes: Stroke[], pngBase64: string, ocr: boolean, view?: ViewBox) => Promise<number | null>
  update: (drawingId: number, strokes: Stroke[], pngBase64: string, ocr: boolean, view?: ViewBox) => Promise<void>
  reocr: (drawingId: number) => Promise<void>
  remove: (drawingId: number) => Promise<void>
}

const EDITOR_CONTENT_CLASS =
  'prose-notes bg-surface w-full min-h-56 p-3 text-sm [&_blockquote]:border-l-2 [&_blockquote]:border-border [&_blockquote]:pl-3 [&_code]:bg-subtle [&_code]:rounded [&_code]:px-1 [&_code]:font-mono [&_code]:text-xs [&_h2]:text-lg [&_h2]:font-semibold [&_h3]:text-base [&_h3]:font-semibold [&_pre]:bg-subtle [&_pre]:rounded-md [&_pre]:p-3 [&_pre]:font-mono [&_pre]:text-xs [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_table]:w-full [&_table]:border-collapse [&_th]:border [&_th]:border-border [&_th]:p-1 [&_th]:text-left [&_td]:border [&_td]:border-border [&_td]:p-1'

export function MarkdownEditor({
  value,
  onChange,
  ariaLabel,
  drawings,
  drawingAdapter,
  apiRef,
  aiHelper,
  onSnapRegion,
}: {
  value: string
  onChange: (markdown: string) => void
  ariaLabel: string
  drawings?: DrawingMeta[]
  drawingAdapter?: DrawingAdapter
  apiRef?: { current: MarkdownEditorApi | null }
  aiHelper?: AiHelperContext
  onSnapRegion?: () => void
}) {
  const { t } = useTranslation()
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange
  const drawingsRef = useRef<DrawingMeta[]>(drawings ?? [])
  drawingsRef.current = drawings ?? []
  const drawingAdapterRef = useRef<DrawingAdapter | undefined>(drawingAdapter)
  drawingAdapterRef.current = drawingAdapter
  const editorRef = useRef<Editor | null>(null)
  const [activeEditor, setActiveEditor] = useState<Editor | null>(null)
  const [aiCloseSignal, setAiCloseSignal] = useState(0)
  const selectionRef = useRef<{ from: number; to: number } | null>(null)
  const dictation = useDictation({
    transcribe: transcribeViaGateway,
    classifyError: classifyDictationError,
    onResult: (text) => {
      const current = editorRef.current
      if (current !== null && !current.isDestroyed) {
        insertMarkdown(current, text, 'at-cursor')
      }
    },
  })
  const [canvas, setCanvas] = useState<{ open: boolean; editingId: number | null }>({
    open: false,
    editingId: null,
  })
  const [canvasFocus, setCanvasFocus] = useState<ViewBox | null>(null)
  const [canvasFullscreen, setCanvasFullscreen] = useState(false)
  const [strokes, setStrokes] = useState<Stroke[]>([])
  const [ocrOn, setOcrOn] = useState(true)
  const [savingCanvas, setSavingCanvas] = useState(false)
  const [canvasError, setCanvasError] = useState<string | null>(null)
  const [ocrBaselines, setOcrBaselines] = useState<Map<number, { before: string; sawJob: boolean }>>(
    new Map()
  )
  const [ocrDiffs, setOcrDiffs] = useState<Map<number, DrawingOcrDiff>>(new Map())
  const [confirm, confirmElement] = useConfirm()

  const handleDrawingAction = useRef<DrawingActionHandler>(
    (id: number, action: DrawingAction) => {
      if (action === 'copy') {
        const meta = drawingsRef.current.find((entry) => entry.id === id)
        if (meta?.ocr_markdown && navigator.clipboard) {
          void navigator.clipboard.writeText(meta.ocr_markdown)
        }
        return
      }
      if (action === 'reocr') {
        const meta = drawingsRef.current.find((entry) => entry.id === id)
        setOcrBaselines((current) => {
          const next = new Map(current)
          next.set(id, { before: meta?.ocr_markdown ?? '', sawJob: false })
          return next
        })
        drawingAdapterRef.current?.reocr(id).catch((error: unknown) => {
          setOcrBaselines((current) => {
            const next = new Map(current)
            next.delete(id)
            return next
          })
          setCanvasError(error instanceof Error ? error.message : String(error))
        })
        return
      }
      if (action === 'delete') {
        removeDrawingNodes(editorRef.current, id)
        drawingAdapterRef.current?.remove(id).catch((error: unknown) => {
          setCanvasError(error instanceof Error ? error.message : String(error))
        })
        return
      }
      const meta = drawingsRef.current.find((entry) => entry.id === id)
      const editStrokes = Array.isArray(meta?.strokes) ? (meta.strokes as Stroke[]) : []
      setStrokes(editStrokes)
      setCanvasFocus(meta?.view ?? strokeBounds(editStrokes, 24))
      setCanvasError(null)
      setCanvas({ open: true, editingId: id })
    }
  )

  const drawingImage = useMemo(
    () =>
      createDrawingImage(
        (id: number) => drawingsRef.current.find((drawing) => drawing.id === id),
        handleDrawingAction.current
      ),
    []
  )

  const extensions = useMemo(
    () => [
      StarterKit.configure({
        paragraph: false,
        link: {
          protocols: ['http', 'https', 'mailto', 'ca-material', 'ca-drawing', 'mention'],
        },
      }),
      BlankLineParagraph,
      CaMath,
      CaMermaid,
      MarkdownTable,
      TableRow,
      TableCell,
      TableHeader,
      drawingImage.extension,
      Markdown.configure({ html: false, breaks: true, linkify: false }),
    ],
    [drawingImage]
  )

  const handleReady = useCallback((instance: Editor | null) => {
    editorRef.current = instance
    setActiveEditor(instance)
    if (instance !== null) {
      instance.on('selectionUpdate', ({ editor: current }) => {
        const { from, to } = current.state.selection
        if (from !== to) {
          selectionRef.current = { from, to }
        } else if (current.isFocused) {
          selectionRef.current = null
        }
      })
    }
  }, [])

  const handleChange = useCallback((markdown: string) => {
    onChangeRef.current(markdown)
  }, [])

  const openCanvas = useCallback(() => {
    setStrokes([])
    setCanvasFocus(null)
    setCanvasFullscreen(false)
    setCanvasError(null)
    setCanvas({ open: true, editingId: null })
  }, [])

  const handleAiInsert = useCallback(() => {
    setAiCloseSignal((signal) => signal + 1)
  }, [])

  const insertDrawingAtCursor = (id: number) => {
    const current = editorRef.current
    if (current === null || current.isDestroyed) {
      return
    }
    current
      .chain()
      .focus()
      .insertContent({
        type: 'image',
        attrs: { src: drawingSrc(id), alt: t('notes.drawingRefAlt') },
      })
      .run()
  }

  const removeDrawingNodes = (current: Editor | null, drawingId: number) => {
    if (current === null || current.isDestroyed) {
      return
    }
    const src = drawingSrc(drawingId)
    const tr = current.state.tr
    const matches: Array<[number, number]> = []
    current.state.doc.descendants((node, pos) => {
      if (node.type.name === 'image' && String(node.attrs.src ?? '') === src) {
        matches.push([pos, pos + node.nodeSize])
      }
    })
    for (const [from, to] of matches.reverse()) {
      tr.delete(from, to)
    }
    if (matches.length > 0) {
      current.view.dispatch(tr)
      current.commands.focus()
    }
  }

  useEffect(() => {
    if (apiRef) {
      apiRef.current = {
        insertDrawing: insertDrawingAtCursor,
        removeDrawing: (id: number) => {
          removeDrawingNodes(editorRef.current, id)
        },
        insertMarkdown: (markdown: string, mode: InsertMarkdownMode) => {
          const current = editorRef.current
          if (current !== null && !current.isDestroyed) {
            insertMarkdown(current, markdown, mode)
          }
        },
        insertQuote: (text: string, source) => {
          const lines = text
            .split('\n')
            .map((line) => line.trim())
            .filter((line) => line.length > 0)
          if (lines.length === 0) {
            return
          }
          const content: Record<string, unknown>[] = [
            {
              type: 'blockquote',
              content: lines.map((line) => ({
                type: 'paragraph',
                content: [{ type: 'text', text: line }],
              })),
            },
          ]
          if (source !== null) {
            content.push({
              type: 'paragraph',
              content: [
                { type: 'text', text: '— ' },
                {
                  type: 'text',
                  marks: [
                    { type: 'link', attrs: { href: `ca-material://${source.materialId}` } },
                  ],
                  text: source.title,
                },
              ],
            })
          }
          const current = editorRef.current
          if (current === null || current.isDestroyed) {
            return
          }
          current.chain().focus().insertContent(content).run()
        },
      }
    }
  })

  useEffect(
    () => () => {
      if (apiRef) {
        apiRef.current = null
      }
    },
    [apiRef]
  )

  const lastSyncedRef = useRef(value)
  useEffect(() => {
    const current = editorRef.current
    if (current === null || current.isDestroyed) {
      return
    }
    if (value !== lastSyncedRef.current) {
      lastSyncedRef.current = value
      selectionRef.current = null
    }
    stripBlankMarkers(current)
  }, [value, activeEditor])

  useEffect(() => {
    const current = editorRef.current
    if (current === null || current.isDestroyed) {
      return
    }
    drawingImage.refresh()
  }, [drawings, activeEditor, drawingImage])

  useEffect(() => {
    if (ocrBaselines.size === 0) {
      return
    }
    const settled: { id: number; before: string; after: string }[] = []
    const dropped: number[] = []
    const started: number[] = []
    for (const [id, baseline] of ocrBaselines) {
      const meta = (drawings ?? []).find((entry) => entry.id === id)
      if (meta === undefined) {
        dropped.push(id)
        continue
      }
      if (meta.ocr_job_id) {
        started.push(id)
        continue
      }
      if (!baseline.sawJob) {
        continue
      }
      settled.push({ id, before: baseline.before, after: meta.ocr_markdown ?? '' })
    }
    if (settled.length === 0 && dropped.length === 0 && started.length === 0) {
      return
    }
    let changed = false
    const next = new Map(ocrBaselines)
    for (const entry of settled) {
      if (next.delete(entry.id)) {
        changed = true
      }
    }
    for (const id of dropped) {
      if (next.delete(id)) {
        changed = true
      }
    }
    for (const id of started) {
      const baseline = next.get(id)
      if (baseline !== undefined && !baseline.sawJob) {
        next.set(id, { ...baseline, sawJob: true })
        changed = true
      }
    }
    if (!changed) {
      return
    }
    setOcrBaselines(next)
    if (settled.length > 0) {
      setOcrDiffs((current) => {
        const next = new Map(current)
        for (const { id, before, after } of settled) {
          if (after !== before) {
            next.set(id, { before, after })
          }
        }
        return next
      })
    }
  }, [drawings, ocrBaselines])

  const dismissOcrDiff = useCallback((drawingId: number) => {
    setOcrDiffs((current) => {
      if (!current.has(drawingId)) {
        return current
      }
      const next = new Map(current)
      next.delete(drawingId)
      return next
    })
  }, [])

  const drawingDiffStore = useMemo<DrawingDiffStore>(
    () => ({ diffs: ocrDiffs, dismiss: dismissOcrDiff }),
    [ocrDiffs, dismissOcrDiff]
  )

  const closeCanvas = () => {
    setCanvas({ open: false, editingId: null })
    setStrokes([])
    setCanvasFocus(null)
    setCanvasFullscreen(false)
    setCanvasError(null)
  }

  const saveCanvas = async () => {
    const adapter = drawingAdapterRef.current
    if (adapter === undefined || strokes.length === 0) {
      return
    }
    const exported = exportDrawing(strokes)
    if (!exported) {
      setCanvasError(t('notes.canvasUnavailable'))
      return
    }
    const pngBase64 = exported.dataUrl.split(',')[1] ?? ''
    const view = exported.view
    setSavingCanvas(true)
    setCanvasError(null)
    try {
      if (canvas.editingId !== null) {
        await adapter.update(canvas.editingId, strokes, pngBase64, ocrOn, view)
      } else {
        const id = await adapter.create(strokes, pngBase64, ocrOn, view)
        if (id !== null) {
          insertDrawingAtCursor(id)
        }
      }
      setCanvas({ open: false, editingId: null })
      setStrokes([])
      setCanvasFocus(null)
      setCanvasFullscreen(false)
    } catch (error) {
      setCanvasError(error instanceof Error ? error.message : String(error))
    } finally {
      setSavingCanvas(false)
    }
  }

  const referencedIds = new Set(
    [...value.matchAll(/\(ca-drawing:\/\/(-?\d+)\)/g)].map((match) => Number(match[1]))
  )
  const unreferencedDrawings = (drawings ?? []).filter(
    (drawing) => !referencedIds.has(drawing.id)
  )

  return (
    <DrawingDiffContext.Provider value={drawingDiffStore}>
    <div className="flex min-h-0 flex-1 flex-col space-y-1">
      <div
      data-testid="editor-chrome"
      className="group/editor flex min-h-0 flex-1 flex-col [&_[data-as=rich-text-editor]]:flex [&_[data-as=rich-text-editor]]:min-h-0 [&_[data-as=rich-text-editor]]:flex-1 [&_[data-as=rich-text-editor]]:flex-col [&_[data-as=rich-text-editor]>div:not([role=toolbar])]:min-h-0 [&_[data-as=rich-text-editor]>div:not([role=toolbar])]:flex-1 [&_[data-as=rich-text-editor]>div:not([role=toolbar])]:overflow-y-auto [&_[role=toolbar]]:opacity-0 [&_[role=toolbar]]:transition-opacity [&_[role=toolbar]]:duration-150 hover:[&_[role=toolbar]]:opacity-100 focus-within:[&_[role=toolbar]]:opacity-100 motion-reduce:[&_[role=toolbar]]:transition-none"
      >
      <RichTextEditor
        value={value}
        onValueChange={handleChange}
        ariaLabel={ariaLabel}
        extensions={extensions}
        parseMarkdown={encodeMarkdownForParse}
        serializeMarkdown={decodeMarkdownFromSerialize}
        toolbar={['history', 'heading', 'format', 'list', 'quote']}
        headingLevels={[2, 3]}
        labels={{
          toolbar: t('editor.toolbar'),
          undo: t('editor.undo'),
          redo: t('editor.redo'),
          bold: t('editor.bold'),
          italic: t('editor.italic'),
          strike: t('editor.strike'),
          code: t('editor.code'),
          heading: (level) => (level === 2 ? t('editor.heading2') : t('editor.heading3')),
          bulletList: t('editor.bulletList'),
          orderedList: t('editor.orderedList'),
          blockquote: t('editor.quote'),
        }}
        contentClassName={EDITOR_CONTENT_CLASS}
        toolbarExtra={(editor) => (
          <>
          <StudyToolbarButtons
            editor={editor}
            hasCanvas={drawingAdapter !== undefined}
            onOpenCanvas={openCanvas}
            onSnapRegion={onSnapRegion}
            aiHelper={aiHelper}
            aiSelectionRef={selectionRef}
            aiCloseSignal={aiCloseSignal}
            onAiInsert={handleAiInsert}
            dictationStatus={dictation.status}
            onDictationStart={() => void dictation.start()}
          />
          <InfoButton
            label={t('editor.editorHelp')}
            title={t('editor.mathHelpTitle')}
            className="ml-auto self-center"
          >
            {t('editor.mathHint')}
          </InfoButton>
          </>
        )}
        onReady={handleReady}
      />
      </div>
      <DictationStrip
        status={dictation.status}
        seconds={dictation.seconds}
        levelRef={dictation.levelRef}
        error={dictation.error}
        labels={{
          stop: t('dictation.stop'),
          cancel: t('dictation.cancel'),
          recording: t('dictation.recording'),
          transcribing: t('dictation.transcribing'),
          unsupported: t('dictation.unsupported'),
          denied: t('dictation.denied'),
          unassigned: t('dictation.unassigned'),
          failed: t('dictation.failedHint', { detail: '{detail}' }),
        }}
        onStop={() => void dictation.stop()}
        onCancel={dictation.cancel}
        onDismissError={dictation.dismissError}
      />
      {canvasError && !canvas.open ? (
        <p className="text-warning text-xs" role="alert">
          {canvasError}
        </p>
      ) : null}
      {unreferencedDrawings.map((drawing) => (
        <Card key={drawing.id}>
          <CardContent className="space-y-2 p-4">
            {drawing.png_sha ? (
              <img
                src={`/api/v1/blobs/${drawing.png_sha}`}
                alt={t('notes.drawingAlt')}
                className="border-border max-w-full rounded-md border"
              />
            ) : null}
            {drawing.ocr_markdown ? (
              <div className="text-sm">
                <BlockRenderer
                  blocks={[{ type: 'text', md: drawing.ocr_markdown }] as Block[]}
                />
              </div>
            ) : drawing.ocr_job_id ? (
              <p className="text-muted-foreground flex items-center gap-1.5 text-xs">
                <Loader2 className="size-3 animate-spin" aria-hidden />
                {t('notes.ocrPending')}
              </p>
            ) : (
              <p className="text-muted-foreground text-xs">{t('notes.notTranscribed')}</p>
            )}
            <div className="flex items-center justify-between">
              {drawing.ocr_version !== undefined ? (
                <span className="text-muted-foreground text-[11px]">
                  {t('notes.ocrVersion', { version: drawing.ocr_version })}
                </span>
              ) : (
                <span />
              )}
              <div className="flex items-center gap-1">
                <Button variant="ghost" size="sm" onClick={() => insertDrawingAtCursor(drawing.id)}>
                  <MoveDown aria-hidden />
                  {t('notes.insertInline')}
                </Button>
                <PopoverMenu
                  label={t('notes.drawingMoreActions')}
                  trigger={<MoreHorizontal className="size-4" aria-hidden />}
                  items={[
                    {
                      key: 'edit',
                      label: t('notes.editDrawing'),
                      icon: PenTool,
                      onSelect: () => handleDrawingAction.current(drawing.id, 'edit'),
                    },
                    ...(drawing.png_sha && !drawing.png_sha.startsWith('data:')
                      ? [
                          {
                            key: 'reocr',
                            label: t('notes.reocrDrawing'),
                            icon: RefreshCw,
                            onSelect: () => handleDrawingAction.current(drawing.id, 'reocr'),
                          },
                        ]
                      : []),
                    ...(drawing.ocr_markdown
                      ? [
                          {
                            key: 'copy',
                            label: t('notes.copyOcr'),
                            icon: Copy,
                            onSelect: () => handleDrawingAction.current(drawing.id, 'copy'),
                          },
                        ]
                      : []),
                    {
                      key: 'delete',
                      label: t('notes.deleteDrawing'),
                      icon: Trash2,
                      danger: true,
                      onSelect: async () => {
                        const ok = await confirm({
                          title: t('notes.deleteDrawing'),
                          description: t('notes.confirmDeleteDrawing'),
                          confirmLabel: t('notes.deleteDrawing'),
                          cancelLabel: t('common.cancel'),
                          destructive: true,
                        })
                        if (ok) handleDrawingAction.current(drawing.id, 'delete')
                      },
                    },
                  ]}
                />
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
      {canvas.open
        ? createPortal(
            <>
              <div
                className="fixed inset-0 z-40 bg-black/30"
                onClick={closeCanvas}
                aria-hidden
              />
              <div
                role="dialog"
                aria-label={t('editor.drawTitle')}
                className={cn(
                  'bg-surface border-border animate-in fixed z-50 flex flex-col shadow-lg motion-reduce:animate-none',
                  canvasFullscreen
                    ? 'inset-0 h-full max-h-full w-full rounded-none border-0'
                    : 'top-1/2 left-1/2 max-h-[85vh] w-[min(56rem,92vw)] -translate-x-1/2 -translate-y-1/2 rounded-lg border p-4'
                )}
                onKeyDown={(event) => {
                  if (event.key === 'Escape') {
                    if (canvasFullscreen) {
                      setCanvasFullscreen(false)
                    } else {
                      closeCanvas()
                    }
                  }
                }}
              >
                <div className="mb-2 flex items-center justify-between gap-2">
                  <p className="text-muted-foreground text-xs">
                    {canvas.editingId !== null
                      ? t('notes.editingDrawingHint')
                      : t('notes.drawHint')}
                  </p>
                  <button
                    type="button"
                    aria-label={t('editor.close')}
                    className="text-muted-foreground hover:text-foreground rounded p-1"
                    onClick={closeCanvas}
                  >
                    <X className="size-4" aria-hidden />
                  </button>
                </div>
                {canvasError ? (
                  <p className="text-warning mb-2 text-xs" role="alert">
                    {canvasError}
                  </p>
                ) : null}
                <div className={canvasFullscreen ? 'flex-1 min-h-0' : 'flex-1 overflow-y-auto'}>
                  <DrawCanvas
                    strokes={strokes}
                    onChange={setStrokes}
                    focus={canvasFocus}
                    fullscreen={canvasFullscreen}
                    onToggleFullscreen={() => setCanvasFullscreen((value) => !value)}
                    fillContainer={canvasFullscreen}
                  />
                </div>
                <div className="border-border mt-3 flex flex-wrap items-center justify-between gap-2 border-t pt-3">
                  <label className="text-muted-foreground flex items-center gap-2 text-xs">
                    <input
                      type="checkbox"
                      checked={ocrOn}
                      onChange={(event) => setOcrOn(event.target.checked)}
                    />
                    {t('notes.ocrToggle')}
                  </label>
                  <div className="flex gap-2">
                    {canvas.editingId !== null ? (
                      <Button variant="outline" size="sm" onClick={closeCanvas}>
                        {t('notes.cancelDrawingEdit')}
                      </Button>
                    ) : null}
                    <Button
                      size="sm"
                      disabled={strokes.length === 0 || savingCanvas}
                      onClick={() => void saveCanvas()}
                    >
                      {savingCanvas ? (
                        <Loader2 className="animate-spin" aria-hidden />
                      ) : null}
                      {t('notes.saveDrawing')}
                    </Button>
                  </div>
                </div>
              </div>
            </>,
            document.body
          )
        : null}
      {confirmElement}
    </div>
    </DrawingDiffContext.Provider>
  )
}
