import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { Editor } from '@tiptap/react'
import {
  Check,
  FileText,
  MoveDown,
  RotateCcw,
  Sparkles,
  X,
} from 'lucide-react'

import {
  insertMarkdown,
  textBetween,
  type InsertMarkdownMode,
  type SelectionRange,
} from '@/components/editor/insertMarkdown'
import { LazyMarkdownEditor } from '@/components/editor/LazyMarkdownEditor'
import { MarkdownPreview } from '@/components/editor/MarkdownPreview'
import { Button } from '@/components/ui/button'
import { FlowStatusCard, type FlowStep } from '@/components/ui/flow-status'
import { FloatingPanel } from './FloatingPanel'
import { cn } from '@/lib/utils'

import { EDITOR_PRESETS, type EditorPresetKey } from './editorPresets'
import { useEditorTransform } from './useEditorTransform'

export interface AiHelperContext {
  courseId?: number
  nodeId?: number
  title: string
}

interface RunParams {
  text: string
  instruction: string
  preset: EditorPresetKey | null
  mode: 'transform' | 'write'
  includeContext: boolean
  groundInMaterial: boolean
}

const MAX_DOC_TEXT = 12_000
const CONTEXT_AROUND = 2000
const CONTEXT_CAP = 6000

export function AiHelperPopover({
  editor,
  context,
  selectionRef,
  closeSignal,
  onInsert,
}: {
  editor: Editor | null
  context: AiHelperContext
  selectionRef: { current: SelectionRange | null }
  closeSignal: number
  onInsert: () => void
}) {
  const { t } = useTranslation()
  const transform = useEditorTransform()
  const [instruction, setInstruction] = useState('')
  const [includeContext, setIncludeContext] = useState(true)
  const [groundInMaterial, setGroundInMaterial] = useState(false)
  const [resultEdit, setResultEdit] = useState('')
  const [editing, setEditing] = useState(false)
  const [hadSelection, setHadSelection] = useState(false)
  const paramsRef = useRef<RunParams | null>(null)

  useEffect(() => {
    if (transform.status === 'done') {
      setResultEdit(transform.result)
      setEditing(false)
    }
  }, [transform.status, transform.result])

  const currentSelection = (): SelectionRange | null =>
    editor === null ? null : selectionRef.current

  const selectionActive = (): boolean => {
    const selection = currentSelection()
    return selection !== null && selection.from !== selection.to
  }

  const selectedText = (): string => {
    if (editor === null) {
      return ''
    }
    const selection = currentSelection()
    if (selection === null || selection.from === selection.to) {
      return ''
    }
    return textBetween(editor, selection.from, selection.to)
  }

  const contextDocument = (): string => {
    if (editor === null) {
      return ''
    }
    const selection = currentSelection()
    if (selection === null) {
      return ''
    }
    return textBetween(
      editor,
      Math.max(1, selection.from - CONTEXT_AROUND),
      selection.to + CONTEXT_AROUND
    ).slice(0, CONTEXT_CAP)
  }

  const run = (params: RunParams) => {
    paramsRef.current = params
    setHadSelection(params.mode === 'transform' && params.text.trim().length > 0)
    void transform.start({
      text: params.text,
      instruction: params.instruction,
      preset: params.preset,
      mode: params.mode,
      include_context: params.includeContext,
      context_document: params.includeContext ? contextDocument() : '',
      ground_in_material: params.groundInMaterial,
      course_id: context.courseId ?? null,
      node_id: context.nodeId ?? null,
    })
  }

  const runPreset = (key: EditorPresetKey) => {
    const text = selectedText()
    if (!text.trim()) {
      return
    }
    run({
      text,
      instruction: '',
      preset: key,
      mode: 'transform',
      includeContext,
      groundInMaterial,
    })
  }

  const runWholeNote = () => {
    if (editor === null) {
      return
    }
    const text = editor.getText().slice(0, MAX_DOC_TEXT)
    if (!text.trim()) {
      return
    }
    run({
      text,
      instruction: '',
      preset: 'compact',
      mode: 'transform',
      includeContext: false,
      groundInMaterial,
    })
  }

  const runFreeForm = () => {
    const custom = instruction.trim()
    if (!custom) {
      return
    }
    const text = selectedText()
    const useSelection = text.trim().length > 0
    run({
      text: useSelection ? text : '',
      instruction: custom,
      preset: null,
      mode: useSelection ? 'transform' : 'write',
      includeContext,
      groundInMaterial,
    })
    setInstruction('')
  }

  const retry = () => {
    if (paramsRef.current !== null) {
      run(paramsRef.current)
    }
  }

  const discard = () => {
    transform.reset()
    setResultEdit('')
    setInstruction('')
  }

  const insert = (mode: InsertMarkdownMode) => {
    if (editor === null) {
      return
    }
    insertMarkdown(
      editor,
      resultEdit,
      mode,
      mode === 'replace-selection' ? currentSelection() : null
    )
    transform.reset()
    setResultEdit('')
    onInsert()
  }

  const keepEditorFocus = (event: React.MouseEvent) => {
    const target = event.target as HTMLElement
    if (target.closest('textarea, input, [contenteditable="true"]')) {
      return
    }
    event.preventDefault()
  }

  const contextChip = (
    enabled: boolean,
    label: string,
    toggle: () => void
  ) => (
    <button
      type="button"
      aria-pressed={enabled}
      onClick={toggle}
      className={cn(
        'border-border rounded-full border px-2 py-0.5 text-[11px]',
        enabled
          ? 'bg-primary text-primary-foreground border-transparent'
          : 'text-muted-foreground hover:text-foreground'
      )}
    >
      {label}
    </button>
  )

  const renderIdleView = () => {
    const hasSelection = selectionActive()
    return (
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto">
        <div>
          <textarea
            value={instruction}
            onChange={(event) => setInstruction(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                runFreeForm()
              }
            }}
            placeholder={t('editor.ai.placeholder')}
            rows={2}
            aria-label={t('editor.ai.promptLabel')}
            className="bg-subtle border-border text-foreground placeholder:text-muted-foreground focus:border-primary w-full resize-none rounded-md border p-2 text-sm outline-none"
          />
          <div className="mt-1.5 flex items-center justify-between gap-2">
            <span className="text-muted-foreground text-[11px]">
              {hasSelection
                ? t('editor.ai.selectionHint')
                : t('editor.ai.noSelectionHint')}
            </span>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={!instruction.trim()}
              onClick={runFreeForm}
              aria-label={t('editor.ai.run')}
            >
              {t('editor.ai.run')}
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1">
          {contextChip(includeContext, t('editor.ai.includeContext'), () =>
            setIncludeContext((value) => !value)
          )}
          {context.courseId !== undefined
            ? contextChip(groundInMaterial, t('editor.ai.groundInMaterial'), () =>
                setGroundInMaterial((value) => !value)
              )
            : null}
        </div>

        <div className="border-border rounded-md border p-2">
          <p className="text-muted-foreground mb-2 text-[11px] font-medium tracking-wide uppercase">
            {t('editor.ai.transformTitle')}
          </p>
          <div className="grid grid-cols-2 gap-1">
            {EDITOR_PRESETS.map((preset) => (
              <button
                key={preset.key}
                type="button"
                disabled={!hasSelection}
                onClick={() => runPreset(preset.key)}
                className={cn(
                  'text-muted-foreground hover:bg-subtle hover:text-foreground flex items-center gap-1.5 rounded px-2 py-1.5 text-left text-xs',
                  !hasSelection && 'opacity-40'
                )}
                aria-label={t(preset.labelKey)}
              >
                <preset.icon className="size-4 shrink-0" aria-hidden />
                {t(preset.labelKey)}
              </button>
            ))}
          </div>
          {!hasSelection ? (
            <div className="mt-2 flex items-center justify-between gap-2 border-t pt-2">
              <span className="text-muted-foreground text-[11px]">
                {t('editor.ai.selectToTransform')}
              </span>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={runWholeNote}
                aria-label={t('editor.ai.wholeNote')}
              >
                <FileText className="size-3.5" aria-hidden />
                {t('editor.ai.wholeNote')}
              </Button>
            </div>
          ) : null}
        </div>
      </div>
    )
  }

  const flowTitle = t('editor.ai.flowTitle', { title: context.title })

  const flowSteps = (transformRunning: boolean): FlowStep[] => [
    {
      id: 'transform',
      label: t('editor.ai.stepTransform'),
      status: transformRunning ? 'running' : 'failed',
    },
    { id: 'review', label: t('editor.ai.stepReview'), status: 'pending' },
  ]

  const renderRunningView = () => (
    <div className="flex min-h-0 flex-1 flex-col space-y-2">
      <FlowStatusCard
        title={flowTitle}
        steps={flowSteps(true)}
        status="running"
        onCancel={() => void transform.stop()}
        labels={{ cancel: t('editor.ai.stop') }}
        className="shrink-0"
      />
      <div className="bg-subtle border-primary/40 text-foreground min-h-0 w-full flex-1 overflow-y-auto rounded-md border p-2 text-xs leading-relaxed whitespace-pre-wrap">
        {transform.result}
        <span className="animate-pulse after:content-['▍']" aria-hidden />
      </div>
      <div className="flex shrink-0 items-center">
        <span className="text-muted-foreground text-[11px]">
          {t('editor.ai.streaming')}
        </span>
      </div>
    </div>
  )

  const renderReviewView = () => (
    <div className="flex min-h-0 flex-1 flex-col space-y-2">
      <div className="min-h-0 flex-1 overflow-y-auto">
        {editing ? (
          <LazyMarkdownEditor
            value={resultEdit}
            onChange={setResultEdit}
            ariaLabel={t('editor.ai.resultLabel')}
          />
        ) : (
          <div className="border-border bg-subtle w-full rounded-md border p-3">
            <MarkdownPreview markdown={resultEdit} />
          </div>
        )}
      </div>
      <div className="flex shrink-0 items-center justify-between">
        <p className="text-muted-foreground text-[11px]">
          {t('editor.ai.chars', { count: resultEdit.length })}
        </p>
        <button
          type="button"
          onClick={() => setEditing((value) => !value)}
          className="text-muted-foreground hover:text-foreground text-[11px] underline-offset-2 hover:underline"
        >
          {editing ? t('editor.ai.preview') : t('editor.ai.edit')}
        </button>
      </div>
      <div className="flex flex-wrap justify-end gap-1">
        <Button
          type="button"
          size="sm"
          disabled={!hadSelection}
          onClick={() => insert('replace-selection')}
        >
          <Check className="size-3.5" aria-hidden />
          {t('editor.ai.replaceSelection')}
        </Button>
        <Button type="button" size="sm" onClick={() => insert('after-block')}>
          <MoveDown className="size-3.5" aria-hidden />
          {t('editor.ai.insertBelow')}
        </Button>
        <Button type="button" size="sm" onClick={() => insert('at-cursor')}>
          {t('editor.ai.insertAtCursor')}
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={retry}>
          <RotateCcw className="size-3.5" aria-hidden />
          {t('editor.ai.regenerate')}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={discard}>
          <X className="size-3.5" aria-hidden />
          {t('editor.ai.discard')}
        </Button>
      </div>
    </div>
  )

  const renderErrorView = () => (
    <div className="min-h-0 flex-1 space-y-2 overflow-y-auto">
      <FlowStatusCard
        title={flowTitle}
        steps={flowSteps(false)}
        status="failed"
        error={{
          code: 'editor_ai_error',
          message: transform.error ?? t('editor.ai.flowFailed'),
          retryable: paramsRef.current !== null,
        }}
        onRetry={retry}
        labels={{ retry: t('editor.ai.retry') }}
      />
      <div className="flex justify-end gap-1">
        <Button type="button" size="sm" variant="ghost" onClick={discard}>
          {t('editor.ai.discard')}
        </Button>
      </div>
    </div>
  )

  return (
    <FloatingPanel
      label={t('editor.ai.helper')}
      closeSignal={closeSignal}
      focusOnOpen={false}
      preserveFocus
      minWidth={288}
      minHeight={200}
      panelClassName="w-[26rem]"
      trigger={<Sparkles className="text-primary size-4" aria-hidden />}
    >
      {() => (
        <div
          className="flex min-h-0 flex-1 flex-col space-y-1"
          onMouseDown={keepEditorFocus}
        >
          <div className="flex shrink-0 items-center justify-between">
            <p className="text-muted-foreground text-xs">
              {t('editor.ai.title', { title: context.title })}
            </p>
            {transform.status !== 'idle' ? (
              <button
                type="button"
                aria-label={t('editor.ai.discard')}
                className="text-muted-foreground hover:text-foreground rounded p-1"
                onClick={discard}
              >
                <X className="size-3.5" aria-hidden />
              </button>
            ) : null}
          </div>
          {transform.status === 'running'
            ? renderRunningView()
            : transform.status === 'done'
              ? renderReviewView()
              : transform.status === 'error'
                ? renderErrorView()
                : renderIdleView()}
        </div>
      )}
    </FloatingPanel>
  )
}