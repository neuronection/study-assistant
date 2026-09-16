import {
  BookOpen,
  Calculator,
  Compass,
  Globe,
  HelpCircle,
  LineChart,
  Link2,
  Sigma,
  SlidersHorizontal,
  Wrench,
  type LucideIcon,
} from 'lucide-react'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { answerQuizQuestion } from '@/lib/api'
import type { ChatToolCall } from '@/lib/api'
import { useChatStore } from '@/lib/chat-store'
import { useQueryClient } from '@tanstack/react-query'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import type { ChatToolCardProps } from '@/components/ui/chat-tool-card'

export interface ToolMeta {
  icon: LucideIcon
  labelKey: string | null
  phase: string
}

const TOOL_META: Record<string, ToolMeta> = {
  CALC: { icon: Calculator, labelKey: 'chat.tool.calc', phase: 'computing' },
  SYMPY: { icon: Sigma, labelKey: 'chat.tool.sympy', phase: 'computing' },
  READ: { icon: BookOpen, labelKey: 'chat.tool.read', phase: 'reading' },
  STATE: { icon: SlidersHorizontal, labelKey: 'chat.tool.state', phase: 'reading' },
  PLOT: { icon: LineChart, labelKey: 'chat.tool.plot', phase: 'plotting' },
  FIND: { icon: BookOpen, labelKey: 'chat.tool.find', phase: 'reading' },
  SEARCH: { icon: Globe, labelKey: 'chat.tool.search', phase: 'reading' },
  DISCOVER: { icon: Compass, labelKey: 'chat.tool.discover', phase: 'reading' },
  FETCH: { icon: Link2, labelKey: 'chat.tool.fetch', phase: 'reading' },
  QUIZ: { icon: HelpCircle, labelKey: 'chat.tool.quiz', phase: 'reading' },
}

export function getToolMeta(name: string): ToolMeta {
  return TOOL_META[name] ?? { icon: Wrench, labelKey: null, phase: 'computing' }
}

export interface ToolViewProps {
  tool: ChatToolCall
}

type ToolView = (props: ToolViewProps) => ReactNode

function MathResultView({ tool }: ToolViewProps) {
  if (!tool.result) {
    return null
  }
  return <div className="text-foreground font-mono text-sm">= {tool.result}</div>
}

function PlotResultView() {
  const { t } = useTranslation()
  return <div className="text-muted-foreground text-xs">{t('chat.tool.chartNote')}</div>
}

function StateResultView() {
  const { t } = useTranslation()
  return <div className="text-muted-foreground text-xs">{t('chat.tool.stateNote')}</div>
}

const URL_RE = /https?:\/\/[^\s)\]>"]+/g

function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

function SearchResultsView({ tool }: ToolViewProps) {
  if (!tool.result) {
    return null
  }
  const urls = Array.from(new Set(tool.result.match(URL_RE) ?? []))
  if (urls.length === 0) {
    return <GenericResultView tool={tool} />
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {urls.map((url) => (
        <a
          key={url}
          href={url}
          target="_blank"
          rel="noreferrer"
          className="bg-subtle text-primary hover:bg-primary/10 flex max-w-full items-center gap-1 rounded-full px-2 py-0.5 text-[11px]"
          title={url}
        >
          <Globe className="size-3 shrink-0" aria-hidden />
          <span className="truncate">{domainOf(url)}</span>
        </a>
      ))}
    </div>
  )
}

function FetchResultView({ tool }: ToolViewProps) {
  if (!tool.result) {
    return null
  }
  const url = tool.argument.trim()
  const domain = domainOf(url)
  return (
    <div className="text-muted-foreground text-xs">
      <a
        href={url.startsWith('http') ? url : undefined}
        target="_blank"
        rel="noreferrer"
        className="text-primary hover:underline"
      >
        {domain}
      </a>
      {` · ${tool.result}`}
    </div>
  )
}

function QuizCardView({ tool }: ToolViewProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const session = useChatStore((state) => state.session)
  const quiz = tool.quiz ?? null
  const [answer, setAnswer] = useState('')
  const [choice, setChoice] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [verdict, setVerdict] = useState<{
    correct: boolean
    detail: string
    expected: string | null
  } | null>(
    quiz?.answered
      ? {
          correct: quiz.verdict === 'correct',
          detail: quiz.verdict_detail ?? '',
          expected: quiz.expected_display ?? null,
        }
      : null,
  )
  if (!quiz?.question) {
    return <GenericResultView tool={tool} />
  }
  const sessionId = session?.id ?? null
  const interactive = !verdict && sessionId !== null

  const submit = async (value: string | number) => {
    if (sessionId === null || busy) {
      return
    }
    setBusy(true)
    try {
      const result = await answerQuizQuestion(sessionId, value)
      setVerdict({
        correct: result.correct,
        detail: result.verdict_detail,
        expected: result.expected_display,
      })
      await queryClient.invalidateQueries({ queryKey: ['chat-messages', sessionId] })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-2">
      <p className="text-foreground text-sm font-medium">{quiz.question}</p>
      {quiz.choices && quiz.choices.length > 0 ? (
        <div className="space-y-1">
          {quiz.choices.map((option, index) => {
            const chosen = choice === index
            const isCorrect =
              verdict !== null && quiz.expected_display === option
            return (
              <button
                key={index}
                type="button"
                disabled={!interactive}
                className={cn(
                  'border-border bg-surface flex w-full items-center gap-2 rounded-md border px-2.5 py-1.5 text-left text-sm',
                  interactive && 'hover:bg-subtle',
                  chosen && 'border-primary',
                  verdict !== null && isCorrect && 'border-success text-success',
                  verdict !== null &&
                    chosen &&
                    !verdict.correct &&
                    'border-danger text-danger'
                )}
                onClick={() => {
                  setChoice(index)
                  void submit(index)
                }}
              >
                <span className="text-muted-foreground font-mono text-[11px]">
                  {String.fromCharCode(65 + index)}
                </span>
                {option}
              </button>
            )
          })}
        </div>
      ) : verdict !== null ? (
        <p className="bg-subtle text-muted-foreground rounded-md p-2 text-xs">
          {t('chat.quiz.yourAnswer')}: {quiz.student_answer}
        </p>
      ) : (
        <div className="flex gap-1.5">
          <input
            className="bg-surface border-border min-w-0 flex-1 rounded-md border px-2 py-1.5 text-sm"
            placeholder={t('chat.quiz.answerPlaceholder')}
            value={answer}
            onChange={(event) => setAnswer(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && answer.trim()) {
                void submit(answer.trim())
              }
            }}
          />
          <Button
            size="sm"
            disabled={!answer.trim() || busy}
            onClick={() => void submit(answer.trim())}
          >
            {t('chat.quiz.submit')}
          </Button>
        </div>
      )}
      {verdict !== null ? (
        <p
          className={cn(
            'rounded-md px-2 py-1 text-xs font-medium',
            verdict.correct ? 'bg-success/15 text-success' : 'bg-danger/15 text-danger'
          )}
        >
          {verdict.correct ? t('chat.quiz.correct') : t('chat.quiz.incorrect')}
          {verdict.expected !== null && !verdict.correct
            ? ` · ${t('chat.quiz.expected', { answer: verdict.expected })}`
            : null}
        </p>
      ) : null}
    </div>
  )
}

function GenericResultView({ tool }: ToolViewProps) {
  if (!tool.result) {
    return null
  }
  return (
    <pre className="bg-subtle border-border overflow-x-auto rounded-md border p-2 font-mono text-[11px] whitespace-pre-wrap break-all">
      {tool.result}
    </pre>
  )
}

const TOOL_VIEWS: Record<string, ToolView> = {
  CALC: MathResultView,
  SYMPY: MathResultView,
  READ: GenericResultView,
  STATE: StateResultView,
  PLOT: PlotResultView,
  SEARCH: SearchResultsView,
  DISCOVER: SearchResultsView,
  FETCH: FetchResultView,
  QUIZ: QuizCardView,
}

export function getToolView(name: string): ToolView {
  return TOOL_VIEWS[name] ?? GenericResultView
}

type Translate = (key: string) => string

/**
 * Maps a chat tool call onto the library `ChatToolCard` (plan 12 §6: the
 * registry stays app-side feeding icon / labels / `renderResult`). The
 * header shows the backend-provided title or the argument as summary;
 * result views render through the `renderResult` slot — STATE keeps its
 * note even without a serialized result, QUIZ cards open by default.
 */
export function toolCardProps(tool: ChatToolCall, t: Translate): ChatToolCardProps {
  const meta = getToolMeta(tool.name)
  const summary = tool.title ?? tool.argument
  const status: ChatToolCardProps['status'] =
    tool.status === 'failed'
      ? 'failed'
      : tool.status === 'done' || (tool.result !== null && tool.result !== undefined)
        ? 'done'
        : 'running'
  return {
    name: tool.name,
    title: summary || undefined,
    status,
    args: tool.argument || undefined,
    result: tool.result ?? undefined,
    durationMs: tool.duration_ms ?? undefined,
    icon: meta.icon,
    defaultOpen: tool.name === 'QUIZ',
    labels: {
      args: t('chat.tool.argument'),
      result: t('chat.tool.result'),
    },
    renderResult: () => {
      const ResultView = getToolView(tool.name)
      const showResult =
        (tool.result !== null && tool.result !== undefined) || tool.name === 'STATE'
      return showResult ? <ResultView tool={tool} /> : null
    },
  }
}

export function formatDuration(ms: number | null | undefined): string | null {
  if (ms === null || ms === undefined) {
    return null
  }
  if (ms < 1000) {
    return `${Math.max(0, Math.round(ms))} ms`
  }
  return `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)} s`
}
