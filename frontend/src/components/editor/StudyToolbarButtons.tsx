import type { Editor } from '@tiptap/react'
import { Camera, PenTool, Sigma, Workflow } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { DictationButton, type DictationStatus } from '@/components/ui/dictation'
import type { SelectionRange } from '@/components/editor/insertMarkdown'
import { AiHelperPopover, type AiHelperContext } from '@/features/ai/AiHelperPopover'

const MERMAID_STARTER = 'flowchart TD\n  A --> B'

export interface StudyToolbarButtonsProps {
  editor: Editor | null
  hasCanvas: boolean
  onOpenCanvas: () => void
  onSnapRegion?: () => void
  aiHelper?: AiHelperContext
  aiSelectionRef: { current: SelectionRange | null }
  aiCloseSignal: number
  onAiInsert: () => void
  dictationStatus: DictationStatus
  onDictationStart: () => void
}

function AppToolbarButton({
  label,
  onClick,
  children,
}: {
  label: string
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      className="text-[var(--as-muted-fg)] hover:text-[var(--as-fg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--as-focus-ring)] rounded p-1.5 transition-colors"
      onClick={onClick}
    >
      {children}
    </button>
  )
}

export function StudyToolbarButtons({
  editor,
  hasCanvas,
  onOpenCanvas,
  onSnapRegion,
  aiHelper,
  aiSelectionRef,
  aiCloseSignal,
  onAiInsert,
  dictationStatus,
  onDictationStart,
}: StudyToolbarButtonsProps) {
  const { t } = useTranslation()
  return (
    <>
      <AppToolbarButton
        label={t('editor.insertMath')}
        onClick={() =>
          editor
            ?.chain()
            .focus()
            .insertContent({
              type: 'caMath',
              attrs: { latex: 'x', display: false, autofocus: true },
            })
            .run()
        }
      >
        <Sigma className="size-4" aria-hidden />
      </AppToolbarButton>
      <AppToolbarButton
        label={t('editor.insertMermaid')}
        onClick={() =>
          editor
            ?.chain()
            .focus()
            .insertContent({
              type: 'caMermaid',
              attrs: { source: MERMAID_STARTER, autofocus: true },
            })
            .run()
        }
      >
        <Workflow className="size-4" aria-hidden />
      </AppToolbarButton>
      {hasCanvas ? (
        <AppToolbarButton label={t('editor.insertDrawing')} onClick={onOpenCanvas}>
          <PenTool className="size-4" aria-hidden />
        </AppToolbarButton>
      ) : null}
      {onSnapRegion ? (
        <AppToolbarButton label={t('editor.snapRegion')} onClick={onSnapRegion}>
          <Camera className="size-4" aria-hidden />
        </AppToolbarButton>
      ) : null}
      {aiHelper ? (
        <AiHelperPopover
          editor={editor}
          context={aiHelper}
          selectionRef={aiSelectionRef}
          closeSignal={aiCloseSignal}
          onInsert={onAiInsert}
        />
      ) : null}
      <DictationButton
        status={dictationStatus}
        onStart={onDictationStart}
        label={t('dictation.start')}
      />
    </>
  )
}
