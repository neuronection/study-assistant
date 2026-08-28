import { Loader2 } from 'lucide-react'
import { lazy, Suspense } from 'react'
import { useTranslation } from 'react-i18next'

import type { AiHelperContext } from '@/features/ai/AiHelperPopover'

import type { DrawingAdapter, DrawingMeta } from './MarkdownEditor'

const MarkdownEditor = lazy(() =>
  import('./MarkdownEditor').then((module) => ({ default: module.MarkdownEditor }))
)

export function LazyMarkdownEditor({
  value,
  onChange,
  ariaLabel,
  drawings,
  drawingAdapter,
  aiHelper,
}: {
  value: string
  onChange: (markdown: string) => void
  ariaLabel: string
  drawings?: DrawingMeta[]
  drawingAdapter?: DrawingAdapter
  aiHelper?: AiHelperContext
}) {
  const { t } = useTranslation()
  return (
    <Suspense fallback={<Loader2 className="animate-spin" aria-label={t('library.loading')} />}>
      <MarkdownEditor
        value={value}
        onChange={onChange}
        ariaLabel={ariaLabel}
        drawings={drawings}
        drawingAdapter={drawingAdapter}
        aiHelper={aiHelper}
      />
    </Suspense>
  )
}