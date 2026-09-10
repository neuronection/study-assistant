import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { Editor } from '@tiptap/react'
import {
  Check,
  CircleAlert,
  Code,
  Columns2,
  Eye,
  FileText,
  MoveDown,
  RotateCcw,
  Sparkles,
  TextSelect,
  Wrench,
  X,
} from 'lucide-react'

import {
  captureSelection,
  summaryTotalBlocks,
  type CapturedSelection,
} from '@/components/editor/selectionCapture'
import {
  insertMarkdown,
  textBetween,
  type InsertMarkdownMode,
  type SelectionRange,
} from '@/components/editor/insertMarkdown'
import { MarkdownPreview } from '@/components/editor/MarkdownPreview'
import {
  extractBlock,
  validateBlockSource,
  type BlockFixGateResult,
  type BlockGateKind,
} from '@/lib/blockGate'
import { repairMermaidSource } from '@/lib/mermaidRepair'
import { Button } from '@/components/ui/button'
import { FlowStatusCard, type FlowStep } from '@/components/ui/flow-status'
import { FloatingPanel } from './FloatingPanel'
import { SelectionSummaryChip, selectionScopeLabel } from './SelectionSummaryChip'
import { useEditorTransformTransport } from './useEditorTransformTransport'
import { SegmentedControl } from '@/components/motion/SegmentedControl'
import { cn } from '@/lib/utils'

import { EDITOR_PRESETS, type EditorPresetKey } from './editorPresets'
import { useAiTextTransform } from '@/components/ui/ai-text-transform'
import { TextDiffView } from '@/components/ui/text-diff-view'
import type { EditorTransformRequest } from '@/lib/api'

export interface AiHelperContext {
  courseId?: number
  nodeId?: number
  title: string
}

type TransformScope = 'selection' | 'document'

type ReviewMode = 'diff' | 'formatted' | 'raw'

const REVIEW_MODES: {
  key: ReviewMode
  icon: React.ComponentType<{ className?: string }>
  labelKey: string
}[] = [
  { key: 'diff', icon: Columns2, labelKey: 'editor.ai.viewDiff' },
  { key: 'formatted', icon: Eye, labelKey: 'editor.ai.viewFormatted' },
  { key: 'raw', icon: Code, labelKey: 'editor.ai.viewRaw' },
]

const PANEL_WIDE_PX = 600

interface RunParams {
  text: string
  original?: string
  instruction: string
  preset: EditorPresetKey | string | null
  mode: 'transform' | 'write'
  scope: TransformScope
  range: SelectionRange | null
  capture: CapturedSelection | null
  fixKind: BlockGateKind | null
  diagnostic: string | null
  includeContext: boolean
  groundInMaterial: boolean
}

const MAX_DOC_TEXT = 12_000
const CONTEXT_AROUND = 2000
const CONTEXT_CAP = 6000

function captureBlockKind(capture: CapturedSelection | null): BlockGateKind | null {
  if (capture === null || summaryTotalBlocks(capture.summary) !== 1) {
    return null
  }
  if (capture.summary.diagrams === 1) {
    return 'mermaid'
  }
  if (capture.summary.formulas === 1) {
    return 'math'
  }
  return null
}

function captureHasBlocks(capture: CapturedSelection | null): boolean {
  return (
    capture !== null &&
    capture.summary.diagrams +
      capture.summary.formulas +
      capture.summary.codeBlocks +
      capture.summary.tables +
      capture.summary.imagesDrawings >
      0
  )
}

function fixPreset(kind: BlockGateKind): string {
  return kind === 'mermaid' ? 'fix_mermaid' : 'fix_math'
}

function wrapBlockSource(
  kind: BlockGateKind,
  source: string,
  display: boolean
): string {
  return kind === 'mermaid'
    ? '```mermaid\n' + source + '\n```'
    : display
      ? `$$${source}$$`
      : `$${source}$`
}

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
  const [instruction, setInstruction] = useState('')
  const [includeContext, setIncludeContext] = useState(true)
  const [groundInMaterial, setGroundInMaterial] = useState(false)
  const [resultEdit, setResultEdit] = useState('')
  const [ranScope, setRanScope] = useState<TransformScope>('selection')
  const [ranMode, setRanMode] = useState<'transform' | 'write'>('transform')
  const [ranOriginal, setRanOriginal] = useState('')
  const [reviewMode, setReviewMode] = useState<ReviewMode>('diff')
  const [panelWide, setPanelWide] = useState(false)
  const [rootEl, setRootEl] = useState<HTMLDivElement | null>(null)
  const [captured, setCaptured] = useState<CapturedSelection | null>(null)
  const [gate, setGate] = useState<BlockFixGateResult | null>(null)
  const [directReview, setDirectReview] = useState(false)
  const [deterministicFix, setDeterministicFix] = useState(false)
  const paramsRef = useRef<RunParams | null>(null)
  const requestRef = useRef<EditorTransformRequest | null>(null)
  const aiTransport = useEditorTransformTransport(requestRef)

  const transform = useAiTextTransform({ transport: aiTransport })

  const capture = useCallback(
    (): CapturedSelection | null =>
      editor === null ? null : captureSelection(editor),
    [editor]
  )

  useEffect(() => {
    setCaptured(capture())
  }, [capture])

  useEffect(() => {
    if (rootEl === null || typeof ResizeObserver === 'undefined') {
      return
    }
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      const width =
        entry.borderBoxSize && entry.borderBoxSize.length > 0
          ? entry.borderBoxSize[0].inlineSize
          : (entry.contentRect?.width ?? 0)
      setPanelWide(width >= PANEL_WIDE_PX)
    })
    observer.observe(rootEl)
    return () => observer.disconnect()
  }, [rootEl])

  useEffect(() => {
    if (transform.status === 'done') {
      setResultEdit(transform.result)
      setReviewMode(paramsRef.current?.mode === 'write' ? 'formatted' : 'diff')
    }
  }, [transform.status, transform.result])

  const reviewActive = directReview || transform.status === 'done'

  const reviewKind = reviewActive
    ? captureBlockKind(paramsRef.current?.capture ?? null)
    : null
  const reviewExtracted =
    reviewKind !== null ? extractBlock(reviewKind, resultEdit) : null
  const gateExpected = reviewKind !== null && reviewExtracted !== null
  const gateOk = gateExpected && gate !== null && gate.ok
  const gateFailed = gateExpected && gate !== null && !gate.ok
  const crossKind = reviewKind !== null && reviewExtracted === null
  const showMarkdownHint =
    ranScope === 'selection' &&
    (crossKind ||
      (reviewKind === null && captureHasBlocks(paramsRef.current?.capture ?? null)))

  useEffect(() => {
    const kind = gateExpected ? reviewKind : null
    if (kind === null) {
      setGate(null)
      return
    }
    const extracted = extractBlock(kind, resultEdit)
    if (extracted === null) {
      setGate(null)
      return
    }
    let cancelled = false
    setGate(null)
    void validateBlockSource(kind, extracted.source, extracted.display).then(
      (result) => {
        if (!cancelled) {
          setGate(result)
        }
      }
    )
    return () => {
      cancelled = true
    }
  }, [gateExpected, reviewKind, resultEdit])

  const currentSelection = (): SelectionRange | null =>
    editor === null ? null : selectionRef.current

  const contextDocument = (): string => {
    if (editor === null) {
      return ''
    }
    const selection = currentSelection()
    if (selection === null || selection.from === selection.to) {
      return editor.getText().slice(0, CONTEXT_CAP)
    }
    return textBetween(
      editor,
      Math.max(1, selection.from - CONTEXT_AROUND),
      selection.to + CONTEXT_AROUND
    ).slice(0, CONTEXT_CAP)
  }

  const documentText = (): string => {
    if (editor === null || (editor as { schema?: unknown }).schema === null) {
      return ''
    }
    return editor.getText().slice(0, MAX_DOC_TEXT)
  }

  const run = (params: RunParams) => {
    setRanScope(params.scope)
    setRanMode(params.mode)
    setRanOriginal(params.original ?? params.text)
    setDeterministicFix(false)
    setDirectReview(false)
    setGate(null)
    paramsRef.current = params
    requestRef.current = {
      text: params.text,
      instruction: params.instruction,
      preset: params.preset,
      mode: params.mode,
      include_context: params.includeContext,
      context_document: params.includeContext ? contextDocument() : '',
      ground_in_material: params.groundInMaterial,
      course_id: context.courseId ?? null,
      node_id: context.nodeId ?? null,
      ...(params.diagnostic ? { diagnostic: params.diagnostic } : {}),
    }
    void transform.start()
  }

  const runPreset = (key: EditorPresetKey) => {
    const captureNow = capture()
    const useSelection = captureNow !== null
    const text = useSelection ? captureNow.markdown : documentText()
    if (!text.trim()) {
      return
    }
    run({
      text,
      instruction: '',
      preset: key,
      mode: 'transform',
      scope: useSelection ? 'selection' : 'document',
      range: useSelection
        ? { from: captureNow.from, to: captureNow.to }
        : null,
      capture: captureNow,
      fixKind: null,
      diagnostic: null,
      includeContext: useSelection && includeContext,
      groundInMaterial,
    })
  }

  const runFreeForm = () => {
    const custom = instruction.trim()
    if (!custom) {
      return
    }
    const captureNow = capture()
    const useSelection = captureNow !== null
    run({
      text: useSelection ? captureNow.markdown : '',
      instruction: custom,
      preset: null,
      mode: useSelection ? 'transform' : 'write',
      scope: useSelection ? 'selection' : 'document',
      range: useSelection
        ? { from: captureNow.from, to: captureNow.to }
        : null,
      capture: captureNow,
      fixKind: null,
      diagnostic: null,
      includeContext,
      groundInMaterial,
    })
    setInstruction('')
  }

  const applyDeterministicFix = (
    kind: BlockGateKind,
    source: string,
    repaired: string,
    display: boolean,
    captureNow: CapturedSelection
  ) => {
    paramsRef.current = {
      text: source,
      instruction: '',
      preset: fixPreset(kind),
      mode: 'transform',
      scope: 'selection',
      range: { from: captureNow.from, to: captureNow.to },
      capture: captureNow,
      fixKind: kind,
      diagnostic: '',
      includeContext: false,
      groundInMaterial,
    }
    setRanScope('selection')
    setRanMode('transform')
    setRanOriginal(captureNow.markdown)
    setResultEdit(wrapBlockSource(kind, repaired, display))
    setReviewMode('diff')
    setDeterministicFix(true)
    setDirectReview(true)
  }

  const runFix = () => {
    const captureNow = capture()
    if (captureNow === null) {
      return
    }
    const { summary, markdown } = captureNow
    const mermaidExtract =
      summary.diagrams > 0 ? extractBlock('mermaid', markdown) : null
    const mathExtract = summary.formulas > 0 ? extractBlock('math', markdown) : null
    const kind: BlockGateKind | null =
      mermaidExtract !== null ? 'mermaid' : mathExtract !== null ? 'math' : null
    if (kind === null) {
      return
    }
    const extracted = kind === 'mermaid' ? mermaidExtract : mathExtract
    if (extracted === null) {
      return
    }
    const single = captureBlockKind(captureNow) !== null
    const source = single ? extracted.source : markdown
    void validateBlockSource(kind, source, extracted.display).then((probe) => {
      const diagnostic = probe.ok ? '' : (probe.error ?? '')
      if (single && kind === 'mermaid') {
        const repaired = repairMermaidSource(source)
        if (repaired !== null) {
          applyDeterministicFix(
            kind,
            source,
            repaired,
            extracted.display,
            captureNow
          )
          return
        }
      }
      run({
        text: source,
        original: single ? captureNow.markdown : markdown,
        instruction: '',
        preset: fixPreset(kind),
        mode: 'transform',
        scope: 'selection',
        range: { from: captureNow.from, to: captureNow.to },
        capture: captureNow,
        fixKind: single ? kind : null,
        diagnostic,
        includeContext: false,
        groundInMaterial,
      })
    })
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
    setDirectReview(false)
    setDeterministicFix(false)
    setGate(null)
  }

  const insert = (mode: InsertMarkdownMode, force = false) => {
    if (editor === null) {
      return
    }
    if (mode === 'replace-selection' && !force && gate !== null && !gate.ok) {
      return
    }
    insertMarkdown(
      editor,
      resultEdit,
      mode,
      mode === 'replace-selection' ? (paramsRef.current?.range ?? null) : null
    )
    transform.reset()
    setResultEdit('')
    setDirectReview(false)
    setDeterministicFix(false)
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
    const captureNow = captured
    const hasSelection = captureNow !== null
    const hasText = documentText().trim().length > 0
    const fixAvailable =
      captureNow !== null &&
      (captureNow.summary.diagrams > 0 || captureNow.summary.formulas > 0)
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

        {captureNow !== null ? (
          <SelectionSummaryChip summary={captureNow.summary} />
        ) : null}

        <div className="border-border rounded-md border p-2">
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="text-muted-foreground text-[11px] font-medium tracking-wide uppercase">
              {t(
                hasSelection
                  ? 'editor.ai.transformTitle'
                  : 'editor.ai.transformWholeNoteTitle'
              )}
            </p>
            <span
              className={cn(
                'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px]',
                hasSelection
                  ? 'border-primary/30 bg-primary/10 text-primary'
                  : 'border-border text-muted-foreground'
              )}
            >
              {hasSelection ? (
                <TextSelect className="size-3" aria-hidden />
              ) : (
                <FileText className="size-3" aria-hidden />
              )}
              {hasSelection
                ? selectionScopeLabel(captureNow.summary, t)
                : t('editor.ai.scopeWholeNote')}
            </span>
          </div>
          {fixAvailable ? (
            <button
              type="button"
              onClick={runFix}
              className="border-primary/30 bg-primary/10 text-primary hover:bg-primary/20 focus-visible:outline-none focus-visible:ring-ring mb-1.5 flex w-full items-center justify-center gap-1.5 rounded border px-2 py-1.5 text-xs focus-visible:ring-2"
            >
              <Wrench className="size-3.5" aria-hidden />
              {t('editor.ai.tryFix')}
            </button>
          ) : null}
          <div className="grid grid-cols-2 gap-1">
            {EDITOR_PRESETS.map((preset) => (
              <button
                key={preset.key}
                type="button"
                disabled={!hasSelection && !hasText}
                onClick={() => runPreset(preset.key)}
                className={cn(
                  'text-muted-foreground hover:bg-subtle hover:text-foreground focus-visible:outline-none focus-visible:ring-ring flex items-center gap-1.5 rounded px-2 py-1.5 text-left text-xs focus-visible:ring-2',
                  !hasSelection && !hasText && 'opacity-40'
                )}
                aria-label={t(preset.labelKey)}
              >
                <preset.icon className="size-4 shrink-0" aria-hidden />
                {t(preset.labelKey)}
              </button>
            ))}
          </div>
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

  const renderReviewView = () => {
    const showSourcePane =
      panelWide &&
      ranScope === 'selection' &&
      ranOriginal.trim().length > 0 &&
      reviewMode !== 'diff'
    return (
      <div className="flex min-h-0 flex-1 flex-col space-y-2">
        <SegmentedControl
          ariaLabel={t('editor.ai.viewLabel')}
          className="inline-flex shrink-0 self-start"
          items={REVIEW_MODES.map((mode) => ({
            value: mode.key,
            label: t(mode.labelKey),
            icon: mode.icon,
          }))}
          value={reviewMode}
          onChange={(next) => setReviewMode(next as typeof REVIEW_MODES[number]['key'])}
        />
        {deterministicFix || showMarkdownHint ? (
          <div className="flex items-center gap-2">
            {deterministicFix ? (
              <span className="border-success/30 bg-success/10 text-success inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px]">
                <Wrench className="size-3" aria-hidden />
                {t('editor.ai.fix.deterministic')}
              </span>
            ) : null}
            {showMarkdownHint ? (
              <span className="border-border text-muted-foreground inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px]">
                {t('editor.ai.appliesAsMarkdown')}
              </span>
            ) : null}
          </div>
        ) : null}
        <div className="flex min-h-0 flex-1 gap-2">
          {showSourcePane ? (
            <div className="border-border bg-subtle w-52 shrink-0 overflow-y-auto rounded-md border p-2">
              <p className="text-muted-foreground mb-1 text-[11px] font-medium tracking-wide uppercase">
                {t('diff.original')}
              </p>
              <pre className="text-foreground/80 font-mono text-[11px] leading-relaxed whitespace-pre-wrap">
                {ranOriginal}
              </pre>
            </div>
          ) : null}
          <div className="min-h-0 flex-1 flex">
            {reviewMode === 'diff' ? (
              <TextDiffView
                original={ranOriginal}
                suggested={resultEdit}
                className="w-full"
                labels={{
                  original: t('diff.original'),
                  suggested: t('diff.suggested'),
                  unchangedLines: (count) => t('diff.unchangedLines', { count }),
                  showLess: t('diff.showLess'),
                  prevChange: t('diff.prevChange'),
                  nextChange: t('diff.nextChange'),
                  changePosition: (index, total) =>
                    t('diff.changePosition', { index, total }),
                }}
              />
            ) : reviewMode === 'formatted' ? (
              <div className="border-border bg-subtle w-full rounded-md border p-3">
                <MarkdownPreview markdown={resultEdit} />
              </div>
            ) : (
              <textarea
                value={resultEdit}
                onChange={(event) => setResultEdit(event.target.value)}
                aria-label={t('editor.ai.resultLabel')}
                className="bg-subtle border-border text-foreground min-h-full w-full resize-none rounded-md border p-3 font-mono text-xs leading-relaxed outline-none"
              />
            )}
          </div>
        </div>
        {gateFailed && gate !== null && gate.error ? (
          <p
            role="alert"
            className="text-danger bg-danger/10 rounded-md p-2 font-mono text-[11px] break-words"
          >
            {gate.error}
          </p>
        ) : null}
        <div className="flex shrink-0 items-center justify-between">
          <p className="text-muted-foreground text-[11px]">
            {t('editor.ai.chars', { count: resultEdit.length })}
          </p>
          {gateOk ? (
            <span className="text-success inline-flex items-center gap-1 text-[11px]">
              <Check className="size-3.5" aria-hidden />
              {t('editor.ai.fix.gateOk')}
            </span>
          ) : gateFailed ? (
            <span className="text-danger inline-flex items-center gap-1 text-[11px]">
              <CircleAlert className="size-3.5" aria-hidden />
              {t('editor.ai.fix.gateFail')}
            </span>
          ) : null}
        </div>
        <div className="flex flex-wrap justify-end gap-1">
          {ranMode === 'transform' ? (
            ranScope === 'selection' ? (
              <Button
                type="button"
                size="sm"
                disabled={gateExpected && !gateOk}
                onClick={() => insert('replace-selection')}
              >
                <Check className="size-3.5" aria-hidden />
                {t('editor.ai.replaceSelection')}
              </Button>
            ) : (
              <Button
                type="button"
                size="sm"
                onClick={() => insert('replace-document')}
              >
                <Check className="size-3.5" aria-hidden />
                {t('editor.ai.replaceNote')}
              </Button>
            )
          ) : null}
          {gateFailed ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => insert('replace-selection', true)}
            >
              {t('editor.ai.insertAsMarkdown')}
            </Button>
          ) : null}
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
  }

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
          ref={setRootEl}
          className="flex min-h-0 flex-1 flex-col space-y-1"
          onMouseDown={keepEditorFocus}
        >
          <div className="flex shrink-0 items-center justify-between">
            <p className="text-muted-foreground text-xs">
              {t('editor.ai.title', { title: context.title })}
            </p>
            {transform.status !== 'idle' || directReview ? (
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
          {transform.status === 'running' && !directReview
            ? renderRunningView()
            : reviewActive
              ? renderReviewView()
              : transform.status === 'error'
                ? renderErrorView()
                : renderIdleView()}
        </div>
      )}
    </FloatingPanel>
  )
}
