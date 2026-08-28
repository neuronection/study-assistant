import type { Editor } from '@tiptap/react'
import { EditorContent, useEditor } from '@tiptap/react'
import { StarterKit } from '@tiptap/starter-kit'
import { TableCell, TableHeader, TableRow } from '@tiptap/extension-table'
import {
  Bold,
  Code,
  Copy,
  Heading2,
  Heading3,
  Italic,
  List,
  ListOrdered,
  Loader2,
  MoreHorizontal,
  MoveDown,
  PenTool,
  Quote,
  Redo2,
  RefreshCw,
  Sigma,
  Strikethrough,
  Trash2,
  Undo2,
  Workflow,
  X,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { createPortal } from 'react-dom'
import { Markdown, type MarkdownStorage } from 'tiptap-markdown'

import { BlockRenderer } from '@/components/blocks/BlockRenderer'
import type { Block } from '@/components/blocks/types'
import {
  DrawCanvas,
  exportDrawing,
  strokeBounds,
  type Stroke,
  type ViewBox,
} from '@/components/canvas/DrawCanvas'
import { DictationMicButton, DictationStrip } from '@/components/dictation/DictationStrip'
import { useDictation } from '@/components/dictation/useDictation'
import { insertMarkdown, type InsertMarkdownMode } from '@/components/editor/insertMarkdown'
import { AiHelperPopover, type AiHelperContext } from '@/features/ai/AiHelperPopover'
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
import { BlankLineParagraph, decodeMarkdownFromSerialize, encodeMarkdownForParse, stripBlankMarkers } from '@/components/editor/markdownFidelity'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { PopoverMenu } from '@/components/ui/popover-menu'
import { cn } from '@/lib/utils'

export interface MarkdownEditorApi {
  insertDrawing: (id: number) => void
  insertQuote: (text: string, source: { title: string; materialId: number } | null) => void
  insertMarkdown: (markdown: string, mode: InsertMarkdownMode) => void
}

export interface DrawingAdapter {
  create: (strokes: Stroke[], pngBase64: string, ocr: boolean, view?: ViewBox) => Promise<number | null>
  update: (drawingId: number, strokes: Stroke[], pngBase64: string, ocr: boolean, view?: ViewBox) => Promise<void>
  reocr: (drawingId: number) => Promise<void>
  remove: (drawingId: number) => Promise<void>
}

const MERMAID_STARTER = 'flowchart TD\n  A --> B'

export function MarkdownEditor({
  value,
  onChange,
  ariaLabel,
  drawings,
  drawingAdapter,
  apiRef,
  aiHelper,
}: {
  value: string
  onChange: (markdown: string) => void
  ariaLabel: string
  drawings?: DrawingMeta[]
  drawingAdapter?: DrawingAdapter
  apiRef?: { current: MarkdownEditorApi | null }
  aiHelper?: AiHelperContext
}) {
  const { t } = useTranslation()
  const lastEmitted = useRef(value)
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange
  const drawingsRef = useRef<DrawingMeta[]>(drawings ?? [])
  drawingsRef.current = drawings ?? []
  const drawingAdapterRef = useRef<DrawingAdapter | undefined>(drawingAdapter)
  drawingAdapterRef.current = drawingAdapter
  const editorRef = useRef<Editor | null>(null)
  const [aiCloseSignal, setAiCloseSignal] = useState(0)
  const selectionRef = useRef<{ from: number; to: number } | null>(null)
  const dictation = useDictation({
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
        drawingAdapterRef.current?.reocr(id).catch((error: unknown) => {
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

  const editor = useEditor({
    extensions: [
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
    content: encodeMarkdownForParse(value),
    onUpdate: ({ editor: current }) => {
      const markdown = decodeMarkdownFromSerialize(
        (current.storage as unknown as { markdown: MarkdownStorage })
          .markdown
          .getMarkdown()
      )
      lastEmitted.current = markdown
      onChangeRef.current(markdown)
    },
    onSelectionUpdate: ({ editor: current }) => {
      const { from, to } = current.state.selection
      if (from !== to) {
        selectionRef.current = { from, to }
      } else if (current.isFocused) {
        selectionRef.current = null
      }
    },
    editorProps: {
      attributes: {
        'aria-label': ariaLabel,
        class:
          'prose-notes bg-surface w-full min-h-56 p-3 text-sm outline-none [&_blockquote]:border-l-2 [&_blockquote]:border-border [&_blockquote]:pl-3 [&_code]:bg-subtle [&_code]:rounded [&_code]:px-1 [&_code]:font-mono [&_code]:text-xs [&_h2]:text-lg [&_h2]:font-semibold [&_h3]:text-base [&_h3]:font-semibold [&_pre]:bg-subtle [&_pre]:rounded-md [&_pre]:p-3 [&_pre]:font-mono [&_pre]:text-xs [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_table]:w-full [&_table]:border-collapse [&_th]:border [&_th]:border-border [&_th]:p-1 [&_th]:text-left [&_td]:border [&_td]:border-border [&_td]:p-1',
      },
    },
  })
  editorRef.current = editor

  const insertDrawingAtCursor = (id: number) => {
    editor
      ?.chain()
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
          editor?.chain().focus().insertContent(content).run()
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

  useEffect(() => {
    if (editor === null || editor.isDestroyed) {
      return
    }
    stripBlankMarkers(editor)
    if (value === lastEmitted.current) {
      return
    }
    const currentMarkdown = decodeMarkdownFromSerialize(
      (editor.storage as unknown as { markdown: MarkdownStorage })
        .markdown.getMarkdown()
    )
    if (value === currentMarkdown) {
      lastEmitted.current = value
      return
    }
lastEmitted.current = value
    const hadFocus = editor.isFocused
    const caret = editor.state.selection.head
    selectionRef.current = null
    editor.commands.setContent(encodeMarkdownForParse(value), { emitUpdate: false })
    stripBlankMarkers(editor)
    if (hadFocus) {
      const size = editor.state.doc.content.size
      editor.commands.setTextSelection(Math.min(caret, size))
      editor.commands.focus()
    }
  }, [value, editor])

  useEffect(() => {
    if (editor === null || editor.isDestroyed) {
      return
    }
    drawingImage.refresh()
  }, [drawings, editor, drawingImage])

  if (editor === null) {
    return null
  }

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

  const toolbar: {
    key: string
    icon: React.ComponentType<{ className?: string }>
    label: string
    action: (current: Editor) => void
    active: (current: Editor) => boolean
    disabled?: (current: Editor) => boolean
  }[] = [
    { key: 'undo', icon: Undo2, label: t('editor.undo'), action: (e) => e.chain().focus().undo().run(), active: () => false, disabled: (e) => !e.can().undo() },
    { key: 'redo', icon: Redo2, label: t('editor.redo'), action: (e) => e.chain().focus().redo().run(), active: () => false, disabled: (e) => !e.can().redo() },
    { key: 'bold', icon: Bold, label: t('editor.bold'), action: (e) => e.chain().focus().toggleBold().run(), active: (e) => e.isActive('bold') },
    { key: 'italic', icon: Italic, label: t('editor.italic'), action: (e) => e.chain().focus().toggleItalic().run(), active: (e) => e.isActive('italic') },
    { key: 'strike', icon: Strikethrough, label: t('editor.strike'), action: (e) => e.chain().focus().toggleStrike().run(), active: (e) => e.isActive('strike') },
    { key: 'code', icon: Code, label: t('editor.code'), action: (e) => e.chain().focus().toggleCode().run(), active: (e) => e.isActive('code') },
    { key: 'h2', icon: Heading2, label: t('editor.heading2'), action: (e) => e.chain().focus().toggleHeading({ level: 2 }).run(), active: (e) => e.isActive('heading', { level: 2 }) },
    { key: 'h3', icon: Heading3, label: t('editor.heading3'), action: (e) => e.chain().focus().toggleHeading({ level: 3 }).run(), active: (e) => e.isActive('heading', { level: 3 }) },
    { key: 'ul', icon: List, label: t('editor.bulletList'), action: (e) => e.chain().focus().toggleBulletList().run(), active: (e) => e.isActive('bulletList') },
    { key: 'ol', icon: ListOrdered, label: t('editor.orderedList'), action: (e) => e.chain().focus().toggleOrderedList().run(), active: (e) => e.isActive('orderedList') },
    { key: 'quote', icon: Quote, label: t('editor.quote'), action: (e) => e.chain().focus().toggleBlockquote().run(), active: (e) => e.isActive('blockquote') },
    { key: 'math', icon: Sigma, label: t('editor.insertMath'), action: (e) => e.chain().focus().insertContent({ type: 'caMath', attrs: { latex: 'x', display: false, autofocus: true } }).run(), active: () => false },
    { key: 'mermaid', icon: Workflow, label: t('editor.insertMermaid'), action: (e) => e.chain().focus().insertContent({ type: 'caMermaid', attrs: { source: MERMAID_STARTER, autofocus: true } }).run(), active: () => false },
  ]

  const referencedIds = new Set(
    [...value.matchAll(/\(ca-drawing:\/\/(-?\d+)\)/g)].map((match) => Number(match[1]))
  )
  const unreferencedDrawings = (drawings ?? []).filter(
    (drawing) => !referencedIds.has(drawing.id)
  )

  return (
    <div className="space-y-1">
      <div className="bg-surface border-border flex flex-wrap gap-0.5 rounded-md border p-1" role="toolbar" aria-label={t('editor.toolbar')}>
        {toolbar.map((item) => (
          <button
            key={item.key}
            type="button"
            title={item.label}
            aria-label={item.label}
            aria-pressed={item.active(editor)}
            disabled={item.disabled?.(editor) ?? false}
            className={cn(
              'rounded p-1.5',
              item.active(editor)
                ? 'bg-subtle text-foreground'
                : 'text-muted-foreground hover:text-foreground'
            )}
            onClick={() => item.action(editor)}
          >
            <item.icon className="size-4" aria-hidden />
          </button>
        ))}
        {drawingAdapter ? (
          <button
            type="button"
            title={t('editor.insertDrawing')}
            aria-label={t('editor.insertDrawing')}
            className="text-muted-foreground hover:text-foreground rounded p-1.5"
            onClick={() => {
              setStrokes([])
              setCanvasFocus(null)
              setCanvasFullscreen(false)
              setCanvasError(null)
              setCanvas({ open: true, editingId: null })
            }}
          >
            <PenTool className="size-4" aria-hidden />
          </button>
        ) : null}
        {aiHelper ? (
          <AiHelperPopover
            editor={editor}
            context={aiHelper}
            selectionRef={selectionRef}
            closeSignal={aiCloseSignal}
            onInsert={() => setAiCloseSignal((signal) => signal + 1)}
          />
        ) : null}
        <DictationMicButton
          status={dictation.status}
          onStart={() => void dictation.start()}
          label={t('dictation.start')}
        />
      </div>
      <DictationStrip
        status={dictation.status}
        seconds={dictation.seconds}
        levelRef={dictation.levelRef}
        error={dictation.error}
        stopLabel={t('dictation.stop')}
        cancelLabel={t('dictation.cancel')}
        onStop={() => void dictation.stop()}
        onCancel={dictation.cancel}
        onDismissError={dictation.dismissError}
      />
      <div className="bg-surface border-border max-h-[65vh] overflow-y-auto rounded-md border">
        <EditorContent editor={editor} />
      </div>
      <p className="text-muted-foreground text-[11px]">{t('editor.mathHint')}</p>
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
                      onSelect: () => {
                        if (window.confirm(t('notes.confirmDeleteDrawing'))) {
                          handleDrawingAction.current(drawing.id, 'delete')
                        }
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
                  'bg-surface border-border animate-in fixed z-50 flex flex-col shadow-lg',
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
    </div>
  )
}
