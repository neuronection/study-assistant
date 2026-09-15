import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Printer } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { PrintDoc, useAutoPrint } from '@/components/print/PrintDoc'
import { BlockRenderer } from '@/components/blocks/BlockRenderer'
import type { Block } from '@/components/blocks/types'
import { Button } from '@/components/ui/button'
import { dueFlashcards } from '@/lib/api'

export function FlashcardPrintSheet({
  courseId,
  nodeId,
  autoPrint = true,
  onBack,
}: {
  courseId?: number
  nodeId?: number
  autoPrint?: boolean
  onBack?: () => void
}) {
  const { t } = useTranslation()
  const due = useQuery({
    queryKey: ['cards-due', courseId ?? null, nodeId ?? null],
    queryFn: () => dueFlashcards(20, courseId, nodeId),
  })
  useAutoPrint(autoPrint)

  return (
    <PrintDoc
      title={t('print.flashcardSheet', { count: (due.data ?? []).length })}
      contextLine={t('print.generatedBy')}
      toolbar={
        <div className="flex gap-2">
          {onBack ? (
            <Button variant="outline" size="sm" onClick={onBack}>
              <ArrowLeft aria-hidden />
              {t('common.back')}
            </Button>
          ) : null}
          <Button variant="outline" size="sm" onClick={() => window.print()}>
            <Printer aria-hidden />
            {t('library.printDoc')}
          </Button>
        </div>
      }
    >
      <div className="print-cut-grid">
        {(due.data ?? []).map((card) => (
          <div key={card.id} className="print-cut-card">
            <BlockRenderer blocks={card.front as Block[]} actions={false} />
            <div className="print-cut-divider" aria-hidden />
            <BlockRenderer blocks={card.back as Block[]} actions={false} />
          </div>
        ))}
      </div>
    </PrintDoc>
  )
}
