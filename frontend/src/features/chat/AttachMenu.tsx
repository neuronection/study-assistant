import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Check,
  Dumbbell,
  FileText,
  GraduationCap,
  ListChecks,
  Loader2,
  StickyNote,
  Upload,
} from 'lucide-react'
import { useState, type ComponentType } from 'react'
import { useTranslation } from 'react-i18next'

import { MaterialUploadDropzone } from '@/components/materials/MaterialUploadDropzone'
import { useMaterialUpload } from '@/components/materials/materialUpload'
import {
  createFolder,
  listCourses,
  listExercises,
  listFolders,
  listMaterials,
  listNotes,
  listQuizzes,
  type ChatAttachmentKind,
} from '@/lib/api'
import { fuzzyFilter } from '@/lib/fuzzy'

import { cn } from '@/lib/utils'

export const CHAT_UPLOADS_FOLDER = 'Chat uploads'

export const ATTACH_KIND_ICONS: Record<
  ChatAttachmentKind,
  { icon: ComponentType<{ className?: string }>; labelKey: string }
> = {
  material: { icon: FileText, labelKey: 'chat.attach.tabMaterials' },
  note: { icon: StickyNote, labelKey: 'chat.attach.tabNotes' },
  quiz: { icon: ListChecks, labelKey: 'chat.attach.tabQuizzes' },
  exercise: { icon: Dumbbell, labelKey: 'chat.attach.tabExercises' },
  course: { icon: GraduationCap, labelKey: 'chat.attach.tabCourses' },
  node: { icon: FileText, labelKey: 'chat.attach.tabCourses' },
}

export interface PendingAttachment {
  kind: ChatAttachmentKind
  id: number
  title: string
}

type TabKey = 'materials' | 'notes' | 'quizzes' | 'exercises' | 'courses' | 'upload'

const TABS: {
  key: TabKey
  icon: ComponentType<{ className?: string }>
  titleKey: string
}[] = [
  { key: 'materials', icon: FileText, titleKey: 'chat.attach.tabMaterials' },
  { key: 'notes', icon: StickyNote, titleKey: 'chat.attach.tabNotes' },
  { key: 'quizzes', icon: ListChecks, titleKey: 'chat.attach.tabQuizzes' },
  { key: 'exercises', icon: Dumbbell, titleKey: 'chat.attach.tabExercises' },
  { key: 'courses', icon: GraduationCap, titleKey: 'chat.attach.tabCourses' },
  { key: 'upload', icon: Upload, titleKey: 'chat.attach.tabUpload' },
]

interface Row {
  kind: ChatAttachmentKind
  id: number
  title: string
  meta: string | null
}

export function AttachMenu({
  courseId,
  uploadCourseId = courseId,
  uploadHint,
  resolveUploadFolder,
  attached,
  onSelect,
  extraActions = [],
}: {
  courseId: number | null
  uploadCourseId?: number | null
  uploadHint?: string
  resolveUploadFolder?: () => Promise<number | null>
  attached: PendingAttachment[]
  onSelect: (item: PendingAttachment) => void
  extraActions?: { key: string; icon: ComponentType<{ className?: string }>; label: string; run: () => void }[]
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<TabKey>('materials')
  const [query, setQuery] = useState('')

  const materials = useQuery({
    queryKey: ['attach', 'materials', courseId],
    queryFn: () => listMaterials(undefined, courseId ?? undefined),
    enabled: tab === 'materials',
  })
  const notes = useQuery({
    queryKey: ['attach', 'notes', courseId],
    queryFn: () => listNotes(undefined, courseId ?? undefined, { limit: 100 }),
    enabled: tab === 'notes',
  })
  const quizzes = useQuery({
    queryKey: ['attach', 'quizzes', courseId],
    queryFn: () => listQuizzes(courseId ?? undefined),
    enabled: tab === 'quizzes',
  })
  const exercises = useQuery({
    queryKey: ['attach', 'exercises', courseId],
    queryFn: () => listExercises(courseId ?? undefined),
    enabled: tab === 'exercises',
  })
  const courses = useQuery({
    queryKey: ['attach', 'courses'],
    queryFn: () => listCourses(),
    enabled: tab === 'courses',
  })

  const upload = useMaterialUpload({
    courseId: uploadCourseId,
    getFolderId:
      resolveUploadFolder ??
      (async () => {
        const folders = await listFolders(uploadCourseId as number)
        const existing = folders.find((folder) => folder.name === CHAT_UPLOADS_FOLDER)
        return (
          existing ?? (await createFolder(CHAT_UPLOADS_FOLDER, null, uploadCourseId as number))
        ).id
      }),
    onUploaded: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ['attach'] })
      onSelect({
        kind: 'material',
        id: result.material.id,
        title: result.material.title,
      })
    },
  })

  let rows: Row[] = []
  let loading = false
  if (tab === 'materials') {
    loading = materials.isLoading
    rows = (materials.data ?? []).map((material) => ({
      kind: 'material' as const,
      id: material.id,
      title: material.title,
      meta: material.kind,
    }))
  } else if (tab === 'notes') {
    loading = notes.isLoading
    rows = (notes.data?.items ?? []).map((note) => ({
      kind: 'note' as const,
      id: note.id,
      title: note.title,
      meta: note.tags.join(' · ') || null,
    }))
  } else if (tab === 'quizzes') {
    loading = quizzes.isLoading
    rows = (quizzes.data ?? []).map((quiz) => ({
      kind: 'quiz' as const,
      id: quiz.id,
      title: quiz.title,
      meta: t('chat.attach.questions', { count: quiz.question_count }),
    }))
  } else if (tab === 'exercises') {
    loading = exercises.isLoading
    rows = (exercises.data ?? []).map((exercise) => ({
      kind: 'exercise' as const,
      id: exercise.id,
      title: exercise.title,
      meta: t('chat.attach.steps', { count: exercise.step_count }),
    }))
  } else if (tab === 'courses') {
    loading = courses.isLoading
    rows = (courses.data ?? []).map((course) => ({
      kind: 'course' as const,
      id: course.id,
      title: course.title,
      meta: course.description,
    }))
  }
  if (query.trim() && tab !== 'upload') {
    rows = fuzzyFilter(rows, query, (row) =>
      row.meta ? `${row.title} ${row.meta}` : row.title,
    )
  }

  return (
    <div className="flex flex-col gap-2">
      {extraActions.length > 0 ? (
        <div className="grid grid-cols-1 gap-1">
          {extraActions.map((action) => {
            const Icon = action.icon
            return (
              <button
                key={action.key}
                type="button"
                title={action.label}
                aria-label={action.label}
                className="hover:bg-subtle text-foreground flex items-center gap-2 rounded-md px-2 py-1.5 text-xs font-medium transition-colors"
                onClick={action.run}
              >
                <Icon className="text-muted-foreground size-3.5 shrink-0" aria-hidden />
                <span className="truncate">{action.label}</span>
              </button>
            )
          })}
          <div className="bg-border my-0.5 h-px w-full" role="separator" />
        </div>
      ) : null}
      <div role="tablist" aria-label={t('chat.attach.buttonTitle')} className="flex gap-0.5">
        {TABS.map((entry) => {
          const Icon = entry.icon
          const active = tab === entry.key
          return (
            <button
              key={entry.key}
              type="button"
              role="tab"
              aria-selected={active}
              title={t(entry.titleKey)}
              className={cn(
                'rounded-md p-1.5 transition-colors',
                active
                  ? 'bg-subtle text-foreground'
                  : 'text-muted-foreground hover:bg-subtle',
              )}
              onClick={() => setTab(entry.key)}
            >
              <Icon className="size-4" aria-hidden />
            </button>
          )
        })}
      </div>

      {tab === 'upload' ? (
        <div className="flex flex-col gap-2 py-1">
          {uploadCourseId === null ? (
            <p className="text-muted-foreground px-1 text-xs">
              {t('chat.attach.uploadNeedsCourse')}
            </p>
          ) : (
            <MaterialUploadDropzone
              upload={upload}
              variant="row"
              label={t('chat.attach.chooseFile')}
              hint={uploadHint ?? t('chat.attach.uploadHint')}
            />
          )}
        </div>
      ) : (
        <>
          <input
            className="bg-surface border-border rounded-md border px-2 py-1.5 text-xs"
            placeholder={t('chat.attach.searchPlaceholder')}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <div className="max-h-64 overflow-y-auto">
            {loading ? (
              <p className="text-muted-foreground flex items-center gap-2 px-1 py-2 text-xs">
                <Loader2 className="size-3.5 animate-spin" aria-hidden />
                {t('chat.attach.loading')}
              </p>
            ) : rows.length === 0 ? (
              <p className="text-muted-foreground px-1 py-2 text-xs">
                {t('chat.attach.noResults')}
              </p>
            ) : (
              rows.map((row) => {
                const isAttached = attached.some(
                  (item) => item.kind === row.kind && item.id === row.id,
                )
                const Icon = ATTACH_KIND_ICONS[row.kind].icon
                return (
                  <button
                    key={`${row.kind}-${row.id}`}
                    type="button"
                    disabled={isAttached}
                    onClick={() =>
                      onSelect({ kind: row.kind, id: row.id, title: row.title })
                    }
                    className="hover:bg-subtle flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left transition-colors disabled:opacity-40"
                  >
                    <Icon className="text-muted-foreground mt-0.5 size-4 shrink-0" aria-hidden />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{row.title}</span>
                      {row.meta ? (
                        <span className="text-muted-foreground block truncate text-xs">
                          {row.meta}
                        </span>
                      ) : null}
                    </span>
                    {isAttached ? (
                      <Check className="text-success mt-0.5 size-3.5 shrink-0" aria-hidden />
                    ) : null}
                  </button>
                )
              })
            )}
          </div>
        </>
      )}
    </div>
  )
}
