import { useNavigate } from '@tanstack/react-router'

import { useCurrentOrigin } from '@/lib/origin'
import {
  AlertTriangle,
  BookOpen,
  ClipboardList,
  Dumbbell,
  Layers,
  ListChecks,
  Network,
  ScrollText,
  Sigma,
  StickyNote,
  type LucideIcon,
} from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  Modal,
  ModalContent,
  ModalDescription,
  ModalHeader,
  ModalTitle,
} from '@neuronection/assistant-ui'
import type { ComposeKind } from '@/lib/api'
import { GenerateDialog } from './GenerateDialog'
import { NoteComposeDialog } from './NoteComposeDialog'
import { useCloseFloatings } from '@/lib/ui-overlays'

type LauncherAction =
  | { type: 'quiz' }
  | { type: 'exercise' }
  | { type: 'flashcards' }
  | { type: 'compose'; kind: ComposeKind }
  | { type: 'note' }

export function StudyLauncherDialog({
  courseId,
  nodeId,
  rootNodeId,
  onClose,
  onNoteCreated,
}: {
  courseId: number
  nodeId: number
  rootNodeId: number
  onClose: () => void
  onNoteCreated: (noteId: number) => void
}) {
  useCloseFloatings()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const from = useCurrentOrigin()
  const [action, setAction] = useState<LauncherAction | null>(null)

  if (action !== null) {
    if (action.type === 'note') {
      return (
        <NoteComposeDialog
          courseId={courseId}
          nodeId={nodeId}
          rootNodeId={rootNodeId}
          onClose={onClose}
          onSuccess={onNoteCreated}
        />
      )
    }
    if (action.type === 'compose') {
      return (
        <GenerateDialog
          task="compose"
          courseId={courseId}
          scopeNodeId={nodeId}
          rootNodeId={rootNodeId}
          initial={{ composeKind: action.kind }}
          onClose={onClose}
          onSuccess={onClose}
        />
      )
    }
    return (
      <GenerateDialog
        task={action.type}
        courseId={courseId}
        scopeNodeId={nodeId}
        rootNodeId={rootNodeId}
        onClose={onClose}
        onSuccess={(result) => {
          if ('id' in result && 'question_count' in result) {
            void navigate({
              to: '/quiz/$activityId',
              params: { activityId: String(result.id) },
              search: { from },
            })
          } else {
            onClose()
          }
        }}
      />
    )
  }

  const actions: { action: LauncherAction; icon: LucideIcon; label: string }[] = [
    { action: { type: 'quiz' }, icon: ListChecks, label: t('launcher.quiz') },
    { action: { type: 'exercise' }, icon: Dumbbell, label: t('launcher.exercise') },
    { action: { type: 'flashcards' }, icon: Layers, label: t('launcher.flashcards') },
    { action: { type: 'compose', kind: 'study_guide' }, icon: BookOpen, label: t('launcher.studyGuide') },
    { action: { type: 'compose', kind: 'summary_sheet' }, icon: ScrollText, label: t('launcher.summarySheet') },
    { action: { type: 'compose', kind: 'practice_set' }, icon: ClipboardList, label: t('launcher.practiceSet') },
    { action: { type: 'compose', kind: 'error_recap' }, icon: AlertTriangle, label: t('launcher.errorRecap') },
    { action: { type: 'compose', kind: 'mindmap' }, icon: Network, label: t('launcher.mindmap') },
    ...(nodeId === rootNodeId
      ? [
          {
            action: { type: 'compose', kind: 'formula_sheet' } as LauncherAction,
            icon: Sigma,
            label: t('launcher.formulaSheet'),
          },
        ]
      : []),
    { action: { type: 'note' }, icon: StickyNote, label: t('launcher.note') },
  ]

  return (
    <Modal open onOpenChange={(next) => !next && onClose()}>
      <ModalContent size="lg" closeLabel={t('common.close')} aria-describedby="launcher-hint">
        <ModalHeader>
          <ModalTitle className="text-base">{t('launcher.title')}</ModalTitle>
          <ModalDescription id="launcher-hint">{t('launcher.hint')}</ModalDescription>
        </ModalHeader>
        <div className="grid grid-cols-2 gap-2 px-6 pb-6">
          {actions.map(({ action: item, icon: Icon, label }) => (
            <button
              key={JSON.stringify(item)}
              type="button"
              className="bg-surface hover:bg-subtle border-border flex items-center gap-2 rounded-lg border px-3 py-2.5 text-left text-sm"
              onClick={() => setAction(item)}
            >
              <Icon className="text-muted-foreground size-4 shrink-0" aria-hidden />
              <span className="truncate">{label}</span>
            </button>
          ))}
        </div>
      </ModalContent>
    </Modal>
  )
}
