import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BookOpen, Loader2, Minus, Plus, Sparkles, StickyNote, Tag, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorBanner } from '@/components/ErrorBanner'
import { FieldLabel } from '@/components/ui/FieldLabel'
import { InfoButton } from '@/components/ui/InfoButton'
import { CourseSelectField } from '@/components/workspace/CoursePicker'
import { MaterialPickerDialog } from '@/features/courses/MaterialPickerDialog'
import { NotePickerDialog } from '@/features/notes/NotePickerDialog'
import {
  COMPOSE_KINDS,
  composeMaterial,
  conceptGraph,
  generateExercise,
  generateFlashcards,
  generateQuiz,
  getNodeArtifacts,
  listMaterials,
  listNotes,
  nodeWorkspace,
  previewAiContext,
  type ComposeKind,
  type ExerciseInfo,
  type FlashcardInfo,
  type GenerateScope,
  type Material,
  type QuizActivity,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { useCloseFloatings } from '@/lib/ui-overlays'

export type GenerateTask = 'quiz' | 'exercise' | 'flashcards' | 'compose' | 'practice'

const EXERCISE_KINDS = [
  'multi_step',
  'matching',
  'ordering',
  'categorize',
  'fill_blank',
  'explain',
  'error_spot',
  'correct_solution',
] as const

const QUIZ_TYPES = [
  'single',
  'multi',
  'truefalse',
  'text',
  'numeric',
  'equation',
  'numberline',
  'table_fill',
] as const

type ExerciseKind = (typeof EXERCISE_KINDS)[number]
type QuizType = (typeof QUIZ_TYPES)[number]

type PracticeItem = QuizActivity | ExerciseInfo

type GenerateResult = QuizActivity | ExerciseInfo | FlashcardInfo[] | Material | PracticeItem[]

interface MaterialOption {
  id: number
  title: string
  inScope: boolean
}

export function GenerateDialog({
  task,
  courseId,
  scopeNodeId,
  rootNodeId,
  initial,
  onClose,
  onSuccess,
}: {
  task: GenerateTask
  courseId: number | null
  scopeNodeId?: number
  rootNodeId?: number
  initial?: {
    topic?: string | null
    count?: number | null
    stepCount?: number | null
    difficulty?: number | null
    composeKind?: ComposeKind
    exerciseKind?: ExerciseKind
    hint?: string | null
  }
  onClose: () => void
  onSuccess: (result: GenerateResult) => void
}) {
  useCloseFloatings()
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const atRoot = scopeNodeId === undefined || scopeNodeId === rootNodeId
  const [scope, setScope] = useState<GenerateScope>(atRoot ? 'course' : 'subtree')
  const [topic, setTopic] = useState(initial?.topic ?? '')
  const [composeKind, setComposeKind] = useState<ComposeKind>(
    initial?.composeKind ?? 'study_guide'
  )
  const [instructions, setInstructions] = useState('')
  const [count, setCount] = useState(initial?.count ?? 8)
  const [difficulty, setDifficulty] = useState(initial?.difficulty ?? 0)
  const [stepCount, setStepCount] = useState(initial?.stepCount ?? 4)
  const [exerciseKind, setExerciseKind] = useState<ExerciseKind>(
    initial?.exerciseKind ?? 'multi_step'
  )
  const [quizTypes, setQuizTypes] = useState<QuizType[]>(() =>
    task === 'practice' ? [...QUIZ_TYPES] : []
  )
  const [exerciseKinds, setExerciseKinds] = useState<ExerciseKind[]>(() =>
    task === 'practice' && initial?.exerciseKind ? [initial.exerciseKind] : []
  )
  const [shuffle, setShuffle] = useState(false)
  const [source, setSource] = useState<'mistakes' | 'note' | 'material'>('mistakes')
  const [sourceNoteId, setSourceNoteId] = useState<number | null>(null)
  const [sourceMaterialId, setSourceMaterialId] = useState<number | null>(null)
  const [pickedCourse, setPickedCourse] = useState<number | null>(null)
  const [hint, setHint] = useState(initial?.hint ?? '')
  const [excluded, setExcluded] = useState<number[]>([])
  const [extraMaterials, setExtraMaterials] = useState<number[]>([])
  const [pickerMode, setPickerMode] = useState<'add' | 'exclude' | null>(null)
  const [noteTitles, setNoteTitles] = useState<Map<number, string>>(new Map())
  const [showNotePicker, setShowNotePicker] = useState(false)
  const [conceptIds, setConceptIds] = useState<number[]>([])
  const [error, setError] = useState<string | null>(null)
  const courseIdForRequest = courseId ?? pickedCourse
  const composeHasContext = task !== 'flashcards'

  const placementNodeId =
    scope === 'course' ? (rootNodeId ?? scopeNodeId ?? null) : (scopeNodeId ?? null)
  const existingArtifact = useQuery({
    queryKey: ['node-artifact', placementNodeId, composeKind],
    queryFn: () => getNodeArtifacts(placementNodeId as number, composeKind),
    enabled: task === 'compose' && placementNodeId !== null && composeHasContext,
  })
  const existing = task === 'compose' ? (existingArtifact.data?.artifact ?? null) : null
  const showContextSections = task !== 'flashcards'

  const workspace = useQuery({
    queryKey: ['node-workspace', String(scopeNodeId)],
    queryFn: () => nodeWorkspace(scopeNodeId as number),
    enabled: showContextSections && scopeNodeId !== undefined && !atRoot,
  })
  const courseMaterials = useQuery({
    queryKey: ['materials', 'course', courseIdForRequest],
    queryFn: () => listMaterials(undefined, courseIdForRequest as number),
    enabled:
      courseIdForRequest !== null &&
      (showContextSections || source === 'material') &&
      (scope === 'course' || !atRoot || source === 'material'),
  })

  const materialOptions: MaterialOption[] = useMemo(() => {
    if (!showContextSections || courseIdForRequest === null) return []
    if (atRoot || scope === 'course') {
      return (courseMaterials.data ?? []).map((material) => ({
        id: material.id,
        title: material.title,
        inScope: true,
      }))
    }
    const direct = (workspace.data?.materials ?? []).map((entry) => entry.material_id)
    const nested = Object.values(workspace.data?.child_materials ?? {}).flatMap((rows) =>
      rows.map((entry) => entry.material_id)
    )
    const titles = new Map<number, string>()
    for (const entry of workspace.data?.materials ?? []) {
      titles.set(entry.material_id, entry.title)
    }
    for (const rows of Object.values(workspace.data?.child_materials ?? {})) {
      for (const entry of rows) {
        titles.set(entry.material_id, entry.title)
      }
    }
    const scopeIds =
      scope === 'node'
        ? direct
        : Array.from(new Set([...direct, ...nested]))
    return scopeIds.map((id) => ({
      id,
      title: titles.get(id) ?? `#${id}`,
      inScope: true,
    }))
  }, [showContextSections, courseIdForRequest, atRoot, scope, courseMaterials.data, workspace.data])

  const materialTitle = useMemo(() => {
    const titles = new Map<number, string>()
    for (const option of materialOptions) {
      titles.set(option.id, option.title)
    }
    for (const material of courseMaterials.data ?? []) {
      titles.set(material.id, material.title)
    }
    return (id: number) => titles.get(id) ?? `#${id}`
  }, [materialOptions, courseMaterials.data])

  const notes = useQuery({
    queryKey: [
      'notes',
      'generate',
      courseIdForRequest,
      scopeNodeId,
      scope === 'node' ? 'direct' : 'rolled',
    ],
    queryFn: () => {
      if (scopeNodeId !== undefined && !atRoot && scope !== 'course') {
        return listNotes(undefined, undefined, {
          node_id: scopeNodeId,
          include_children: scope !== 'node',
          limit: 50,
        })
      }
      return listNotes(undefined, courseIdForRequest as number, { limit: 50 })
    },
    enabled: courseIdForRequest !== null,
  })

  const concepts = useQuery({
    queryKey: ['concepts', 'graph', courseIdForRequest],
    queryFn: () => conceptGraph(courseIdForRequest as number),
    enabled: courseIdForRequest !== null && showContextSections,
  })

  const specBody = useMemo(
    () => ({
      node_id:
        scope === 'course'
          ? (rootNodeId ?? scopeNodeId ?? null)
          : (scopeNodeId ?? null),
      scope,
      exclude_material_ids: excluded.length > 0 ? excluded : undefined,
      include_material_ids:
        extraMaterials.length > 0 && showContextSections ? extraMaterials : undefined,
      note_ids: noteTitles.size > 0 ? [...noteTitles.keys()] : undefined,
      concept_ids: conceptIds.length > 0 ? conceptIds : undefined,
      context_hint: hint.trim() ? hint.trim() : undefined,
      query: topic.trim() ? topic.trim() : undefined,
      max_chunks: task === 'flashcards' ? 0 : undefined,
    }),
    [scope, rootNodeId, scopeNodeId, excluded, extraMaterials, noteTitles, conceptIds, hint, topic, task, showContextSections]
  )

  const [debouncedSpec, setDebouncedSpec] = useState(specBody)
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSpec(specBody), 300)
    return () => clearTimeout(timer)
  }, [specBody])

  const preview = useQuery({
    queryKey: ['ai-preview', courseIdForRequest, JSON.stringify(debouncedSpec)],
    queryFn: () => previewAiContext(courseIdForRequest as number, debouncedSpec),
    enabled: courseIdForRequest !== null,
  })

  const invalidateKeys = async () => {
    const keys: string[][] = []
    if (task === 'quiz' || task === 'practice') keys.push(['quizzes'])
    if (task === 'exercise' || task === 'practice') keys.push(['exercises'])
    if (task === 'flashcards') keys.push(['cards'], ['cards-due'])
    if (task === 'compose') keys.push(['materials'], ['tree'], ['node-artifacts'])
    for (const key of keys) {
      await queryClient.invalidateQueries({ queryKey: key })
    }
  }

  const generate = useMutation({
    mutationFn: () => {
      if (courseIdForRequest === null) {
        throw new Error(t('generate.courseRequired'))
      }
      const context = { ...specBody }
      delete context.query
      delete context.max_chunks
      if (task === 'practice') {
        const requests: Promise<PracticeItem>[] = []
        if (quizTypes.length > 0) {
          requests.push(
            generateQuiz({
              course_id: courseIdForRequest,
              count,
              difficulty: difficulty > 0 ? difficulty : null,
              topic: topic.trim() || null,
              question_types: [...quizTypes],
              shuffle,
              ...context,
            })
          )
        }
        for (const kind of exerciseKinds) {
          requests.push(
            generateExercise({
              course_id: courseIdForRequest,
              topic: topic.trim() || null,
              difficulty: difficulty > 0 ? difficulty : null,
              step_count: stepCount,
              kind,
              ...context,
            })
          )
        }
        if (requests.length === 0) {
          throw new Error(t('generate.practiceEmpty'))
        }
        return Promise.all(requests) as Promise<GenerateResult>
      }
      if (task === 'quiz') {
        return generateQuiz({
          course_id: courseIdForRequest,
          count,
          difficulty: difficulty > 0 ? difficulty : null,
          topic: topic.trim() || null,
          ...context,
        }) as Promise<GenerateResult>
      }
      if (task === 'exercise') {
        return generateExercise({
          course_id: courseIdForRequest,
          topic: topic.trim() || null,
          difficulty: difficulty > 0 ? difficulty : null,
          step_count: stepCount,
          kind: exerciseKind,
          ...context,
        }) as Promise<GenerateResult>
      }
      if (task === 'compose') {
        return composeMaterial({
          course_id: courseIdForRequest,
          kind: composeKind,
          title: topic.trim() || null,
          instructions: instructions.trim() || null,
          regenerate: existing !== null ? true : undefined,
          ...context,
        }).then(
          (result) => result.material as unknown as GenerateResult
        )
      }
      return generateFlashcards({
        source,
        note_id: source === 'note' ? sourceNoteId : null,
        material_id: source === 'material' ? sourceMaterialId : null,
        course_id: courseIdForRequest,
        node_id: scopeNodeId ?? null,
        count,
        context_hint: hint.trim() ? hint.trim() : null,
      }) as Promise<GenerateResult>
    },
    onSuccess: async (result) => {
      setError(null)
      await invalidateKeys()
      onSuccess(result)
    },
    onError: (err: Error) => setError(err.message),
  })

  const toggle = (id: number, list: number[], setList: (next: number[]) => void) => {
    setList(list.includes(id) ? list.filter((entry) => entry !== id) : [...list, id])
  }

  const previewStats = preview.data?.stats

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <Card className="max-h-[85vh] w-full max-w-lg overflow-y-auto">
        <CardHeader>
          <CardTitle className="text-base">{t(`generate.title.${task}`)}</CardTitle>
          <p className="text-muted-foreground text-xs">{t(`generate.hint.${task}`)}</p>
        </CardHeader>
        <CardContent className="space-y-4">
          {courseId === null ? (
            <CourseSelectField value={pickedCourse} onChange={setPickedCourse} />
          ) : null}

          {task === 'flashcards' ? (
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <select
                className="bg-surface border-border rounded-md border px-2 py-1.5"
                value={source}
                onChange={(event) =>
                  setSource(event.target.value as 'mistakes' | 'note' | 'material')
                }
                aria-label={t('cards.sourceLabel')}
              >
                <option value="mistakes">{t('cards.sourceMistakes')}</option>
                <option value="note">{t('cards.sourceNote')}</option>
                <option value="material">{t('cards.sourceMaterial')}</option>
              </select>
              {source === 'note' ? (
                <select
                  className="bg-surface border-border rounded-md border px-2 py-1.5"
                  value={sourceNoteId ?? ''}
                  onChange={(event) => setSourceNoteId(Number(event.target.value))}
                  aria-label={t('cards.noteLabel')}
                >
                  <option value="">{t('cards.pickNote')}</option>
                  {(notes.data?.items ?? []).map((note) => (
                    <option key={note.id} value={note.id}>
                      {note.title}
                    </option>
                  ))}
                </select>
              ) : null}
              {source === 'material' ? (
                <select
                  className="bg-surface border-border rounded-md border px-2 py-1.5"
                  value={sourceMaterialId ?? ''}
                  onChange={(event) => setSourceMaterialId(Number(event.target.value))}
                  aria-label={t('generate.materialLabel')}
                >
                  <option value="">{t('generate.pickMaterial')}</option>
                  {(courseMaterials.data ?? []).map((material) => (
                    <option key={material.id} value={material.id}>
                      {material.title}
                    </option>
                  ))}
                </select>
              ) : null}
              <select
                className="bg-surface border-border rounded-md border px-2 py-1.5"
                value={count}
                onChange={(event) => setCount(Number(event.target.value))}
                aria-label={t('cards.countLabel')}
              >
                {[4, 8, 12, 20].map((value) => (
                  <option key={value} value={value}>
                    {t('quiz.countOption', { count: value })}
                  </option>
                ))}
              </select>
            </div>
          ) : task === 'compose' ? (
            <div className="space-y-3">
              <select
                className="bg-surface border-border w-full rounded-md border px-2 py-1.5 text-sm"
                value={composeKind}
                onChange={(event) => setComposeKind(event.target.value as ComposeKind)}
                aria-label={t('generate.kindLabel')}
              >
                {COMPOSE_KINDS.map((kind) => (
                  <option key={kind} value={kind}>
                    {t(`generate.kind.${kind}`)}
                  </option>
                ))}
              </select>
              {existing !== null ? (
                <div className="bg-subtle border-border flex flex-wrap items-center gap-2 rounded-md border px-3 py-2 text-xs">
                  <span className="min-w-0 flex-1">
                    {t('generate.existingArtifact', { title: existing.title })}
                  </span>
                  <a
                    href={`/library/${existing.material_id}`}
                    className="text-primary hover:underline"
                  >
                    {t('generate.openExisting')}
                  </a>
                </div>
              ) : null}
              <input
                className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
                placeholder={t('generate.titlePlaceholder')}
                value={topic}
                onChange={(event) => setTopic(event.target.value)}
              />
              <textarea
                className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
                placeholder={t('generate.instructionsPlaceholder')}
                rows={3}
                value={instructions}
                onChange={(event) => setInstructions(event.target.value)}
              />
            </div>
          ) : task === 'practice' ? (
            <div className="space-y-3">
              <FieldLabel info={t('generate.topicInfo')} infoTitle={t('generate.topicPlaceholder')} label={t('common.info')}>
                {t('generate.topicLabel')}
              </FieldLabel>
              <input
                className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
                placeholder={t('generate.topicPlaceholder')}
                value={topic}
                onChange={(event) => setTopic(event.target.value)}
              />
              <div className="space-y-2">
                <FieldLabel info={t('generate.quizFormatInfo')} infoTitle={t('generate.quizFormatLabel')} label={t('common.info')}>
                  {t('generate.quizFormatLabel')}
                </FieldLabel>
                <div className="flex flex-wrap gap-1.5">
                  {QUIZ_TYPES.map((type) => {
                    const active = quizTypes.includes(type)
                    return (
                      <span key={type} className="group flex items-center gap-1">
                        <button
                          type="button"
                          aria-pressed={active}
                          className={
                            active
                              ? 'bg-primary text-primary-foreground rounded-full px-2.5 py-1 text-[11px]'
                              : 'bg-subtle text-muted-foreground hover:text-foreground rounded-full px-2.5 py-1 text-[11px]'
                          }
                          onClick={() =>
                            setQuizTypes((prev) =>
                              prev.includes(type)
                                ? prev.filter((entry) => entry !== type)
                                : [...prev, type]
                            )
                          }
                        >
                          {t(`generate.questionType.${type}`)}
                        </button>
                        <InfoButton title={t(`generate.questionType.${type}`)} label={t('common.info')}>
                          {t(`generate.questionTypeInfo.${type}`)}
                        </InfoButton>
                      </span>
                    )
                  })}
                </div>
              </div>
              <div className="flex gap-3">
                <label className="flex flex-1 flex-col gap-1 text-xs">
                  <FieldLabel info={t('generate.countInfo')} infoTitle={t('generate.countLabel')} label={t('common.info')}>
                    {t('generate.countLabel')}
                  </FieldLabel>
                  <select
                    className="bg-surface border-border rounded-md border px-2 py-1.5 text-xs"
                    value={count}
                    onChange={(event) => setCount(Number(event.target.value))}
                  >
                    {[5, 8, 10, 15, 20].map((value) => (
                      <option key={value} value={value}>
                        {t('quiz.countOption', { count: value })}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-1 flex-col gap-1 text-xs">
                  <FieldLabel info={t('generate.shuffleInfo')} infoTitle={t('generate.shuffleLabel')} label={t('common.info')}>
                    {t('generate.shuffleLabel')}
                  </FieldLabel>
                  <button
                    type="button"
                    aria-pressed={shuffle}
                    aria-label={t('generate.shuffleLabel')}
                    className={
                      shuffle
                        ? 'bg-primary text-primary-foreground rounded-md border border-transparent px-2 py-1.5 text-xs'
                        : 'bg-surface border-border text-muted-foreground rounded-md border px-2 py-1.5 text-xs'
                    }
                    onClick={() => setShuffle((prev) => !prev)}
                  >
                    {shuffle ? t('common.yes') : t('common.no')}
                  </button>
                </label>
              </div>
              <div className="space-y-2">
                <FieldLabel info={t('generate.exerciseFormatInfo')} infoTitle={t('generate.exerciseFormatLabel')} label={t('common.info')}>
                  {t('generate.exerciseFormatLabel')}
                </FieldLabel>
                <div className="flex flex-wrap gap-1.5">
                  {EXERCISE_KINDS.map((kind) => {
                    const active = exerciseKinds.includes(kind)
                    return (
                      <span key={kind} className="group flex items-center gap-1">
                        <button
                          type="button"
                          aria-pressed={active}
                          className={
                            active
                              ? 'bg-primary text-primary-foreground rounded-full px-2.5 py-1 text-[11px]'
                              : 'bg-subtle text-muted-foreground hover:text-foreground rounded-full px-2.5 py-1 text-[11px]'
                          }
                          onClick={() =>
                            setExerciseKinds((prev) =>
                              prev.includes(kind)
                                ? prev.filter((entry) => entry !== kind)
                                : [...prev, kind]
                            )
                          }
                        >
                          {t(`generate.exerciseKind.${kind}`)}
                        </button>
                        <InfoButton title={t(`generate.exerciseKind.${kind}`)} label={t('common.info')}>
                          {t(`generate.exerciseKindInfo.${kind}`)}
                        </InfoButton>
                      </span>
                    )
                  })}
                </div>
              </div>
              <div className="flex gap-3">
                <label className="flex flex-1 flex-col gap-1 text-xs">
                  <FieldLabel info={t('generate.stepCountInfo')} infoTitle={t('exercises.stepCountLabel')} label={t('common.info')}>
                    {t('exercises.stepCountLabel')}
                  </FieldLabel>
                  <select
                    className="bg-surface border-border rounded-md border px-2 py-1.5 text-xs"
                    value={stepCount}
                    onChange={(event) => setStepCount(Number(event.target.value))}
                  >
                    {[2, 3, 4, 5, 6].map((value) => (
                      <option key={value} value={value}>
                        {t('exercises.stepOption', { count: value })}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-1 flex-col gap-1 text-xs">
                  <FieldLabel info={t('generate.difficultyInfo')} infoTitle={t('generate.difficulty')} label={t('common.info')}>
                    {t('generate.difficulty')}
                  </FieldLabel>
                  <select
                    className="bg-surface border-border rounded-md border px-2 py-1.5 text-xs"
                    value={difficulty}
                    onChange={(event) => setDifficulty(Number(event.target.value))}
                  >
                    <option value={0}>{t('generate.difficultyMixed')}</option>
                    {[1, 2, 3, 4, 5].map((value) => (
                      <option key={value} value={value}>
                        {t('exercises.difficultyOption', { level: value })}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              <input
                className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
                placeholder={t('generate.topicPlaceholder')}
                value={topic}
                onChange={(event) => setTopic(event.target.value)}
              />
              {task === 'exercise' ? (
                <label className="flex flex-col gap-1 text-xs">
                  {t('generate.exerciseKindLabel')}
                  <select
                    className="bg-surface border-border rounded-md border px-2 py-1.5 text-xs"
                    value={exerciseKind}
                    onChange={(event) =>
                      setExerciseKind(event.target.value as ExerciseKind)
                    }
                  >
                    {EXERCISE_KINDS.map((kind) => (
                      <option key={kind} value={kind}>
                        {t(`generate.exerciseKind.${kind}`)}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              <div className="flex gap-3">
                <label className="flex flex-1 flex-col gap-1 text-xs">
                  {t('generate.difficulty')}
                  <select
                    className="bg-surface border-border rounded-md border px-2 py-1.5 text-xs"
                    value={difficulty}
                    onChange={(event) => setDifficulty(Number(event.target.value))}
                  >
                    <option value={0}>{t('generate.difficultyMixed')}</option>
                    {[1, 2, 3, 4, 5].map((value) => (
                      <option key={value} value={value}>
                        {t('exercises.difficultyOption', { level: value })}
                      </option>
                    ))}
                  </select>
                </label>
                {task === 'quiz' ? (
                  <label className="flex flex-1 flex-col gap-1 text-xs">
                    {t('generate.countLabel')}
                    <select
                      className="bg-surface border-border rounded-md border px-2 py-1.5 text-xs"
                      value={count}
                      onChange={(event) => setCount(Number(event.target.value))}
                    >
                      {[5, 8, 10, 15, 20].map((value) => (
                        <option key={value} value={value}>
                          {t('quiz.countOption', { count: value })}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : (
                  <label className="flex flex-1 flex-col gap-1 text-xs">
                    {t('exercises.stepCountLabel')}
                    <select
                      className="bg-surface border-border rounded-md border px-2 py-1.5 text-xs"
                      value={stepCount}
                      onChange={(event) => setStepCount(Number(event.target.value))}
                    >
                      {[2, 3, 4, 5, 6].map((value) => (
                        <option key={value} value={value}>
                          {t('exercises.stepOption', { count: value })}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
              </div>
            </div>
          )}

          {showContextSections && scopeNodeId !== undefined && !atRoot ? (
            <label className="flex flex-col gap-1 text-xs">
              {t('workspace.scopeLabel')}
              <select
                className="bg-surface border-border rounded-md border px-2 py-1.5 text-xs"
                value={scope}
                onChange={(event) => setScope(event.target.value as GenerateScope)}
              >
                <option value="node">{t('generate.scopeNode')}</option>
                <option value="subtree">{t('generate.scopeSubtree')}</option>
                <option value="course">{t('workspace.scopeCourse')}</option>
              </select>
            </label>
          ) : null}

          {showContextSections ? (
            <section className="space-y-2" aria-label={t('generate.materialsSection')}>
              <h3 className="flex items-center gap-1 text-xs font-semibold">
                <BookOpen className="size-3.5" aria-hidden />
                {t('generate.materialsSection')}
              </h3>
              {materialOptions.length === 0 &&
              extraMaterials.length === 0 &&
              excluded.length === 0 ? (
                <p className="text-muted-foreground text-xs">
                  {t('generate.noMaterials')}
                </p>
              ) : null}
              {materialOptions.length > 0 &&
              excluded.length === 0 &&
              extraMaterials.length === 0 ? (
                <p className="text-muted-foreground text-xs">
                  {t('generate.materialsInScopeHint', { count: materialOptions.length })}
                </p>
              ) : null}
              {excluded.length > 0 || extraMaterials.length > 0 ? (
                <div className="flex flex-wrap gap-1">
                  {excluded.map((id) => (
                    <ContextChip
                      key={`excluded-${id}`}
                      title={materialTitle(id)}
                      tone="excluded"
                      hint={t('generate.excludedHint')}
                      removeLabel={t('generate.restoreMaterial', { title: materialTitle(id) })}
                      onRemove={() =>
                        setExcluded((prev) => prev.filter((entry) => entry !== id))
                      }
                    />
                  ))}
                  {extraMaterials.map((id) => (
                    <ContextChip
                      key={`added-${id}`}
                      title={materialTitle(id)}
                      tone="added"
                      hint={t('generate.addedHint')}
                      removeLabel={t('generate.removeMaterial', { title: materialTitle(id) })}
                      onRemove={() =>
                        setExtraMaterials((prev) => prev.filter((entry) => entry !== id))
                      }
                    />
                  ))}
                </div>
              ) : null}
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" size="sm" onClick={() => setPickerMode('add')}>
                  <Plus className="size-4" aria-hidden />
                  {t('generate.addMaterial')}
                </Button>
                {materialOptions.length > 0 ? (
                  <Button variant="ghost" size="sm" onClick={() => setPickerMode('exclude')}>
                    <Minus className="size-4" aria-hidden />
                    {t('generate.excludeMaterial')}
                  </Button>
                ) : null}
              </div>
            </section>
          ) : null}

          {showContextSections ? (
            <section className="space-y-2" aria-label={t('generate.notesSection')}>
              <h3 className="flex items-center gap-1 text-xs font-semibold">
                <StickyNote className="size-3.5" aria-hidden />
                {t('generate.notesSection')}
              </h3>
              {noteTitles.size === 0 ? (
                <p className="text-muted-foreground text-xs">
                  {t('generate.noNotesAttached')}
                </p>
              ) : (
                <div className="flex flex-wrap gap-1">
                  {Array.from(noteTitles.entries()).map(([id, title]) => (
                    <ContextChip
                      key={`note-${id}`}
                      title={title}
                      tone="added"
                      hint={t('generate.noteHint')}
                      removeLabel={t('generate.removeNote', { title })}
                      onRemove={() =>
                        setNoteTitles((prev) => {
                          const next = new Map(prev)
                          next.delete(id)
                          return next
                        })
                      }
                    />
                  ))}
                </div>
              )}
              <Button variant="outline" size="sm" onClick={() => setShowNotePicker(true)}>
                <Plus className="size-4" aria-hidden />
                {t('generate.addNote')}
              </Button>
            </section>
          ) : null}

          {showContextSections && (concepts.data?.concepts ?? []).length > 0 ? (
            <section className="space-y-2" aria-label={t('generate.conceptsSection')}>
              <h3 className="flex items-center gap-1 text-xs font-semibold">
                <Tag className="size-3.5" aria-hidden />
                {t('generate.conceptsSection')}
              </h3>
              <div className="flex flex-wrap gap-1">
                {(concepts.data?.concepts ?? []).map((concept) => {
                  const active = conceptIds.includes(concept.id)
                  return (
                    <button
                      key={concept.id}
                      type="button"
                      className={
                        active
                          ? 'bg-primary text-primary-foreground rounded-full px-2 py-0.5 text-[11px]'
                          : 'bg-subtle text-muted-foreground rounded-full px-2 py-0.5 text-[11px]'
                      }
                      aria-pressed={active}
                      onClick={() => toggle(concept.id, conceptIds, setConceptIds)}
                    >
                      {concept.name}
                    </button>
                  )
                })}
              </div>
            </section>
          ) : null}

          <label className="flex flex-col gap-1 text-xs">
            {t('generate.hintLabel')}
            <textarea
              className="bg-surface border-border min-h-16 rounded-md border px-2 py-1.5 text-xs"
              placeholder={t('generate.hintPlaceholder')}
              value={hint}
              onChange={(event) => setHint(event.target.value)}
            />
          </label>

          <section className="space-y-1" aria-label={t('generate.previewSection')}>
            <p className="text-xs">
              {preview.isFetching ? (
                <span className="text-muted-foreground inline-flex items-center gap-1">
                  <Loader2 className="size-3 animate-spin" aria-hidden />
                  {t('generate.previewLoading')}
                </span>
              ) : previewStats ? (
                t('generate.previewSummary', {
                  materials: previewStats.materials.length,
                  chunks: previewStats.chunks.length,
                  notes: previewStats.notes.length,
                  concepts: previewStats.concepts.length,
                  hints: previewStats.hints,
                })
              ) : (
                <span className="text-muted-foreground">{t('generate.previewEmpty')}</span>
              )}
            </p>
            {preview.data && preview.data.rendered ? (
              <details>
                <summary className="text-muted-foreground cursor-pointer text-xs">
                  {t('generate.previewShow')}
                </summary>
                <pre className="bg-subtle border-border mt-1 max-h-48 overflow-y-auto rounded-md border p-2 text-[10px] whitespace-pre-wrap">
                  {preview.data.rendered}
                </pre>
              </details>
            ) : null}
          </section>

          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={onClose}>
              {t('settings.cancel')}
            </Button>
            <Button
              size="sm"
              disabled={
                generate.isPending ||
                courseIdForRequest === null ||
                (task === 'practice' &&
                  quizTypes.length === 0 &&
                  exerciseKinds.length === 0)
              }
              onClick={() => generate.mutate()}
            >
              {generate.isPending ? (
                <Loader2 className="animate-spin" aria-hidden />
              ) : (
                <Sparkles aria-hidden />
              )}
              {existing !== null
                ? t('generate.regenerateAction')
                : t(`generate.action.${task}`)}
            </Button>
          </div>
          <ErrorBanner message={error} />
        </CardContent>
      </Card>
      {pickerMode !== null && courseIdForRequest !== null ? (
        <MaterialPickerDialog
          courseId={courseIdForRequest}
          nodeId={scopeNodeId ?? null}
          nodeTitle={
            pickerMode === 'exclude'
              ? t('generate.excludeMaterial')
              : t('generate.addMaterial')
          }
          assignedIds={
            pickerMode === 'exclude'
              ? new Set([...excluded, ...extraMaterials])
              : new Set([...materialOptions.map((option) => option.id), ...extraMaterials])
          }
          mode="select"
          confirmLabel={
            pickerMode === 'exclude'
              ? t('generate.excludeAction')
              : undefined
          }
          lockedLabel={
            pickerMode === 'exclude'
              ? t('generate.alreadyInContext')
              : undefined
          }
          onSelect={(ids) => {
            if (pickerMode === 'exclude') {
              setExcluded((prev) =>
                Array.from(new Set([...prev, ...ids.filter((id) => !extraMaterials.includes(id))]))
              )
            } else {
              setExtraMaterials((prev) => {
                const next = new Set([...prev, ...ids])
                for (const id of prev) {
                  if (excluded.includes(id)) {
                    next.delete(id)
                  }
                }
                return Array.from(next)
              })
            }
            setPickerMode(null)
          }}
          onClose={() => setPickerMode(null)}
        />
      ) : null}
      {showNotePicker && courseIdForRequest !== null ? (
        <NotePickerDialog
          courseId={courseIdForRequest}
          nodeTitle={t('generate.notesSection')}
          onSelect={(entries) => {
            setNoteTitles((prev) => {
              const next = new Map(prev)
              for (const entry of entries) {
                next.set(entry.id, entry.title)
              }
              return next
            })
            setShowNotePicker(false)
          }}
          onClose={() => setShowNotePicker(false)}
        />
      ) : null}
    </div>
  )
}

function ContextChip({
  title,
  tone,
  hint,
  removeLabel,
  onRemove,
}: {
  title: string
  tone: 'added' | 'excluded'
  hint: string
  removeLabel: string
  onRemove: () => void
}) {
  const Icon = tone === 'added' ? Plus : Minus
  return (
    <span
      className={cn(
        'group flex max-w-72 items-center gap-1 rounded-full px-2 py-0.5 text-[11px]',
        tone === 'added'
          ? 'bg-primary/10 text-primary'
          : 'bg-subtle text-muted-foreground'
      )}
      title={hint}
    >
      <Icon className="size-3 shrink-0" aria-hidden />
      <span className="min-w-0 truncate">{title}</span>
      <button
        type="button"
        aria-label={removeLabel}
        className="text-muted-foreground hover:text-foreground rounded-full p-0.5 hover:bg-black/10"
        onClick={onRemove}
      >
        <X className="size-3" aria-hidden />
      </button>
    </span>
  )
}
