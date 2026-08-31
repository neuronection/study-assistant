import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from '@tanstack/react-router'
import { ClipboardList, Dumbbell, FileUp, Layers, Sparkles, Download, Upload } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { EntityItems, type EntityItemEntry } from '@/components/entity-list/EntityItems'
import { EmptyState } from '@/components/ui/empty-state'
import { TabActionBar } from '@/components/layout/TabActionBar'
import { Button } from '@/components/ui/button'
import { type ContextMenuItem } from '@/components/ui/ContextMenu'
import { ErrorBanner } from '@/components/ErrorBanner'
import { RenameDialog } from '@/components/RenameDialog'
import { SelectionBar } from '@/components/ui/SelectionBar'
import { UndoDeleteNotice } from '@/components/UndoDeleteNotice'
import { ViewToggle } from '@/components/ui/ViewToggle'
import { useStoredView } from '@/lib/useStoredView'
import { GenerateDialog as AIGenerateDialog } from '@/features/ai/GenerateDialog'
import { DrillsCard } from '@/features/exercises/DrillsCard'
import { AssignToNodeDialog } from '@/features/courses/AssignToNodeDialog'
import { ImportDialog } from '@/features/quiz/ImportDialog'
import { ReviewQueue } from '@/features/flashcards/ReviewQueue'
import { useCurrentOrigin } from '@/lib/origin'
import { useSelection } from '@/lib/useSelection'
import { useConfirm } from '@/lib/use-confirm'
import {
  ankiExportUrl,
  deleteExercise,
  deleteQuiz,
  importAnkiDeck,
  listExercises,
  listFlashcards,
  listQuizzes,
  moveExercise,
  moveQuiz,
  qpkgExportUrl,
  quizExportUrl,
  renameExercise,
  renameQuiz,
  similarExercise,
  type QuizActivity,
} from '@/lib/api'

import { cn } from '@/lib/utils'
import { storageKeys } from '@/lib/constants'

function ScopeChip({
  nodeId,
  courseId,
  titles,
}: {
  nodeId: number | null
  courseId: string
  titles: Map<number, string>
}) {
  const { t } = useTranslation()
  if (nodeId === null) {
    return null
  }
  const label = titles.get(nodeId)
  return (
    <Link
      to="/courses/$courseId/n/$nodeId"
      params={{ courseId, nodeId: String(nodeId) }}
      className="bg-subtle text-muted-foreground hover:text-foreground shrink-0 rounded-full px-2 py-0.5 text-[10px] hover:underline"
      title={label ?? undefined}
    >
      {label ?? t('workspace.otherNode')}
    </Link>
  )
}

function scopeLabel(nodeId: number | null, titles: Map<number, string>): string {
  if (nodeId === null) {
    return ''
  }
  return titles.get(nodeId) ?? ''
}

type PracticeRow = EntityItemEntry & {
  kind: 'quiz' | 'exercise'
  quizId?: number
  exerciseId?: number
}

export type PracticeSegment = 'sets' | 'flashcards'

export function PracticeTab({
  courseId,
  currentId,
  rootId,
  titles,
  initialSegment = 'sets',
}: {
  courseId: string
  currentId: number
  rootId: number
  titles: Map<number, string>
  initialSegment?: PracticeSegment
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const from = useCurrentOrigin()
  const [segment, setSegment] = useState<PracticeSegment>(initialSegment)
  const [showPractice, setShowPractice] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [similarError, setSimilarError] = useState<string | null>(null)
  const [view, setView] = useStoredView(storageKeys.practiceView, 'list')
  const [undoItem, setUndoItem] = useState<number | null>(null)
  const [moveTarget, setMoveTarget] = useState(false)
  const [renaming, setRenaming] = useState<
    { kind: 'quiz' | 'exercise'; id: number; title: string } | null
  >(null)
  const [showCardsGenerate, setShowCardsGenerate] = useState(false)
  const [importMessage, setImportMessage] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const [confirm, confirmElement] = useConfirm()

  const quizzes = useQuery({
    queryKey: ['quizzes', 'node', currentId],
    queryFn: () => listQuizzes(undefined, currentId),
  })
  const exercises = useQuery({
    queryKey: ['exercises', 'node', currentId],
    queryFn: () => listExercises(undefined, currentId),
  })
  const flashcards = useQuery({
    queryKey: ['cards', 'node', currentId],
    queryFn: () => listFlashcards(undefined, currentId),
  })

  const importAnki = useMutation({
    mutationFn: (file: File) => importAnkiDeck(file, Number(courseId)),
    onSuccess: async (result) => {
      setImportMessage(t('cards.ankiImported', { count: result.imported }))
      await queryClient.invalidateQueries({ queryKey: ['cards'] })
      await queryClient.invalidateQueries({ queryKey: ['cards-due'] })
    },
    onError: (err: Error) => setImportMessage(err.message),
  })

  const similar = useMutation({
    mutationFn: (exerciseId: number) => similarExercise(exerciseId),
    onSuccess: async () => {
      setSimilarError(null)
      await queryClient.invalidateQueries({ queryKey: ['exercises'] })
    },
    onError: (err: Error) => setSimilarError(err.message),
  })
  const renameQuizMutation = useMutation({
    mutationFn: ({ id, title }: { id: number; title: string }) => renameQuiz(id, title),
    onSuccess: async () => {
      setRenaming(null)
      await queryClient.invalidateQueries({ queryKey: ['quizzes'] })
      await queryClient.invalidateQueries({ queryKey: ['tree'] })
    },
  })
  const deleteQuizMutation = useMutation({
    mutationFn: (quizId: number) => deleteQuiz(quizId),
    onSuccess: async (result) => {
      setUndoItem(result.deleted_item_id)
      await queryClient.invalidateQueries({ queryKey: ['quizzes'] })
      await queryClient.invalidateQueries({ queryKey: ['tree'] })
    },
  })
  const renameExerciseMutation = useMutation({
    mutationFn: ({ id, title }: { id: number; title: string }) =>
      renameExercise(id, title),
    onSuccess: async () => {
      setRenaming(null)
      await queryClient.invalidateQueries({ queryKey: ['exercises'] })
      await queryClient.invalidateQueries({ queryKey: ['tree'] })
    },
  })
  const deleteExerciseMutation = useMutation({
    mutationFn: (exerciseId: number) => deleteExercise(exerciseId),
    onSuccess: async (result) => {
      setUndoItem(result.deleted_item_id)
      await queryClient.invalidateQueries({ queryKey: ['exercises'] })
      await queryClient.invalidateQueries({ queryKey: ['tree'] })
    },
  })
  const moveQuizzes = useMutation({
    mutationFn: async ({
      nodeId,
      quizIds,
    }: {
      nodeId: number
      quizIds: number[]
    }) => {
      for (const quizId of quizIds) {
        await moveQuiz(quizId, nodeId)
      }
    },
    onSuccess: async () => {
      setMoveTarget(false)
      await queryClient.invalidateQueries({ queryKey: ['quizzes'] })
      await queryClient.invalidateQueries({ queryKey: ['tree'] })
    },
  })
  const moveExercises = useMutation({
    mutationFn: async ({
      nodeId,
      exerciseIds,
    }: {
      nodeId: number
      exerciseIds: number[]
    }) => {
      for (const exerciseId of exerciseIds) {
        await moveExercise(exerciseId, nodeId)
      }
    },
    onSuccess: async () => {
      setMoveTarget(false)
      await queryClient.invalidateQueries({ queryKey: ['exercises'] })
      await queryClient.invalidateQueries({ queryKey: ['tree'] })
    },
  })

  const combinedOrder = useMemo(
    () => [
      ...(quizzes.data ?? []).map((quiz) => `quiz-${quiz.id}`),
      ...(exercises.data ?? []).map((exercise) => `exercise-${exercise.id}`),
    ],
    [quizzes.data, exercises.data]
  )
  const selection = useSelection(combinedOrder)
  const selectedQuizIds = useMemo(
    () =>
      [...selection.selected]
        .filter((key) => key.startsWith('quiz-'))
        .map((key) => Number(key.slice(5))),
    [selection.selected]
  )
  const selectedExerciseIds = useMemo(
    () =>
      [...selection.selected]
        .filter((key) => key.startsWith('exercise-'))
        .map((key) => Number(key.slice(9))),
    [selection.selected]
  )

  const deleteSelected = async () => {
    const total = selectedQuizIds.length + selectedExerciseIds.length
    if (total === 0) {
      return
    }
    const message =
      selectedQuizIds.length > 0 && selectedExerciseIds.length > 0
        ? t('practice.confirmDeleteMixed', {
            quizzes: selectedQuizIds.length,
            exercises: selectedExerciseIds.length,
          })
        : selectedQuizIds.length > 0
          ? t('quiz.confirmDeleteSelection', { count: selectedQuizIds.length })
          : t('exercises.confirmDeleteSelection', { count: selectedExerciseIds.length })
    const ok = await confirm({
      title: t('workspace.deleteSelection'),
      description: message,
      confirmLabel: t('workspace.deleteSelection'),
      cancelLabel: t('common.cancel'),
      destructive: true,
    })
    if (!ok) {
      return
    }
    for (const quizId of selectedQuizIds) {
      deleteQuizMutation.mutate(quizId)
    }
    for (const exerciseId of selectedExerciseIds) {
      deleteExerciseMutation.mutate(exerciseId)
    }
    selection.clear()
  }

  const onMoveDone = (nodeId: number) => {
    if (selectedQuizIds.length > 0) {
      void moveQuizzes.mutateAsync({ nodeId, quizIds: selectedQuizIds })
    }
    if (selectedExerciseIds.length > 0) {
      void moveExercises.mutateAsync({ nodeId, exerciseIds: selectedExerciseIds })
    }
  }

  const items: PracticeRow[] = [
    ...(quizzes.data ?? []).map(
      (quiz): PracticeRow => ({
        key: `quiz-${quiz.id}`,
        kind: 'quiz',
        quizId: quiz.id,
        title: quiz.title,
        icon: ClipboardList,
        meta: t('quiz.questionCount', { count: quiz.question_count }),
        onClick: () =>
          void navigate({
            to: '/quiz/$activityId',
            params: { activityId: String(quiz.id) },
            search: { from },
          }),
        trailing: <ScopeChip nodeId={quiz.node_id} courseId={courseId} titles={titles} />,
        infoTitle: quiz.title,
        info: (
          <span className="flex flex-col gap-1">
            <span>{t('quiz.questionCount', { count: quiz.question_count })}</span>
            <span>
              {t('practice.scopeInfo', {
                scope: scopeLabel(quiz.node_id, titles),
              })}
            </span>
          </span>
        ),
      })
    ),
    ...(exercises.data ?? []).map(
      (exercise): PracticeRow => ({
        key: `exercise-${exercise.id}`,
        kind: 'exercise',
        exerciseId: exercise.id,
        title: exercise.title,
        icon: Dumbbell,
        meta: t('exercises.stepCount', { count: exercise.step_count }),
        onClick: () =>
          void navigate({
            to: '/exercises/$exerciseId',
            params: { exerciseId: String(exercise.id) },
            search: { from },
          }),
        trailing: (
          <>
            {exercise.difficulty !== null ? (
              <span className="bg-subtle text-muted-foreground shrink-0 rounded-full px-2 py-0.5 text-[11px]">
                {t('exercises.difficultyOption', { level: exercise.difficulty })}
              </span>
            ) : null}
            <ScopeChip nodeId={exercise.node_id} courseId={courseId} titles={titles} />
          </>
        ),
        infoTitle: exercise.title,
        info: (
          <span className="flex flex-col gap-1">
            <span>{t('exercises.stepCount', { count: exercise.step_count })}</span>
            <span>
              {t('practice.scopeInfo', {
                scope: scopeLabel(exercise.node_id, titles),
              })}
            </span>
          </span>
        ),
      })
    ),
  ]

  const menu = (item: PracticeRow): ContextMenuItem[] => {
    if (item.kind === 'quiz' && item.quizId !== undefined) {
      const quizId = item.quizId
      return [
        {
          key: 'open',
          label: t('common.open'),
          onSelect: () =>
            void navigate({
              to: '/quiz/$activityId',
              params: { activityId: String(quizId) },
              search: { from },
            }),
        },
        {
          key: 'export',
          label: t('quiz.export'),
          onSelect: () => window.open(quizExportUrl(quizId), '_blank'),
        },
        {
          key: 'qpkg',
          label: t('quiz.qpkg'),
          onSelect: () => window.open(qpkgExportUrl(quizId), '_blank'),
        },
        {
          key: 'print',
          label: t('quiz.print'),
          onSelect: () => {
            void navigate({
              to: '/quiz/$activityId',
              params: { activityId: String(quizId) },
              search: { from },
            }).then(() => window.setTimeout(() => window.print(), 400))
          },
        },
        {
          key: 'rename',
          label: t('common.rename'),
          onSelect: () => {
            const quiz = (quizzes.data ?? []).find((entry) => entry.id === quizId)
            setRenaming({ kind: 'quiz', id: quizId, title: quiz?.title ?? '' })
          },
        },
        {
          key: 'delete',
          label: t('quiz.delete'),
          danger: true,
          onSelect: async () => {
            const quiz = (quizzes.data ?? []).find((entry) => entry.id === quizId)
            const ok = await confirm({
              title: t('quiz.delete'),
              description: t('quiz.confirmDelete', { title: quiz?.title ?? '' }),
              confirmLabel: t('quiz.delete'),
              cancelLabel: t('common.cancel'),
              destructive: true,
            })
            if (ok) deleteQuizMutation.mutate(quizId)
          },
        },
      ]
    }
    if (item.exerciseId !== undefined) {
      const exerciseId = item.exerciseId
      return [
        {
          key: 'open',
          label: t('common.open'),
          onSelect: () =>
            void navigate({
              to: '/exercises/$exerciseId',
              params: { exerciseId: String(exerciseId) },
              search: { from },
            }),
        },
        {
          key: 'similar',
          label: t('exercises.similar'),
          onSelect: () => similar.mutate(exerciseId),
        },
        {
          key: 'rename',
          label: t('common.rename'),
          onSelect: () => {
            const exercise = (exercises.data ?? []).find(
              (entry) => entry.id === exerciseId
            )
            setRenaming({
              kind: 'exercise',
              id: exerciseId,
              title: exercise?.title ?? '',
            })
          },
        },
        {
          key: 'delete',
          label: t('exercises.delete'),
          danger: true,
          onSelect: async () => {
            const exercise = (exercises.data ?? []).find(
              (entry) => entry.id === exerciseId
            )
            const ok = await confirm({
              title: t('exercises.delete'),
              description: t('exercises.confirmDelete', { title: exercise?.title ?? '' }),
              confirmLabel: t('exercises.delete'),
              cancelLabel: t('common.cancel'),
              destructive: true,
            })
            if (ok) deleteExerciseMutation.mutate(exerciseId)
          },
        },
      ]
    }
    return []
  }

  const selectedCount = selectedQuizIds.length + selectedExerciseIds.length
  const isCards = segment === 'flashcards'

  const segments: { key: PracticeSegment; label: string; icon: typeof ClipboardList }[] = [
    { key: 'sets', label: t('practice.segmentSets'), icon: Dumbbell },
    { key: 'flashcards', label: t('practice.segmentFlashcards'), icon: Layers },
  ]

  return (
    <div className="space-y-6">
      <input
        ref={fileInput}
        type="file"
        accept=".apkg"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0]
          if (file) {
            importAnki.mutate(file)
          }
          event.target.value = ''
        }}
      />
      <UndoDeleteNotice deletedItemId={undoItem} onDismiss={() => setUndoItem(null)} />
      {isCards ? (
        <TabActionBar
          actions={[
            {
              label: t('cards.generate'),
              icon: Sparkles,
              onAction: () => setShowCardsGenerate(true),
              primary: true,
            },
            {
              label: t('cards.ankiImport'),
              icon: Upload,
              onAction: () => fileInput.current?.click(),
              pending: importAnki.isPending,
            },
            {
              label: t('cards.ankiExport'),
              icon: Download,
              onAction: () => window.open(ankiExportUrl(Number(courseId)), '_blank'),
            },
          ]}
        />
      ) : (
        <TabActionBar
          actions={[
            {
              label: t('practice.new'),
              icon: Sparkles,
              onAction: () => setShowPractice(true),
              primary: true,
            },
            { label: t('quiz.import'), icon: FileUp, onAction: () => setShowImport(true) },
          ]}
        />
      )}
      <div className="-mt-4 flex w-fit items-center gap-1 rounded-lg bg-subtle p-1" role="tablist">
        {segments.map((entry) => (
          <button
            key={entry.key}
            type="button"
            role="tab"
            aria-selected={segment === entry.key}
            className={cn(
              'flex items-center gap-1.5 rounded-md px-3 py-1 text-xs transition-colors',
              segment === entry.key
                ? 'bg-surface text-foreground font-medium shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            )}
            onClick={() => setSegment(entry.key)}
          >
            <entry.icon className="size-3.5" aria-hidden />
            {entry.label}
          </button>
        ))}
      </div>

      {isCards ? (
        <div className="space-y-2">
          {importMessage ? (
            <p className="text-muted-foreground px-1 text-xs">{importMessage}</p>
          ) : null}
          <ReviewQueue nodeId={currentId} />
          {(flashcards.data ?? []).map((card) => (
            <div
              key={card.id}
              className="border-border flex items-center gap-3 rounded-lg border px-4 py-3 text-sm"
            >
              <Layers className="text-muted-foreground size-4 shrink-0" aria-hidden />
              <span className="min-w-0 flex-1 truncate">
                {card.front.map((block) => block.md ?? '').join(' ')}
              </span>
              <ScopeChip nodeId={card.node_id} courseId={courseId} titles={titles} />
              <span className="text-muted-foreground shrink-0 text-[11px]">
                {t(`cards.kind.${card.kind}`)}
              </span>
              <span className="text-muted-foreground shrink-0 text-[11px]">
                {card.due_at
                  ? t('cards.dueWhen', { when: card.due_at.slice(0, 10) })
                  : t('cards.state.new')}
              </span>
            </div>
          ))}
          {flashcards.data && flashcards.data.length === 0 ? (
            <p className="text-muted-foreground py-4 text-center text-sm">{t('cards.queueEmpty')}</p>
          ) : null}
        </div>
      ) : (
        <>
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <h2 className="flex items-center gap-2 text-sm font-semibold">
                <ClipboardList className="size-4" aria-hidden />
                {t('practice.title')}
              </h2>
              <ViewToggle view={view} onChange={setView} />
            </div>
            {quizzes.data && exercises.data && items.length === 0 ? (
              <EmptyState title={t('practice.emptyList')} />
            ) : (
              <EntityItems
                items={items}
                layout={view}
                menuItems={menu}
                selection={{
                  isSelected: (key) => selection.selected.has(key),
                  onPointerDown: (key, event) => selection.pointerDown(key, event),
                }}
              />
            )}
            <SelectionBar
            count={selection.selected.size}
            countLabel={t('selection.count', { count: selection.selected.size })}
            onClear={() => selection.clear()}
          >
              <Button
                variant="outline"
                size="sm"
                disabled={moveQuizzes.isPending || moveExercises.isPending}
                onClick={() => setMoveTarget(true)}
              >
                {t('workspace.moveToNode')}
              </Button>
              <Button variant="outline" size="sm" onClick={deleteSelected}>
                {t('workspace.deleteSelection')}
              </Button>
            </SelectionBar>
            <ErrorBanner message={similarError} />
          </div>

          <DrillsCard courseId={Number(courseId)} />
        </>
      )}

      {moveTarget ? (
        <AssignToNodeDialog
          courseId={Number(courseId)}
          title={t('workspace.moveToNode')}
          countText={t('moveToNode.count', { count: selectedCount })}
          confirmLabel={t('moveToNode.confirm')}
          onDone={onMoveDone}
          onClose={() => setMoveTarget(false)}
        />
      ) : null}

      {renaming !== null ? (
        <RenameDialog
          title={
            renaming.kind === 'quiz' ? t('quiz.renameTitle') : t('exercises.renameTitle')
          }
          initialName={renaming.title}
          onClose={() => setRenaming(null)}
          onConfirm={(title) => {
            if (renaming.kind === 'quiz') {
              renameQuizMutation.mutate({ id: renaming.id, title })
            } else {
              renameExerciseMutation.mutate({ id: renaming.id, title })
            }
          }}
        />
      ) : null}

      {showPractice ? (
        <AIGenerateDialog
          task="practice"
          courseId={Number(courseId)}
          scopeNodeId={currentId}
          rootNodeId={rootId}
          onClose={() => setShowPractice(false)}
          onSuccess={(result) => {
            setShowPractice(false)
            const firstQuiz = (Array.isArray(result) ? result : [result]).find(
              (item): item is QuizActivity => 'id' in item && 'question_count' in item
            )
            if (firstQuiz) {
              void navigate({
                to: '/quiz/$activityId',
                params: { activityId: String(firstQuiz.id) },
                search: { from },
              })
            }
          }}
        />
      ) : null}
      {showImport ? (
        <ImportDialog courseId={Number(courseId)} onClose={() => setShowImport(false)} />
      ) : null}
      {showCardsGenerate ? (
        <AIGenerateDialog
          task="flashcards"
          courseId={Number(courseId)}
          scopeNodeId={currentId}
          rootNodeId={rootId}
          onClose={() => setShowCardsGenerate(false)}
          onSuccess={() => setShowCardsGenerate(false)}
        />
      ) : null}
      {confirmElement}
    </div>
  )
}