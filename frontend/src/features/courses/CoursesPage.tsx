import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { BookOpen, Download, GraduationCap, History, Loader2, Plus, Trash2, Upload } from 'lucide-react'
import { useRef, useState, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from '@tanstack/react-router'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { ExpandableSearch } from '@/components/ui/ExpandableSearch'
import { fuzzyScore } from '@/lib/fuzzy'
import { formatRelativeTime } from '@/lib/format'
import { useInterfacePrefs } from '@/lib/interface-prefs'
import {
  courseExportUrl,
  courseTree,
  createCourse,
  deleteCourse,
  importCourseBundle,
  listCourses,
  type CourseBundlePreview,
  type NodeInfo,
} from '@/lib/api'
import {
  getRecentNodes,
  resolveRecentNodes,
  type ResolvedRecentNode,
} from '@/lib/recent-nodes'
import { useConfirm } from '@/lib/use-confirm'

export function CoursesPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const courses = useQuery({ queryKey: ['courses'], queryFn: listCourses })
  const { courseCardMeta } = useInterfacePrefs()
  const [creating, setCreating] = useState(false)
  const [title, setTitle] = useState('')
  const [subject, setSubject] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [importPreview, setImportPreview] = useState<CourseBundlePreview | null>(null)

  const lastVisitByCourse = useMemo(() => {
    const map = new Map<number, { nodeId: number; at: number }>()
    for (const entry of getRecentNodes()) {
      if (!map.has(entry.courseId)) {
        map.set(entry.courseId, { nodeId: entry.nodeId, at: entry.at })
      }
    }
    return map
  }, [])
  const recentCourseIds = useMemo(
    () =>
      (courses.data ?? [])
        .filter((course) => lastVisitByCourse.has(course.id))
        .map((course) => course.id),
    [courses.data, lastVisitByCourse]
  )
  const recentTreeQueries = useQueries({
    queries: recentCourseIds.map((id) => ({
      queryKey: ['tree', String(id)],
      queryFn: () => courseTree(id),
    })),
  })
  const lastVisitRows = useMemo(() => {
    if (!courseCardMeta) {
      return new Map<number, ResolvedRecentNode>()
    }
    const trees = new Map<number, NodeInfo[] | undefined>()
    recentCourseIds.forEach((id, index) => {
      trees.set(id, recentTreeQueries[index]?.data)
    })
    const titles = new Map(
      (courses.data ?? []).map((course) => [course.id, course.title])
    )
    const rows = new Map<number, ResolvedRecentNode>()
    for (const [courseId, entry] of lastVisitByCourse) {
      const resolved = resolveRecentNodes(
        [{ courseId, nodeId: entry.nodeId, at: entry.at }],
        trees,
        titles
      )[0]
      if (resolved !== undefined) {
        rows.set(courseId, resolved)
      }
    }
    return rows
  }, [recentCourseIds, recentTreeQueries, lastVisitByCourse, courses.data, courseCardMeta])
  const [importFile, setImportFile] = useState<File | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const importInput = useRef<HTMLInputElement>(null)
  const [confirm, confirmElement] = useConfirm()

  const normalizedQuery = searchQuery.trim()
  const visibleCourses = useMemo(() => {
    const all = courses.data ?? []
    if (!normalizedQuery) {
      return all
    }
    return all.filter((course) =>
      [course.title, course.subject, course.description].some(
        (field) => fuzzyScore(normalizedQuery, field ?? '') !== null
      )
    )
  }, [courses.data, normalizedQuery])

  const create = useMutation({
    mutationFn: () => createCourse({ title: title.trim(), subject: subject.trim() || null }),
    onSuccess: async () => {
      setCreating(false)
      setTitle('')
      setSubject('')
      await queryClient.invalidateQueries({ queryKey: ['courses'] })
    },
    onError: (err: Error) => setError(err.message),
  })

  const remove = useMutation({
    mutationFn: (id: number) => deleteCourse(id, true),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['courses'] }),
  })

  const startImport = useMutation({
    mutationFn: (file: File) => importCourseBundle(file, true),
    onSuccess: (result) => {
      setError(null)
      if (result.dry_run) {
        setImportPreview(result.preview)
      }
    },
    onError: (err: Error) => setError(err.message),
  })

  const commitImport = useMutation({
    mutationFn: (file: File) => importCourseBundle(file, false),
    onSuccess: async (result) => {
      setImportPreview(null)
      setImportFile(null)
      await queryClient.invalidateQueries({ queryKey: ['courses'] })
      if (!result.dry_run) {
        void navigate({
          to: '/courses/$courseId',
          params: { courseId: String(result.imported.course_id) },
        })
      }
    },
    onError: (err: Error) => setError(err.message),
  })

  return (
    <div className="mx-auto max-w-4xl p-8">
      <header className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{t('courses.title')}</h1>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => importInput.current?.click()}>
            <Upload aria-hidden />
            {t('courses.importBundle')}
          </Button>
          <Button size="sm" onClick={() => setCreating(true)}>
            <Plus aria-hidden />
            {t('courses.new')}
          </Button>
        </div>
      </header>

      <input
        ref={importInput}
        type="file"
        accept=".zip"
        aria-label={t('courses.importBundle')}
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0]
          if (file) {
            setImportFile(file)
            startImport.mutate(file)
          }
          event.target.value = ''
        }}
      />

      {importPreview !== null ? (
        <Card className="mb-6">
          <CardContent className="space-y-3 p-4">
            <p className="text-sm font-medium">
              {t('courses.importPreviewTitle', { title: importPreview.title ?? '?' })}
            </p>
            <p className="text-muted-foreground text-xs">
              {t('courses.importPreviewCounts', {
                materials: importPreview.counts.materials ?? 0,
                notes: importPreview.counts.notes ?? 0,
                quizzes: importPreview.counts.quizzes ?? 0,
                exercises: importPreview.counts.exercises ?? 0,
              })}
            </p>
            {importPreview.warnings.length > 0 ? (
              <ul className="text-warning list-disc pl-4 text-xs">
                {importPreview.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            ) : null}
            {error ? <p className="text-danger text-xs">{error}</p> : null}
            <div className="flex justify-end gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setImportPreview(null)
                  setImportFile(null)
                  setError(null)
                }}
              >
                {t('settings.cancel')}
              </Button>
              <Button
                size="sm"
                disabled={commitImport.isPending || importFile === null}
                onClick={() => {
                  if (importFile !== null) {
                    commitImport.mutate(importFile)
                  }
                }}
              >
                {commitImport.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
                {t('courses.importConfirm')}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {importPreview === null && error ? (
        <p className="text-danger mb-4 text-xs">{error}</p>
      ) : null}

      {creating ? (
        <Card className="mb-6">
          <CardContent className="flex flex-col gap-3 p-4">
            <input
              autoFocus
              className="bg-surface border-border rounded-md border px-3 py-2 text-sm"
              placeholder={t('courses.titlePlaceholder')}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
            />
            <input
              className="bg-surface border-border rounded-md border px-3 py-2 text-sm"
              placeholder={t('courses.subjectPlaceholder')}
              value={subject}
              onChange={(event) => setSubject(event.target.value)}
            />
            {error ? <p className="text-danger text-xs">{error}</p> : null}
            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={() => setCreating(false)}>
                {t('settings.cancel')}
              </Button>
              <Button size="sm" disabled={!title.trim() || create.isPending} onClick={() => create.mutate()}>
                {create.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
                {t('settings.add')}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {courses.isLoading ? (
        <Loader2 className="animate-spin" aria-label={t('library.loading')} />
      ) : null}

      {courses.data && courses.data.length > 0 ? (
        <div className="mb-4 flex justify-end">
          <ExpandableSearch
            value={searchQuery}
            onChange={setSearchQuery}
            placeholder={t('courses.searchPlaceholder')}
            ariaLabel={t('courses.searchPlaceholder')}
            clearLabel={t('common.clearSearch')}
          />
        </div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2">
        {visibleCourses.map((course) => (
          <Card key={course.id}>
            <CardContent className="flex items-start gap-3 p-5">
              <span
                className="mt-1 inline-flex size-9 items-center justify-center rounded-lg"
                style={{ backgroundColor: `${course.color ?? '#6366f1'}22`, color: course.color ?? '#6366f1' }}
              >
                <GraduationCap className="size-5" aria-hidden />
              </span>
              <div className="min-w-0 flex-1">
                <Link
                  to="/courses/$courseId"
                  params={{ courseId: String(course.id) }}
                  className="block truncate text-sm font-medium hover:underline"
                >
                  {course.title}
                </Link>
                <p className="text-muted-foreground text-xs">
                  {course.subject ?? t('courses.noSubject')} · {t('courses.materialCount', {
                    count: course.material_count,
                  })}
                </p>
                {lastVisitRows.get(course.id) ? (
                  <button
                    type="button"
                    className="text-primary hover:text-primary/80 mt-1 flex max-w-full items-center gap-1 rounded text-xs"
                    title={lastVisitRows.get(course.id)!.breadcrumb}
                    onClick={() => {
                      const lastVisit = lastVisitRows.get(course.id)!
                      void navigate({
                        to: '/courses/$courseId/n/$nodeId',
                        params: {
                          courseId: String(course.id),
                          nodeId: String(lastVisit.nodeId),
                        },
                      })
                    }}
                  >
                    <History className="size-3 shrink-0" aria-hidden />
                    <span className="truncate">{lastVisitRows.get(course.id)!.title}</span>
                    <span className="text-muted-foreground shrink-0 text-[10px]">
                      · {formatRelativeTime(lastVisitRows.get(course.id)!.at)}
                    </span>
                  </button>
                ) : null}
                {course.description ? (
                  <p className="text-muted-foreground mt-1 line-clamp-2 text-xs" title={course.description}>
                    {course.description}
                  </p>
                ) : null}
              </div>
              <div className="flex gap-1">
                <a
                  href={courseExportUrl(course.id)}
                  download
                  title={t('courses.exportBundle')}
                  className="text-muted-foreground hover:bg-subtle hover:text-foreground inline-flex size-9 items-center justify-center rounded-md"
                >
                  <Download className="size-4" aria-hidden />
                </a>
                <Button
                  variant="ghost"
                  size="icon"
                  title={t('courses.delete')}
                  onClick={async () => {
                    const ok = await confirm({
                      title: t('courses.delete'),
                      description: t('courses.confirmDelete'),
                      confirmLabel: t('courses.delete'),
                      cancelLabel: t('common.cancel'),
                      destructive: true,
                    })
                    if (ok) remove.mutate(course.id)
                  }}
                >
                  <Trash2 className="size-4" aria-hidden />
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {courses.data && courses.data.length === 0 && !creating ? (
        <div className="text-muted-foreground py-16 text-center">
          <BookOpen className="mx-auto mb-3 size-10" aria-hidden />
          <p className="text-sm">{t('courses.empty')}</p>
        </div>
      ) : null}

      {courses.data && courses.data.length > 0 && visibleCourses.length === 0 ? (
        <p className="text-muted-foreground py-16 text-center text-sm">{t('courses.noMatch')}</p>
      ) : null}
      {confirmElement}
    </div>
  )
}
