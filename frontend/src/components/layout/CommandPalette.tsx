import { useNavigate } from '@tanstack/react-router'

import { useCurrentOrigin } from '@/lib/origin'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  BarChart3,
  BookOpen,
  ClipboardList,
  CornerDownLeft,
  Dumbbell,
  GraduationCap,
  Home,
  MessageSquare,
  NotebookPen,
  Plus,
  Search,
  Settings,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { createNote, courseTree, generateQuiz, listCourses, listExercises, listNotes, listQuizzes, search, type NodeInfo } from '@/lib/api'
import { fuzzyFilter } from '@/lib/fuzzy'
import { useWorkspaceStore } from '@/lib/workspace-store'
import { cn } from '@/lib/utils'

interface Action {
  key: string
  label: string
  hint?: string
  indent?: number
  icon: React.ComponentType<{ className?: string }>
  run: () => void | Promise<void>
}

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const from = useCurrentOrigin()
  const queryClient = useQueryClient()
  const courseId = useWorkspaceStore((state) => state.courseId)
  const setCourse = useWorkspaceStore((state) => state.setCourse)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const [notice, setNotice] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLUListElement>(null)

  const courses = useQuery({
    queryKey: ['courses'],
    queryFn: listCourses,
    enabled: open,
  })

  const resolveCourseId = useCallback((): number | null => {
    if (courseId !== null) {
      return courseId
    }
    const list = courses.data ?? []
    if (list.length === 1 && list[0] !== undefined) {
      return list[0].id
    }
    return null
  }, [courseId, courses.data])

  const tree = useQuery({
    queryKey: ['tree', courseId],
    queryFn: () => courseTree(courseId!),
    enabled: open && courseId !== null,
  })

  const notes = useQuery({
    queryKey: ['notes', 'palette'],
    queryFn: () => listNotes(undefined, undefined, { limit: 100 }),
    enabled: open,
  })

  const quizzes = useQuery({
    queryKey: ['quiz', 'palette'],
    queryFn: () => listQuizzes(),
    enabled: open,
  })

  const exercises = useQuery({
    queryKey: ['exercises', 'palette'],
    queryFn: () => listExercises(),
    enabled: open,
  })

  const contentQuery = query.startsWith('?') ? query.slice(1).trim() : null
  const contentSearch = useQuery({
    queryKey: ['palette-content-search', contentQuery],
    queryFn: () => search(contentQuery as string),
    enabled: open && contentQuery !== null && contentQuery.length > 1,
  })

  const actions = useMemo<Action[]>(() => {
    const go = (to: string) => () => {
      void navigate({ to })
      onClose()
    }
    const nav: Action[] = [
      { key: 'nav-home', label: t('nav.home'), icon: Home, run: go('/') },
      { key: 'nav-chat', label: t('nav.chat'), icon: MessageSquare, run: go('/chat') },
      { key: 'nav-courses', label: t('nav.courses'), icon: GraduationCap, run: go('/courses') },
      { key: 'nav-library', label: t('nav.library'), icon: BookOpen, run: go('/library') },
      { key: 'nav-scores', label: t('nav.scores'), icon: BarChart3, run: go('/scores') },
      { key: 'nav-settings', label: t('nav.settings'), icon: Settings, run: go('/settings') },
    ]
    const quick: Action[] = [
      {
        key: 'new-note',
        label: t('palette.newNote'),
        icon: Plus,
        run: async () => {
          const noteCourseId = resolveCourseId()
          if (noteCourseId === null) {
            setNotice(t('workspace.openCourseFirst'))
            return
          }
          const note = await createNote({
            title: t('notes.defaultTitle'),
            course_id: noteCourseId,
          })
          await queryClient.invalidateQueries({ queryKey: ['notes'] })
          void navigate({ to: '/note/$noteId', params: { noteId: String(note.id) } })
          onClose()
        },
      },
      {
        key: 'open-chat',
        label: t('palette.openChat'),
        icon: MessageSquare,
        run: () => {
          void navigate({ to: '/chat' })
          onClose()
        },
      },
    ]
    const courseActions: Action[] = (courses.data ?? []).flatMap((course) => [
      {
        key: `course-${course.id}`,
        label: t('palette.goToCourse', { title: course.title }),
        hint: t('palette.courseHint'),
        icon: GraduationCap,
        run: () => {
          setCourse(course.id)
          void navigate({ to: '/courses/$courseId', params: { courseId: String(course.id) } })
          onClose()
        },
      },
    ])
    const noteActions: Action[] =
      query.trim() === ''
        ? []
        : fuzzyFilter(notes.data?.items ?? [], query, (note) => note.title)
            .slice(0, 8)
            .map((note) => ({
              key: `note-${note.id}`,
              label: t('palette.noteResult', { title: note.title }),
              icon: NotebookPen,
              run: () => {
                void navigate({ to: '/note/$noteId', params: { noteId: String(note.id) } })
                onClose()
              },
            }))
    const quizActions: Action[] =
      query.trim() === ''
        ? []
        : fuzzyFilter((quizzes.data ?? []).slice(0, 100), query, (quiz) => quiz.title)
            .slice(0, 5)
            .map((quiz) => ({
              key: `quiz-${quiz.id}`,
              label: t('palette.quizResult', { title: quiz.title }),
              icon: ClipboardList,
              run: () => {
                void navigate({
                  to: '/quiz/$activityId',
                  params: { activityId: String(quiz.id) },
                  search: { from },
                })
                onClose()
              },
            }))
    const exerciseActions: Action[] =
      query.trim() === ''
        ? []
        : fuzzyFilter((exercises.data ?? []).slice(0, 100), query, (exercise) => exercise.title)
            .slice(0, 5)
            .map((exercise) => ({
              key: `exercise-${exercise.id}`,
              label: t('palette.exerciseResult', { title: exercise.title }),
              icon: Dumbbell,
              run: () => {
                void navigate({
                  to: '/exercises/$exerciseId',
                  params: { exerciseId: String(exercise.id) },
                  search: { from },
                })
                onClose()
              },
            }))
    const nodeActions: Action[] = []
    if (courseId !== null) {
      const collect = (entries: NodeInfo[]) => {
        for (const entry of entries) {
          if (entry.depth >= 1 && entry.depth <= 2) {
            const courseRef = courseId
            nodeActions.push(
              {
                key: `quiz-node-${entry.id}`,
                label: t('palette.quizMeOn', { title: entry.title }),
                hint: t('palette.nodeHint'),
                indent: entry.depth,
                icon: ClipboardList,
                run: async () => {
                  const activity = await generateQuiz({
                    course_id: courseRef,
                    node_id: entry.id,
                    count: 8,
                  })
                  await queryClient.invalidateQueries({ queryKey: ['quizzes'] })
                  void navigate({
                    to: '/quiz/$activityId',
                    params: { activityId: String(activity.id) },
                    search: { from },
                  })
                  onClose()
                },
              },
              {
                key: `open-node-${entry.id}`,
                label: t('palette.openNode', { title: entry.title }),
                indent: entry.depth,
                icon: BookOpen,
                run: () => {
                  void navigate({
                    to: '/courses/$courseId/n/$nodeId',
                    params: { courseId: String(courseRef), nodeId: String(entry.id) },
                  })
                  onClose()
                },
              }
            )
          }
          collect(entry.children)
        }
      }
      collect(tree.data ?? [])
    }
    return [...quick, ...nav, ...noteActions, ...quizActions, ...exerciseActions, ...courseActions, ...nodeActions]
  }, [
    t,
    courses.data,
    tree.data,
    notes.data,
    quizzes.data,
    exercises.data,
    query,
    courseId,
    navigate,
    from,
    onClose,
    queryClient,
    setCourse,
    resolveCourseId,
  ])

  const filtered = useMemo(() => {
    if (contentQuery !== null) {
      return (contentSearch.data?.hits ?? [])
        .slice(0, 8)
        .map<Action>((hit) => ({
          key: `content-${hit.material_id}`,
          label: t('palette.contentResult', {
            title: hit.title,
            snippet: (hit.snippet ?? '').slice(0, 90),
          }),
          icon: Search,
          run: () => {
            void navigate({
              to: '/library/$materialId',
              params: { materialId: String(hit.material_id) },
            })
            onClose()
          },
        }))
    }
    return fuzzyFilter(actions, query, (action) => action.label)
  }, [actions, query, contentQuery, contentSearch.data, t, navigate, onClose])

  useEffect(() => {
    if (open) {
      setQuery('')
      setActive(0)
      setNotice(null)
      requestAnimationFrame(() => inputRef.current?.focus())
    }
  }, [open])

  useEffect(() => {
    setActive((current) => (current < filtered.length ? current : 0))
  }, [filtered.length])

  if (!open) {
    return null
  }

  const runActive = () => {
    const action = filtered[active]
    if (action !== undefined) {
      void action.run()
    }
  }

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActive((current) => Math.min(current + 1, filtered.length - 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActive((current) => Math.max(current - 1, 0))
    } else if (event.key === 'Enter') {
      event.preventDefault()
      runActive()
    } else if (event.key === 'Escape') {
      event.preventDefault()
      onClose()
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 pt-[15vh]"
      role="dialog"
      aria-modal="true"
      aria-label={t('palette.title')}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose()
        }
      }}
    >
      <div
        className="bg-surface border-border w-full max-w-lg overflow-hidden rounded-xl border shadow-xl"
        onKeyDown={onKeyDown}
      >
        <div className="border-border flex items-center gap-2 border-b px-3 py-2.5">
          <Search className="text-muted-foreground size-4 shrink-0" aria-hidden />
          <input
            ref={inputRef}
            className="min-w-0 flex-1 bg-transparent text-sm outline-none"
            placeholder={t('palette.placeholder')}
            aria-label={t('palette.placeholder')}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <kbd className="text-muted-foreground border-border rounded border px-1.5 py-0.5 text-[10px]">
            {t('palette.escKey')}
          </kbd>
        </div>
        {notice ? (
          <p role="status" className="text-muted-foreground border-border border-t px-4 py-2 text-xs">
            {notice}
          </p>
        ) : null}
        {contentQuery !== null && contentSearch.isFetching ? (
          <p role="status" className="text-muted-foreground border-border border-t px-4 py-2 text-xs">
            {t('palette.contentSearching')}
          </p>
        ) : null}
        {contentQuery === null ? (
          <p className="text-muted-foreground border-border border-t px-4 py-1.5 text-[10px]">
            {t('palette.contentHint')}
          </p>
        ) : null}
        {filtered.length === 0 ? (
          <p className="text-muted-foreground px-4 py-6 text-center text-sm">
            {t('palette.noResults')}
          </p>
        ) : (
          <ul ref={listRef} className="max-h-80 overflow-y-auto p-1" role="listbox">
            {filtered.map((action, index) => (
              <li key={action.key} role="option" aria-selected={index === active}>
                <button
                  type="button"
                  className={cn(
                    'flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm',
                    index === active ? 'bg-subtle' : 'hover:bg-subtle/60'
                  )}
                  onMouseEnter={() => setActive(index)}
                  onClick={() => void action.run()}
                >
                  <action.icon className="text-muted-foreground size-4 shrink-0" aria-hidden />
                  <span
                    className="flex-1 truncate"
                    style={{ paddingLeft: `${(action.indent ?? 0) * 10}px` }}
                  >
                    {action.label}
                  </span>
                  {action.hint ? (
                    <span className="text-muted-foreground shrink-0 text-[10px]">
                      {action.hint}
                    </span>
                  ) : null}
                  {index === active ? (
                    <CornerDownLeft className="text-muted-foreground size-3.5 shrink-0" aria-hidden />
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

export function useCommandPaletteOpen() {
  const [open, setOpen] = useState(false)
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setOpen((value) => !value)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  return { open, close: () => setOpen(false), openPalette: () => setOpen(true) }
}
