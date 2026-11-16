import { useNavigate } from '@tanstack/react-router'

import { useCurrentOrigin } from '@/lib/origin'
import { useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  BarChart3,
  BookOpen,
  Camera,
  ClipboardList,
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
  Sigma,
  Presentation,
  type LucideIcon,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { CommandPalette as CommandPaletteShell } from '@/components/ui/command-palette'
import type { CommandGroup, CommandItem } from '@/components/ui/command-list'
import { createNote, courseTree, generateQuiz, listCourses, listExercises, listNotes, listQuizzes, search, type NodeInfo } from '@/lib/api'
import { useCaptureStore } from '@/lib/capture-store'
import { useImportUrlStore } from '@/lib/import-url-store'
import { fuzzyFilter } from '@/lib/fuzzy'
import { getRecentNodes, resolveRecentNodes } from '@/lib/recent-nodes'
import { useInterfacePrefs } from '@/lib/interface-prefs'
import { useWorkspaceStore } from '@/lib/workspace-store'

interface Action {
  key: string
  label: string
  hint?: string
  icon: LucideIcon
  run: () => void | Promise<void>
}

function toCommandItem(action: Action): CommandItem {
  return {
    id: action.key,
    label: action.label,
    hint: action.hint,
    icon: action.icon,
  }
}

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const from = useCurrentOrigin()
  const queryClient = useQueryClient()
  const courseId = useWorkspaceStore((state) => state.courseId)
  const interfacePrefs = useInterfacePrefs()
  const setCourse = useWorkspaceStore((state) => state.setCourse)
  const [query, setQuery] = useState('')
  const [notice, setNotice] = useState<string | null>(null)
  const keepOpenRef = useRef(false)

  const courses = useQuery({
    queryKey: ['courses'],
    queryFn: listCourses,
    enabled: open,
  })

  const resolveCourseId = useCallback((): string | null => {
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
    const map = new Map<string, NodeInfo[]>()
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
    }
    const nav: Action[] = [
      { key: 'nav-home', label: t('nav.home'), icon: Home, run: go('/') },
      { key: 'nav-chat', label: t('nav.chat'), icon: MessageSquare, run: go('/chat') },
      { key: 'nav-courses', label: t('nav.courses'), icon: GraduationCap, run: go('/courses') },
      { key: 'nav-solve', label: t('nav.solve'), icon: Sigma, run: go('/solve') },
      { key: 'nav-studio', label: t('nav.studio'), icon: Presentation, run: go('/studio') },
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
        },
      },
      {
        key: 'snap-region',
        label: t('capture.snapPaletteAction'),
        icon: Camera,
        run: () => {
          useCaptureStore.getState().openSnap()
        },
      },
      {
        key: 'import-url',
        label: t('importUrl.title'),
        icon: Link2,
        run: () => {
          useImportUrlStore.getState().openImport()
        },
      },
      {
        key: 'new-note',
        label: t('palette.newNote'),
        icon: Plus,
        run: async () => {
          keepOpenRef.current = true
          const noteCourseId = resolveCourseId()
          if (noteCourseId === null) {
            setNotice(t('workspace.openCourseFirst'))
            return
          }
          try {
            const note = await createNote({
              title: t('notes.defaultTitle'),
              course_id: noteCourseId,
            })
            await queryClient.invalidateQueries({ queryKey: ['notes'] })
            void navigate({ to: '/note/$noteId', params: { noteId: note.id } })
            onClose()
          } catch {
            setNotice(t('palette.actionFailed'))
          }
        },
      },
      {
        key: 'open-chat',
        label: t('palette.openChat'),
        icon: MessageSquare,
        run: () => {
          void navigate({ to: '/chat' })
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
                void navigate({ to: '/note/$noteId', params: { noteId: note.id } })
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
              icon: BookOpen,
              run: () => {
                void navigate({
                  to: '/courses/$courseId/n/$nodeId',
                  params: { courseId: String(id), nodeId: String(entry.id) },
                })
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
  }, [treeCourseIds, trees, courses.data, t, navigate])

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
        },
      })
    )
  }, [query, trees, courses.data, navigate, interfacePrefs])

  const contentActions = useMemo<Action[]>(() => {
    if (contentQuery === null) {
      return []
    }
    const contentItems: Action[] = []
    for (const hit of contentSearch.data?.hits.slice(0, 8) ?? []) {
      contentItems.push({
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
        },
      })
      const placement = hit.nodes?.[0]
      if (placement !== undefined && contentItems.length < 12) {
        contentItems.push({
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
          },
        })
      }
    }
    return contentItems
  }, [contentQuery, contentSearch.data, t, navigate])

  const filteredActions = useMemo(() => {
    if (contentQuery !== null) {
      return []
    }
    const actionText = (action: Action) => (action.hint ? `${action.label} ${action.hint}` : action.label)
    return fuzzyFilter(actions, query, actionText)
  }, [actions, contentQuery, query])

  const filteredNodes = useMemo(() => {
    if (contentQuery !== null) {
      return []
    }
    const actionText = (action: Action) => (action.hint ? `${action.label} ${action.hint}` : action.label)
    return fuzzyFilter(nodeActions, query, actionText).slice(0, 40)
  }, [contentQuery, nodeActions, query])

  const actionIndex = useMemo(() => {
    const index = new Map<string, Action>()
    for (const action of [...recentActions, ...filteredActions, ...filteredNodes, ...contentActions]) {
      index.set(action.key, action)
    }
    return index
  }, [contentActions, filteredActions, filteredNodes, recentActions])

  const hasRows =
    contentQuery !== null
      ? contentActions.length > 0
      : recentActions.length + filteredActions.length + filteredNodes.length > 0

  const groups = useMemo<CommandGroup[]>(() => {
    const result: CommandGroup[] = []
    if (notice !== null && hasRows) {
      result.push({
        id: 'notice',
        label: t('palette.group.notice'),
        filter: 'none',
        items: [{ id: 'notice', label: notice, disabled: true }],
      })
    }
    if (contentQuery !== null) {
      if (contentActions.length > 0) {
        result.push({
          id: 'content',
          label: t('palette.group.content'),
          filter: 'none',
          items: contentActions.map(toCommandItem),
        })
      }
      return result
    }
    if (recentActions.length > 0) {
      result.push({
        id: 'recent',
        label: t('palette.group.recent'),
        filter: 'none',
        items: recentActions.map(toCommandItem),
      })
    }
    if (filteredActions.length > 0) {
      result.push({
        id: 'actions',
        label: t('palette.group.actions'),
        filter: 'none',
        items: filteredActions.map(toCommandItem),
      })
    }
    if (filteredNodes.length > 0) {
      result.push({
        id: 'nodes',
        label: t('palette.group.nodes'),
        filter: 'none',
        items: filteredNodes.map(toCommandItem),
      })
    }
    if (hasRows) {
      result.push({
        id: 'hint',
        label: t('palette.group.hint'),
        filter: 'none',
        items: [{ id: 'content-hint', label: t('palette.contentHint'), disabled: true }],
      })
    }
    return result
  }, [
    contentActions,
    contentQuery,
    filteredActions,
    filteredNodes,
    hasRows,
    notice,
    recentActions,
    t,
  ])

  const emptyLabel =
    notice !== null && !hasRows
      ? `${
          contentQuery !== null && contentSearch.isFetching
            ? t('palette.contentSearching')
            : t('palette.noResults')
        } ${notice}`
      : contentQuery !== null && contentSearch.isFetching
        ? t('palette.contentSearching')
        : t('palette.noResults')

  const resultsLabel =
    contentQuery !== null && contentSearch.isFetching
      ? `${t('palette.resultCount')} — ${t('palette.contentSearching')}`
      : notice !== null && hasRows
        ? `${t('palette.resultCount')} — ${notice}`
        : t('palette.resultCount')

  useEffect(() => {
    if (open) {
      setQuery('')
      setNotice(null)
      keepOpenRef.current = false
    }
  }, [open])

  const handleOpenChange = useCallback(
    (next: boolean) => {
      if (next) {
        return
      }
      if (keepOpenRef.current) {
        keepOpenRef.current = false
        return
      }
      onClose()
    },
    [onClose],
  )

  const handleSelect = useCallback(
    (item: CommandItem) => {
      keepOpenRef.current = false
      const action = actionIndex.get(item.id)
      if (action !== undefined) {
        void action.run()
      }
    },
    [actionIndex],
  )

  return (
    <CommandPaletteShell
      open={open}
      onOpenChange={handleOpenChange}
      query={query}
      onQueryChange={setQuery}
      groups={groups}
      onSelect={handleSelect}
      labels={{
        placeholder: t('palette.placeholder'),
        empty: emptyLabel,
        results: resultsLabel,
        listLabel: t('palette.searchLabel'),
      }}
      ariaLabel={t('palette.title')}
      closeLabel={t('common.close')}
    />
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
