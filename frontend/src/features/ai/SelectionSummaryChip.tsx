import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, Layers } from 'lucide-react'

import type { SelectionSummary } from '@/components/editor/selectionCapture'
import { summaryTotalBlocks } from '@/components/editor/selectionCapture'
import { cn } from '@/lib/utils'

type Translate = (key: string, options?: Record<string, unknown>) => string

const KIND_ORDER = [
  ['diagram', 'diagrams'],
  ['formula', 'formulas'],
  ['codeBlock', 'codeBlocks'],
  ['table', 'tables'],
  ['image', 'imagesDrawings'],
  ['text', 'textBlocks'],
] as const

const COUNT_KEYS: Record<(typeof KIND_ORDER)[number][1], string> = {
  diagrams: 'editor.ai.kind.diagram',
  formulas: 'editor.ai.kind.formula',
  codeBlocks: 'editor.ai.kind.codeBlock',
  tables: 'editor.ai.kind.table',
  imagesDrawings: 'editor.ai.kind.image',
  textBlocks: 'editor.ai.kind.text',
}

export function selectionSummaryParts(
  summary: SelectionSummary,
  t: Translate
): { key: string; countKey: string; count: number; label: string }[] {
  return KIND_ORDER.map(([key, countKey]) => {
    const count = summary[countKey]
    return {
      key,
      countKey,
      count,
      label: t(COUNT_KEYS[countKey], { count }),
    }
  }).filter((part) => part.count > 0)
}

export function selectionScopeLabel(
  summary: SelectionSummary,
  t: Translate
): string {
  const parts = selectionSummaryParts(summary, t)
  if (parts.length === 1) {
    return t('editor.ai.scopeSelectionKind', {
      kind: t(COUNT_KEYS[parts[0].countKey as (typeof KIND_ORDER)[number][1]], {
        count: parts[0].count,
      }),
    })
  }
  return t('editor.ai.scopeSelectionMixed', {
    count: summaryTotalBlocks(summary),
  })
}

export function SelectionSummaryChip({
  summary,
}: {
  summary: SelectionSummary
}) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  const previewId = useId()
  const parts = selectionSummaryParts(summary, t)
  return (
    <div
      data-as="selection-summary"
      data-testid="selection-summary-chip"
      className="border-border bg-subtle rounded-md border"
    >
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={previewId}
        onClick={() => setExpanded((value) => !value)}
        className="text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-ring flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-[11px] focus-visible:ring-2"
      >
        <Layers className="size-3 shrink-0" aria-hidden />
        <span className="truncate">{parts.map((part) => part.label).join(' · ')}</span>
        <ChevronDown
          className={cn(
            'ml-auto size-3 shrink-0 transition-transform motion-reduce:transition-none',
            expanded && 'rotate-180'
          )}
          aria-hidden
        />
      </button>
      {expanded ? (
        <div id={previewId} className="space-y-1 px-2 pb-2">
          <pre className="border-border bg-surface text-foreground/80 max-h-32 overflow-y-auto rounded border p-1.5 font-mono text-[11px] leading-relaxed whitespace-pre-wrap">
            {summary.preview}
          </pre>
          <p className="text-muted-foreground text-[11px]">
            {t('editor.ai.summaryLines', { count: summary.lines })}
          </p>
        </div>
      ) : null}
    </div>
  )
}
