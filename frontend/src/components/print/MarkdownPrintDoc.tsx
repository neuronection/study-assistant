import { ArrowLeft, Printer } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { MarkdownSurface } from '@/components/ui/chat-markdown'
import { Button } from '@/components/ui/button'
import { PrintDoc, useAutoPrint } from '@/components/print/PrintDoc'
import { normalizeMathFences } from '@/components/editor/markdownFidelity'

export function MarkdownPrintDoc({
  title,
  contextLine,
  markdown,
  autoPrint = true,
  onBack,
}: {
  title: string
  contextLine?: string
  markdown: string
  autoPrint?: boolean
  onBack?: () => void
}) {
  useAutoPrint(autoPrint)
  const { t } = useTranslation()
  return (
    <PrintDoc
      title={title}
      contextLine={contextLine ?? t('print.generatedBy')}
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
      <MarkdownSurface value={normalizeMathFences(markdown)} />
    </PrintDoc>
  )
}
