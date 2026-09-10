import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'

export interface DiffLine {
  kind: 'add' | 'del' | 'hunk' | 'meta' | 'context'
  text: string
}

export function parseUnifiedDiff(diff: string): DiffLine[] {
  if (!diff.trim()) {
    return []
  }
  return diff.split('\n').map((line) => {
    if (line.startsWith('@@')) return { kind: 'hunk', text: line }
    if (line.startsWith('+')) return { kind: 'add', text: line }
    if (line.startsWith('-')) return { kind: 'del', text: line }
    if (line.startsWith('+++') || line.startsWith('---'))
      return { kind: 'meta', text: line }
    return { kind: 'context', text: line }
  })
}

const LINE_TONES: Record<DiffLine['kind'], string> = {
  add: 'bg-success/10 text-success',
  del: 'bg-danger/10 text-danger',
  hunk: 'text-primary bg-primary/5',
  meta: 'text-muted-foreground',
  context: 'text-foreground/80',
}

export function DiffView({
  diff,
  className,
}: {
  diff: string
  className?: string
}) {
  const { t } = useTranslation()
  const lines = useMemo(() => parseUnifiedDiff(diff), [diff])
  if (lines.length === 0) {
    return (
      <p className={cn('text-muted-foreground p-3 text-xs', className)}>
        {t('diff.noChanges')}
      </p>
    )
  }
  return (
    <div
      className={cn(
        'bg-subtle border-border overflow-x-auto rounded-md border font-mono text-xs leading-relaxed',
        className
      )}
      data-testid="diff-view"
    >
      {lines.map((line, index) => (
        <pre
          key={index}
          className={cn(
            'whitespace-pre-wrap px-3 py-0.5',
            LINE_TONES[line.kind]
          )}
        >
          {line.text || ' '}
        </pre>
      ))}
    </div>
  )
}
