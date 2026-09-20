import { useNavigate } from '@tanstack/react-router'
import { AnimatePresence, motion } from 'framer-motion'

import { useCurrentOrigin } from '@/lib/origin'
import { useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  BarChart3,
  BookOpen,
  Camera,
  ClipboardList,
  CornerDownLeft,
  Dumbbell,
  GraduationCap,
  History,
  Home,
  MessageSquare,
  Link2,
  NotebookPen,
  Plus,
  Search,
  Settings,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { createNote, courseTree, generateQuiz, listCourses, listExercises, listNotes, listQuizzes, search, type NodeInfo } from '@/lib/api'
import { useCaptureStore } from '@/lib/capture-store'
import { useImportUrlStore } from '@/lib/import-url-store'
import { fuzzyFilter } from '@/lib/fuzzy'
import { useMotionPresets } from '@/lib/motion'
import { getRecentNodes, resolveRecentNodes } from '@/lib/recent-nodes'
import { useInterfacePrefs } from '@/lib/interface-prefs'
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
  const presets = useMotionPresets()
  const courseId = useWorkspaceStore((state) => state.courseId)
  const interfacePrefs = useInterfacePrefs()
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

  const treeCourseIds = useMemo(() => {
    const ids = (courses.data ?? []).map((course) => course.id)
    if (courseId !== null && !ids.includes(courseId)) {
      ids.push(courseId)
    }
    return ids
  }, [courses.data, courseId])

  const treeQueries = useQueries({
    queries: treeCourseIds.map((id) => ({
      queryKey: ['tree', String(id)],
      queryFn: () => courseTree(id),
      enabled: open,
    })),
  })

  const trees = useMemo(() => {
    const map = new Map<number, NodeInfo[]>()
    treeCourseIds.forEach((id, index) => {
      const data = treeQueries[index]?.data
      if (data !== undefined) {
        map.set(id, data as NodeInfo[])
      }
    })
    return map
  }, [treeCourseIds, treeQueries])

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
        key: 'quick-capture',
        label: t('capture.paletteAction'),
        icon: NotebookPen,
        run: () => {
          useCaptureStore.getState().openCapture()
          onClose()
        },
      },
      {
        key: 'snap-region',
        label: t('capture.snapPaletteAction'),
        icon: Camera,
        run: () => {
          useCaptureStore.getState().openSnap()
          onClose()
        },
      },
      {
        key: 'import-url',
        label: t('importUrl.title'),
        icon: Link2,
        run: () => {
          useImportUrlStore.getState().openImport()
          onClose()
        },
      },
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
    const quizNodeActions: Action[] = []
    if (courseId !== null) {
      const collectQuiz = (entries: NodeInfo[]) => {
        for (const entry of entries) {
          if (entry.depth >= 1 && entry.depth <= 2) {
            const courseRef = courseId
            quizNodeActions.push({
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
            })
          }
          collectQuiz(entry.children)
        }
      }
      collectQuiz(trees.get(courseId) ?? [])
    }
    return [...quick, ...nav, ...noteActions, ...quizActions, ...exerciseActions, ...courseActions, ...quizNodeActions]
  }, [
    t,
    courses.data,
    trees,
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

  const nodeActions = useMemo<Action[]>(() => {
    const openActions: Action[] = []
    for (const id of treeCourseIds) {
      const root = trees.get(id)
      if (root === undefined || root.length === 0) {
        continue
      }
      const courseTitle = (courses.data ?? []).find((course) => course.id === id)?.title ?? root[0]!.title
      const collect = (entries: NodeInfo[], trail: string[]) => {
        for (const entry of entries) {
          if (entry.depth >= 1) {
            const breadcrumb = trail.join(' › ')
            openActions.push({
              key: `open-node-${id}-${entry.id}`,
              label: t('palette.openNode', { title: entry.title }),
              hint: breadcrumb,
              indent: entry.depth,
              icon: BookOpen,
              run: () => {
                void navigate({
                  to: '/courses/$courseId/n/$nodeId',
                  params: { courseId: String(id), nodeId: String(entry.id) },
                })
                onClose()
              },
            })
            collect(entry.children, [...trail, entry.title])
          } else {
            collect(entry.children, trail)
          }
        }
      }
      collect(root, [courseTitle])
    }
    return openActions
  }, [treeCourseIds, trees, courses.data, t, navigate, onClose])

  const recentActions = useMemo<Action[]>(() => {
    if (query.trim() !== '' || !interfacePrefs.paletteRecent) {
      return []
    }
    const courseTitles = new Map(
      (courses.data ?? []).map((course) => [course.id, course.title])
    )
    return resolveRecentNodes(getRecentNodes().slice(0, 5), trees, courseTitles).map(
      (row) => ({
        key: `recent-${row.courseId}-${row.nodeId}`,
        label: row.title,
        hint: row.breadcrumb,
        icon: History,
        run: () => {
          void navigate({
            to: '/courses/$courseId/n/$nodeId',
            params: { courseId: String(row.courseId), nodeId: String(row.nodeId) },
          })
          onClose()
        },
      })
    )
  }, [query, trees, courses.data, navigate, onClose, interfacePrefs])

  const filtered = useMemo(() => {
    if (contentQuery !== null) {
      const contentActions: Action[] = []
      for (const hit of contentSearch.data?.hits.slice(0, 8) ?? []) {
        contentActions.push({
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
        })
        const placement = hit.nodes?.[0]
        if (placement !== undefined && contentActions.length < 12) {
          contentActions.push({
            key: `content-node-${hit.material_id}-${placement.node_id}`,
            label: t('palette.openInNode', { node: placement.node_title }),
            hint: hit.title,
            icon: BookOpen,
            run: () => {
              void navigate({
                to: '/courses/$courseId/n/$nodeId',
                params: {
                  courseId: String(placement.course_id),
                  nodeId: String(placement.node_id),
                },
                search: { material: hit.material_id },
              })
              onClose()
            },
          })
        }
      }
      return contentActions
    }
    const actionText = (action: Action) => (action.hint ? `${action.label} ${action.hint}` : action.label)
    return [
      ...recentActions,
      ...fuzzyFilter(actions, query, actionText),
      ...fuzzyFilter(nodeActions, query, actionText).slice(0, 40),
    ]
  }, [actions, nodeActions, recentActions, query, contentQuery, contentSearch.data, t, navigate, onClose])

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
    <AnimatePresence>
      {open ? (
        <motion.div
          key="palette-backdrop"
          className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 pt-[15vh]"
          role="dialog"
          aria-modal="true"
          aria-label={t('palette.title')}
          initial={presets.backdrop.initial}
          animate={presets.backdrop.animate}
          exit={presets.backdrop.exit}
          transition={presets.backdrop.transition}
          onClick={(event) => {
            if (event.target === event.currentTarget) {
              onClose()
            }
          }}
        >
          <motion.div
            className="bg-surface border-border w-full max-w-lg overflow-hidden rounded-xl border shadow-[var(--as-shadow-3)]"
            onKeyDown={onKeyDown}
            initial={presets.panel.initial}
            animate={presets.panel.animate}
            exit={presets.panel.exit}
            transition={presets.panel.transition}
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
          <motion.ul
            ref={listRef}
            className="max-h-80 overflow-y-auto p-1"
            role="listbox"
            variants={presets.staggeredRows()}
            initial="hidden"
            animate="show"
          >
            {filtered.map((action, index) => (
              <motion.li
                key={action.key}
                role="option"
                aria-selected={index === active}
                variants={presets.row}
              >
                <button
                  type="button"
                  className={cn(
                    'relative flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm',
                    index === active ? 'text-foreground' : 'hover:bg-subtle/60'
                  )}
                  onMouseEnter={() => setActive(index)}
                  onClick={() => void action.run()}
                >
                  {index === active ? (
                    <motion.span
                      layoutId="palette-active"
                      className="bg-subtle absolute inset-0 rounded-md"
                      aria-hidden
                      transition={presets.reduced ? { duration: 0 } : { type: 'spring', stiffness: 500, damping: 40 }}
                    />
                  ) : null}
                  <action.icon className="text-muted-foreground relative size-4 shrink-0" aria-hidden />
                  <span
                    className="relative flex-1 truncate"
                    style={{ paddingLeft: `${(action.indent ?? 0) * 10}px` }}
                  >
                    {action.label}
                  </span>
                  {action.hint ? (
                    <span className="text-muted-foreground relative max-w-[45%] shrink-0 truncate text-[10px]">
                      {action.hint}
                    </span>
                  ) : null}
                  {index === active ? (
                    <CornerDownLeft className="text-muted-foreground relative size-3.5 shrink-0" aria-hidden />
                  ) : null}
                </button>
              </motion.li>
            ))}
          </motion.ul>
        )}
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
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
