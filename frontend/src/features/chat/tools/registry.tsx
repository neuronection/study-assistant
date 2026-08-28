import {
  BookOpen,
  Calculator,
  LineChart,
  Sigma,
  SlidersHorizontal,
  Wrench,
  type LucideIcon,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import type { ChatToolCall } from '@/lib/api'

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
}

export function getToolView(name: string): ToolView {
  return TOOL_VIEWS[name] ?? GenericResultView
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
