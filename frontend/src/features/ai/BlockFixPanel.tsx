import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, CircleAlert, RotateCcw, Sparkles, Wrench, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { FlowStatusCard } from '@/components/ui/flow-status'
import {
  useAiTextTransform,
  type AiTextTransformTransport,
} from '@/components/ui/ai-text-transform'
import { TextDiffView } from '@/components/ui/text-diff-view'
import { cn } from '@/lib/utils'
import type { BlockFixGateResult, BlockGateKind } from '@/lib/blockGate'
import type { EditorTransformRequest } from '@/lib/api'
import { useEditorTransformTransport } from './useEditorTransformTransport'

export type { BlockFixGateResult } from '@/lib/blockGate'

export type BlockFixKind = BlockGateKind

export function BlockFixPanel({
  kind,
  source,
  diagnostic,
  courseId,
  validate,
  tier0Repair,
  transport,
  onApply,
  onDiscard,
}: {
  kind: BlockFixKind
  source: string
  diagnostic: string
  courseId?: number
  validate: (text: string) => Promise<BlockFixGateResult>
  tier0Repair?: (source: string) => Promise<string | null>
  transport?: AiTextTransformTransport
  onApply: (fixed: string) => void
  onDiscard: () => void
}) {
  const { t } = useTranslation()
  const requestRef = useRef<EditorTransformRequest | null>(null)
  const derivedTransport = useEditorTransformTransport(requestRef)
  const activeTransport = transport ?? derivedTransport
  const transform = useAiTextTransform({ transport: activeTransport })
  const [proposed, setProposed] = useState<string | null>(null)
  const [gate, setGate] = useState<BlockFixGateResult | null>(null)
  const [deterministic, setDeterministic] = useState(false)
  const [prompt, setPrompt] = useState('')

  const preset = kind === 'mermaid' ? 'fix_mermaid' : 'fix_math'
  const flowTitle = t('editor.ai.fix.title')

  const startAi = useCallback(
    (customInstruction: string) => {
      requestRef.current = {
        text: source,
        instruction: customInstruction,
        preset,
        mode: 'transform',
        include_context: false,
        context_document: '',
        ground_in_material: false,
        course_id: courseId ?? null,
        node_id: null,
        diagnostic,
      }
      void transform.start()
    },
    [courseId, diagnostic, preset, source, transform]
  )

  const askAi = useCallback(() => {
    setDeterministic(false)
    setProposed(null)
    setGate(null)
    transform.reset()
    startAi(prompt.trim())
  }, [prompt, startAi, transform])

  const run = useCallback(() => {
    setDeterministic(false)
    setProposed(null)
    setGate(null)
    if (tier0Repair !== undefined) {
      void tier0Repair(source).then((repaired) => {
        if (repaired !== null && repaired !== source) {
          setDeterministic(true)
          setProposed(repaired)
          return
        }
        startAi(prompt.trim())
      })
      return
    }
    startAi(prompt.trim())
  }, [prompt, source, startAi, tier0Repair])

  const startedRef = useRef(false)
  useEffect(() => {
    if (startedRef.current) {
      return
    }
    startedRef.current = true
    void run()
  }, [run])

  useEffect(() => {
    if (transform.status === 'done') {
      setProposed(transform.result)
    }
  }, [transform.status, transform.result])

  useEffect(() => {
    if (proposed === null) {
      setGate(null)
      return
    }
    let cancelled = false
    setGate(null)
    void validate(proposed).then((result) => {
      if (!cancelled) {
        setGate(result)
      }
    })
    return () => {
      cancelled = true
    }
  }, [proposed, validate])

  const gateOk = gate !== null && gate.ok
  const gateFailed = gate !== null && !gate.ok

  if (proposed !== null) {
    return (
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <span
            className={cn(
              'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px]',
              deterministic
                ? 'border-success/30 bg-success/10 text-success'
                : 'border-primary/30 bg-primary/10 text-primary'
            )}
          >
            {deterministic ? (
              <Wrench className="size-3" aria-hidden />
            ) : (
              <Sparkles className="size-3" aria-hidden />
            )}
            {t(deterministic ? 'editor.ai.fix.deterministic' : 'editor.ai.fix.proposed')}
          </span>
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
        {gateFailed && gate.error ? (
          <p className="text-danger bg-danger/10 rounded-md p-2 font-mono text-[11px] break-words">
            {gate.error}
          </p>
        ) : null}
        <div className="border-border max-h-56 overflow-y-auto rounded-md border p-2">
          <TextDiffView
            original={source}
            suggested={proposed}
            className="w-full"
            labels={{
              original: t('diff.original'),
              suggested: t('diff.suggested'),
              unchangedLines: (count) => t('diff.unchangedLines', { count }),
              showLess: t('diff.showLess'),
              prevChange: t('diff.prevChange'),
              nextChange: t('diff.nextChange'),
              changePosition: (index, total) => t('diff.changePosition', { index, total }),
            }}
          />
        </div>
        <div className="flex items-center gap-1">
          <input
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                askAi()
              }
            }}
            placeholder={t('editor.ai.fix.askPlaceholder')}
            aria-label={t('editor.ai.fix.askLabel')}
            className="bg-subtle border-border text-foreground placeholder:text-muted-foreground focus:border-primary min-w-0 flex-1 rounded-md border px-2 py-1.5 text-xs outline-none"
          />
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={transform.status === 'running'}
            onClick={askAi}
          >
            <Sparkles className="size-3.5" aria-hidden />
            {t('editor.ai.fix.ask')}
          </Button>
        </div>
        <div className="flex justify-end gap-1">
          <Button type="button" size="sm" disabled={!gateOk} onClick={() => onApply(proposed)}>
            <Check className="size-3.5" aria-hidden />
            {t('editor.ai.fix.apply')}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={askAi}
          >
            <RotateCcw className="size-3.5" aria-hidden />
            {t('editor.ai.fix.regenerate')}
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={onDiscard}>
            <X className="size-3.5" aria-hidden />
            {t('editor.ai.fix.discard')}
          </Button>
        </div>
      </div>
    )
  }

  if (transform.status === 'error') {
    return (
      <div className="space-y-2">
        <FlowStatusCard
          title={flowTitle}
          steps={[{ id: 'fix', label: t('editor.ai.fix.running'), status: 'failed' }]}
          status="failed"
          error={{
            code: 'block_fix_error',
            message: transform.error ?? t('editor.ai.fix.failed'),
            retryable: true,
          }}
          onRetry={() => void run()}
          labels={{ retry: t('editor.ai.retry') }}
        />
        <div className="flex justify-end">
          <Button type="button" size="sm" variant="ghost" onClick={onDiscard}>
            <X className="size-3.5" aria-hidden />
            {t('editor.ai.fix.discard')}
          </Button>
        </div>
      </div>
    )
  }

  if (transform.status === 'running' || transform.status === 'done') {
    return (
      <div className="space-y-2">
        <FlowStatusCard
          title={flowTitle}
          steps={[{ id: 'fix', label: t('editor.ai.fix.running'), status: 'running' }]}
          status="running"
          onCancel={() => void transform.stop()}
          labels={{ cancel: t('editor.ai.stop') }}
        />
        <div className="bg-subtle min-h-16 overflow-y-auto rounded-md p-2 font-mono text-xs whitespace-pre-wrap">
          {transform.result}
        </div>
      </div>
    )
  }

  return (
    <FlowStatusCard
      title={flowTitle}
      steps={[{ id: 'fix', label: t('editor.ai.fix.running'), status: 'pending' }]}
      status="running"
    />
  )
}
