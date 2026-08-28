import {
  BookOpen,
  Dumbbell,
  FilePlus2,
  GitBranchPlus,
  Layers,
  ListChecks,
  MessageSquare,
  Pencil,
  Sparkles,
  StickyNote,
  Trash2,
  Wand2,
} from 'lucide-react'
import type { TFunction } from 'i18next'

import type {
  EntityActionGroup,
  EntityActionHandlers,
  NodeSource,
} from './types'

export function buildEntityActions<T>(
  source: NodeSource<T>,
  node: T,
  handlers: EntityActionHandlers,
  t: TFunction
): EntityActionGroup[] {
  const entity = source.toEntity(node)
  const context = source.toContext(node)
  const hint = source.llmHint ? source.llmHint(node) : null

  const groups: EntityActionGroup[] = [
    {
      label: t('entityMenu.generate'),
      actions: [
        {
          key: 'ask',
          icon: MessageSquare,
          label: t('entityMenu.ask'),
          onSelect: () => handlers.ask(entity, context, hint),
        },
        {
          key: 'quiz',
          icon: ListChecks,
          label: t('entityMenu.quiz'),
          onSelect: () => handlers.generate('quiz', entity, context, hint),
        },
        {
          key: 'exercise',
          icon: Dumbbell,
          label: t('entityMenu.exercise'),
          onSelect: () => handlers.generate('exercise', entity, context, hint),
        },
        {
          key: 'flashcards',
          icon: Layers,
          label: t('entityMenu.flashcards'),
          onSelect: () => handlers.generate('flashcards', entity, context, hint),
        },
        {
          key: 'studyGuide',
          icon: BookOpen,
          label: t('entityMenu.studyGuide'),
          onSelect: () => handlers.generate('study_guide', entity, context, hint),
        },
        {
          key: 'writeNote',
          icon: Sparkles,
          label: t('entityMenu.writeNote'),
          onSelect: () => handlers.writeNote(entity, context, hint),
        },
        ...(source.canAiEdit && handlers.aiEdit
          ? [
              {
                key: 'aiEdit',
                icon: Wand2,
                label: t('entityMenu.aiEdit'),
                onSelect: () => handlers.aiEdit?.(entity, context),
              },
            ]
          : []),
      ],
    },
    {
      label: t('entityMenu.integrate'),
      actions: [
        {
          key: 'addNote',
          icon: StickyNote,
          label: t('entityMenu.addNote'),
          onSelect: () => handlers.addNote(entity, context),
        },
        ...(handlers.addAsSection
          ? [
              {
                key: 'addAsSection',
                icon: FilePlus2,
                label: t('entityMenu.addAsSection'),
                onSelect: () => handlers.addAsSection?.(entity, context),
              },
            ]
          : []),
      ],
    },
  ]

  const editActions: EntityActionGroup['actions'] = []
  if (source.canAddChild && source.addChild && handlers.addChild) {
    editActions.push({
      key: 'addChild',
      icon: GitBranchPlus,
      label: t('entityMenu.addChild'),
      onSelect: () => handlers.addChild?.(),
    })
  }
  if (source.canEdit && source.edit && handlers.editNode) {
    editActions.push({
      key: 'edit',
      icon: Pencil,
      label: t('entityMenu.edit'),
      onSelect: () => handlers.editNode?.(),
    })
  }
  if (source.canRemove && source.remove && handlers.removeNode) {
    editActions.push({
      key: 'remove',
      icon: Trash2,
      label: t('entityMenu.remove'),
      danger: true,
      onSelect: () => handlers.removeNode?.(),
    })
  }
  if (editActions.length > 0) {
    groups.push({ label: t('entityMenu.edit'), actions: editActions })
  }

  return groups
}
