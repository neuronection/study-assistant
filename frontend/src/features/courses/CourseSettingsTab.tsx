import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { ErrorBanner } from '@/components/ui/error-banner'
import { TabActionBar } from '@/components/layout/TabActionBar'
import {
  assignCourseTask,
  assignCourseTaskDefault,
  listCourseTaskDefaults,
  listCourseTasks,
  listModels,
  updateCourse,
  type Course,
} from '@/lib/api'
import { cn } from '@/lib/utils'

const SUB_TABS = ['general', 'tasks'] as const

const CAP_ORDER = ['text', 'vision', 'embeddings', 'audio'] as const

type SubTab = (typeof SUB_TABS)[number]

export function CourseSettingsTab({
  courseId,
  course,
}: {
  courseId: string
  course: Course
}) {
  const { t } = useTranslation()
  const [subTab, setSubTab] = useState<SubTab>('general')

  return (
    <div className="space-y-4" data-testid="course-settings-tab">
      <div className="mb-2 flex flex-wrap items-center gap-1" role="tablist">
        {SUB_TABS.map((entry) => (
          <button
            key={entry}
            type="button"
            role="tab"
            aria-selected={subTab === entry}
            aria-current={subTab === entry ? 'page' : undefined}
            className={cn(
              'flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm transition-colors',
              subTab === entry
                ? 'bg-primary/15 text-primary font-medium'
                : 'text-muted-foreground hover:bg-subtle hover:text-foreground'
            )}
            onClick={() => setSubTab(entry)}
          >
            {t(`courseSettings.sub_${entry}`)}
          </button>
        ))}
      </div>
      {subTab === 'general' ? (
        <GeneralSection courseId={Number(courseId)} course={course} />
      ) : (
        <TasksSection courseId={Number(courseId)} />
      )}
    </div>
  )
}

function GeneralSection({
  courseId,
  course,
}: {
  courseId: number
  course: Course
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [title, setTitle] = useState(course.title)
  const [description, setDescription] = useState(course.description ?? '')

  const dirty = title.trim() !== course.title || description !== (course.description ?? '')

  const save = useMutation({
    mutationFn: () =>
      updateCourse(courseId, { title: title.trim(), description }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['courses'] })
      await queryClient.invalidateQueries({ queryKey: ['tree'] })
      await queryClient.invalidateQueries({ queryKey: ['node-workspace'] })
    },
  })

  return (
    <div className="space-y-4">
      <TabActionBar
        actions={[
          {
            label: t('courseSettings.save'),
            onAction: () => save.mutate(),
            pending: save.isPending,
            disabled: !dirty || title.trim().length === 0,
            primary: true,
          },
        ]}
      />
      {save.isSuccess && !save.isPending ? (
        <p className="text-success text-xs">{t('courseSettings.saved')}</p>
      ) : null}
      <ErrorBanner message={save.isError ? (save.error as Error).message : null} />
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t('courseSettings.generalTitle')}</CardTitle>
          <p className="text-muted-foreground text-xs">{t('courseSettings.generalHint')}</p>
        </CardHeader>
        <CardContent className="space-y-3">
          <label className="block space-y-1">
            <span className="text-sm font-medium">{t('courseSettings.titleLabel')}</span>
            <input
              className="bg-surface border-border w-full rounded-md border px-2 py-1.5 text-sm"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              aria-label={t('courseSettings.titleLabel')}
            />
          </label>
          <label className="block space-y-1">
            <span className="text-sm font-medium">{t('courseSettings.descriptionLabel')}</span>
            <textarea
              className="bg-surface border-border min-h-24 w-full rounded-md border px-2 py-1.5 text-sm"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              aria-label={t('courseSettings.descriptionLabel')}
            />
          </label>
        </CardContent>
      </Card>
    </div>
  )
}

function TasksSection({ courseId }: { courseId: number }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const tasks = useQuery({
    queryKey: ['course-tasks', courseId],
    queryFn: () => listCourseTasks(courseId),
  })
  const defaults = useQuery({
    queryKey: ['course-task-defaults', courseId],
    queryFn: () => listCourseTaskDefaults(courseId),
  })
  const models = useQuery({ queryKey: ['models'], queryFn: listModels })
  const enabledModels = (models.data ?? []).filter(
    (model) => model.enabled && !model.missing
  )
  const assign = useMutation({
    mutationFn: ({
      task,
      field,
      otherValue,
      modelId,
    }: {
      task: string
      field: 'model' | 'fallback'
      otherValue: number | null
      modelId: number | null
    }) =>
      field === 'model'
        ? assignCourseTask(courseId, task, modelId, otherValue)
        : assignCourseTask(courseId, task, otherValue, modelId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['course-tasks', courseId] })
    },
  })
  const assignDefault = useMutation({
    mutationFn: ({
      requires,
      field,
      otherValue,
      modelId,
    }: {
      requires: string
      field: 'model' | 'fallback'
      otherValue: number | null
      modelId: number | null
    }) =>
      field === 'model'
        ? assignCourseTaskDefault(courseId, requires, modelId, otherValue)
        : assignCourseTaskDefault(courseId, requires, otherValue, modelId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['course-task-defaults', courseId] })
      await queryClient.invalidateQueries({ queryKey: ['course-tasks', courseId] })
    },
  })

  const assignable = (requires: string) =>
    enabledModels.filter((model) => model.caps.includes(requires))
  const defaultByCap = new Map(
    (defaults.data ?? []).map((entry) => [entry.requires, entry])
  )

  return (
    <div className="space-y-2">
      <p className="text-muted-foreground text-sm">{t('courseSettings.tasksHint')}</p>
      <ErrorBanner message={assign.isError ? (assign.error as Error).message : null} />
      <ErrorBanner
        message={assignDefault.isError ? (assignDefault.error as Error).message : null}
      />
      <div className="border-border space-y-2 rounded-md border p-3">
        <div>
          <p className="text-sm font-medium">
            {t('settings.defaultModelsTitle')}
          </p>
          <p className="text-muted-foreground text-xs">
            {t('courseSettings.courseDefaultsHint')}
          </p>
        </div>
        {CAP_ORDER.map((requires) => {
          const capLabel = t(`settings.caps.${requires}`)
          const entry = defaultByCap.get(requires)
          const options = assignable(requires)
          return (
            <div key={requires} className="flex flex-wrap items-center gap-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">
                  {t('settings.defaultModelLabel', { cap: capLabel })}
                </p>
                <p className="text-muted-foreground text-xs">
                  {entry?.global_model_label != null
                    ? t('settings.inheritedFromDefault', {
                        label: entry.global_model_label,
                      })
                    : t('settings.defaultModelHint', { cap: capLabel })}
                </p>
              </div>
              <select
                className="bg-surface border-border max-w-52 rounded-md border px-2 py-1.5 text-xs"
                value={entry?.model_id ?? ''}
                onChange={(event) => {
                  const value = event.target.value
                  assignDefault.mutate({
                    requires,
                    field: 'model',
                    otherValue: entry?.fallback_model_id ?? null,
                    modelId: value === '' ? null : Number(value),
                  })
                }}
                aria-label={t('settings.defaultModelLabel', { cap: capLabel })}
              >
                <option value="">{t('settings.unassigned')}</option>
                {options.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.label}
                  </option>
                ))}
              </select>
              <select
                className="bg-surface border-border max-w-52 rounded-md border px-2 py-1.5 text-xs"
                value={entry?.fallback_model_id ?? ''}
                onChange={(event) => {
                  const value = event.target.value
                  assignDefault.mutate({
                    requires,
                    field: 'fallback',
                    otherValue: entry?.model_id ?? null,
                    modelId: value === '' ? null : Number(value),
                  })
                }}
                aria-label={`${t('settings.defaultModelLabel', { cap: capLabel })} — ${t('settings.defaultFallbackLabel')}`}
              >
                <option value="">{t('settings.unassigned')}</option>
                {options.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.label}
                  </option>
                ))}
              </select>
            </div>
          )
        })}
      </div>
      {(tasks.data ?? []).map((task) => (
        <div
          key={task.task}
          className="border-border rounded-md border px-3 py-2"
        >
          <div className="flex items-start gap-3">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">
                {task.task}
                <span className="text-muted-foreground ml-2 rounded-full bg-subtle px-2 py-0.5 text-[11px]">
                  {t(`settings.caps.${task.requires}`)}
                </span>
                {assign.isPending ? (
                  <Loader2 className="ml-2 inline size-3 animate-spin" aria-hidden />
                ) : null}
              </p>
              <p className="text-muted-foreground truncate text-xs">{task.description}</p>
              {task.model_id === null && task.global_model_label !== null ? (
                <p className="text-muted-foreground text-[11px]">
                  {t('settings.inheritedFromDefault', { label: task.global_model_label })}
                </p>
              ) : null}
            </div>
            <select
              className="bg-surface border-border max-w-52 rounded-md border px-2 py-1.5 text-xs"
              value={task.model_id ?? ''}
              onChange={(event) => {
                const value = event.target.value
                assign.mutate({
                  task: task.task,
                  field: 'model',
                  otherValue: task.fallback_model_id,
                  modelId: value === '' ? null : Number(value),
                })
              }}
              aria-label={t('courseSettings.modelAria', { task: task.task })}
            >
              <option value="">
                {task.global_model_label !== null
                  ? t('settings.inheritDefault')
                  : t('settings.unassigned')}
              </option>
              {assignable(task.requires).map((model) => (
                <option key={model.id} value={model.id}>
                  {model.label}
                </option>
              ))}
            </select>
            <select
              className="bg-surface border-border max-w-52 rounded-md border px-2 py-1.5 text-xs"
              value={task.fallback_model_id ?? ''}
              onChange={(event) => {
                const value = event.target.value
                assign.mutate({
                  task: task.task,
                  field: 'fallback',
                  otherValue: task.model_id,
                  modelId: value === '' ? null : Number(value),
                })
              }}
              aria-label={t('courseSettings.fallbackAria', { task: task.task })}
            >
              <option value="">
                {task.global_fallback_model_label !== null
                  ? t('settings.inheritDefault')
                  : t('settings.unassigned')}
              </option>
              {assignable(task.requires).map((model) => (
                <option key={model.id} value={model.id}>
                  {model.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      ))}
    </div>
  )
}
