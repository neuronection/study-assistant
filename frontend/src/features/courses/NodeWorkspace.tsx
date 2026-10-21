import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'
import {Link, useNavigate, useSearch} from '@tanstack/react-router'
import {ChevronRight, Layers, Loader2, MessageSquare, Sparkles} from 'lucide-react'
import {useEffect, useMemo, useState} from 'react'
import {useTranslation} from 'react-i18next'
import {Button} from '@/components/ui/button'
import {Skeleton} from '@/components/ui/skeleton'
import {ErrorBanner} from '@/components/ErrorBanner'
import {MaterialBrowserSkeleton} from '@/components/materials/MaterialBrowser'
import {StudyLauncherDialog} from '@/features/ai/StudyLauncherDialog'
import {SplitStudyPane} from '@/features/library/SplitStudyPane'
import {PlannerTab} from '@/features/planner/PlannerTab'
import {useCurrentOrigin} from '@/lib/origin'
import {courseTree, createChatSession, generateQuiz, getCourse, nodeWorkspace} from '@/lib/api'
import {useChatStore} from '@/lib/chat-store'
import {recordRecentNode} from '@/lib/recent-nodes'
import {SegmentedControl} from '@/components/motion/SegmentedControl'
import {cn} from '@/lib/utils'
import {CourseSettingsTab} from './CourseSettingsTab'
import {NodeSettingsMenu} from './NodeSettingsMenu'
import {NodeTreeSidebar} from './NodeTreeSidebar'
import {PracticeTab} from '@/features/practice/PracticeTab'

import { CoverageTab } from './workspace/CoverageTab'
import { MaterialsTab } from './workspace/MaterialsTab'
import { NotesTab } from './workspace/NotesTab'
import { OverviewTab } from './workspace/OverviewTab'
import { TutorTab } from './workspace/TutorTab'

import {
  TAB_META,
  TABS,
  buildTitleMap,
  findNodeCounts,
  parseTab,
  tabCount,
  type WorkspaceTab,
} from './workspace/tabs'
import { useWorkspaceNavigation } from './workspace/navigation'
function useWorkspaceQuery(nodeId: string | undefined) {
  return useQuery({
    queryKey: ['node-workspace', nodeId !== undefined ? String(nodeId) : 'pending'],
    queryFn: () => nodeWorkspace(nodeId!),
    enabled: nodeId !== undefined,
  })
}

export function NodeWorkspace({ courseId, nodeId }: { courseId: string; nodeId?: string }) {
  const { t } = useTranslation()
  const search = useSearch({ strict: false }) as {
    tab?: string
    note?: string
    material?: string
    study?: string
    folder?: string
  }
  const navigate = useNavigate()
  const from = useCurrentOrigin()
  const queryClient = useQueryClient()
  const parsedTab = parseTab(search.tab)

  const tree = useQuery({
    queryKey: ['tree', courseId],
    queryFn: () => courseTree(courseId),
  })
  const courseQuery = useQuery({
    queryKey: ['course', courseId],
    queryFn: () => getCourse(courseId),
  })
  const rootId = tree.data?.[0]?.id
  const currentId = nodeId !== undefined ? nodeId : rootId
  const workspace = useWorkspaceQuery(currentId)
  const currentNodeCounts = useMemo(
    () => (currentId !== undefined ? findNodeCounts(tree.data ?? [], currentId) : undefined),
    [tree.data, currentId]
  )
  const dueCards = currentNodeCounts?.cards_due

  useEffect(() => {
    if (currentId !== undefined) {
      recordRecentNode(courseId, currentId)
    }
  }, [courseId, currentId])

  const studyHere = useMutation({
    mutationFn: (targetId: string) =>
      generateQuiz({ course_id: courseId, node_id: targetId, count: 8 }),
    onSuccess: async (activity) => {
      await queryClient.invalidateQueries({ queryKey: ['quizzes'] })
      void navigate({ to: '/quiz/$activityId', params: { activityId: String(activity.id) }, search: { from } })
    },
  })
  const [launcherNode, setLauncherNode] = useState<string | null>(null)
  const openChatSession = useChatStore((state) => state.openSession)
  const askAbout = useMutation({
    mutationFn: ({ targetId, title }: { targetId: string; title: string }) =>
      createChatSession(courseId, targetId, title),
    onSuccess: async (session) => {
      await queryClient.invalidateQueries({ queryKey: ['chat-sessions'] })
      openChatSession({ id: session.id, publicId: session.public_id })
    },
  })
  const studyTargetId = studyHere.isPending ? (studyHere.variables ?? null) : null
  const askTargetId = askAbout.isPending ? (askAbout.variables?.targetId ?? null) : null

  const {
    setTab,
    openNoteAt,
    openMaterialAt,
    openFolderInView,
    closeFolderView,
    studyNoteCreated,
    closeStudy,
    closeNotes,
  } = useWorkspaceNavigation(courseId, nodeId)
  const onNoteCreated = async (noteId: string) => {
    await queryClient.invalidateQueries({ queryKey: ['notes'] })
    openNoteAt(noteId)
  }

  if (
    (nodeId === undefined && tree.isLoading) ||
    (currentId !== undefined && workspace.isLoading)
  ) {
    return (
      <div className="mx-auto max-w-6xl space-y-6 p-8" aria-busy="true">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-3.5 w-96" />
        <div className="flex gap-2">
          <Skeleton className="h-8 w-24" />
          <Skeleton className="h-8 w-24" />
          <Skeleton className="h-8 w-24" />
        </div>
        <MaterialBrowserSkeleton view="grid" count={8} />
      </div>
    )
  }
  if (currentId === undefined || workspace.isError || !workspace.data) {
    return <p className="text-muted-foreground p-8 text-sm">{t('chapter.missing')}</p>
  }

  const data = workspace.data
  const node = data.node
  const course = courseQuery.data ?? null
  const titles = buildTitleMap(tree.data ?? [])
  const effectiveTab: WorkspaceTab =
    !node.is_root && (parsedTab.tab === 'settings' || parsedTab.tab === 'planner')
      ? 'overview'
      : parsedTab.tab

  return (
    <>
      <div className="flex min-h-full items-start">
        <NodeTreeSidebar
          courseId={courseId}
          currentId={currentId}
          tab={effectiveTab}
          courseOrigin={courseQuery.data?.origin ?? null}
        />
        <div className="mx-auto flex min-w-0 max-w-5xl flex-1 flex-col space-y-4 self-stretch p-8">
      <header className="flex flex-wrap items-center gap-x-2 gap-y-2">
        <nav
          className="text-muted-foreground flex min-w-0 flex-1 items-center gap-1.5 text-xs"
          aria-label={t('workspace.breadcrumb')}
        >
          {node.breadcrumb.map((crumb, index) => {
            const last = index === node.breadcrumb.length - 1
            if (last) {
              return (
                <span
                  key={crumb.id}
                  className="flex min-w-0 items-center gap-2"
                  aria-current="page"
                >
                  {index > 0 ? (
                    <ChevronRight className="size-3 shrink-0" aria-hidden />
                  ) : null}
                  {course?.color ? (
                    <span
                      className="size-2.5 shrink-0 rounded-full"
                      style={{ backgroundColor: course.color }}
                      aria-hidden
                    />
                  ) : null}
                  <h1 className="text-foreground truncate text-xl font-bold tracking-tight">
                    {crumb.title}
                  </h1>
                </span>
              )
            }
            return (
              <span key={crumb.id} className="flex min-w-0 items-center gap-1.5">
                {index > 0 ? (
                  <ChevronRight className="size-3 shrink-0" aria-hidden />
                ) : null}
                {crumb.depth === 0 ? (
                  <Link
                    to="/courses/$courseId"
                    params={{ courseId }}
                    className="hover:text-foreground truncate hover:underline"
                  >
                    {crumb.title}
                  </Link>
                ) : (
                  <Link
                    to="/courses/$courseId/n/$nodeId"
                    params={{ courseId, nodeId: String(crumb.id) }}
                    className="hover:text-foreground truncate hover:underline"
                  >
                    {crumb.title}
                  </Link>
                )}
              </span>
            )
          })}
        </nav>
        <div className="ml-auto flex shrink-0 items-center gap-2">
          <NodeSettingsMenu
            courseId={courseId}
            examDate={courseQuery.data?.exam_date ?? null}
            node={{
              id: node.id,
              title: node.title,
              summary: node.summary,
              ai_hint: node.ai_hint,
              is_root: node.is_root,
            }}
          />
          <Button size="sm" onClick={() => setLauncherNode(currentId)}>
            <Sparkles aria-hidden />
            {t('workspace.studyHere')}
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={askAbout.isPending}
            onClick={() => askAbout.mutate({ targetId: currentId, title: node.title })}
          >
            {askTargetId === currentId ? (
              <Loader2 className="animate-spin" aria-hidden />
            ) : (
              <MessageSquare aria-hidden />
            )}
            {t('workspace.askAbout')}
          </Button>
        </div>
      </header>

      <ErrorBanner
        message={studyHere.isError ? (studyHere.error as Error).message : null}
      />
      <ErrorBanner
        message={askAbout.isError ? (askAbout.error as Error).message : null}
      />

      <SegmentedControl
        variant="underline"
        items={TABS.filter(
          (entry) => node.is_root || (entry !== 'settings' && entry !== 'planner'),
        ).map((entry) => {
          const meta = TAB_META[entry]
          const count = tabCount(entry, currentNodeCounts)
          return {
            value: entry,
            label: t(`workspace.tab_${entry}`),
            icon: meta.icon,
            ariaCurrent: true,
            badge:
              count !== null && count > 0 ? (
                <span
                  className={cn(
                    'rounded-full px-1.5 text-[10px] leading-4',
                    effectiveTab === entry ? 'bg-primary/10 text-primary' : 'bg-subtle',
                  )}
                >
                  {count}
                </span>
              ) : entry === 'practice' && dueCards !== undefined && dueCards > 0 ? (
                <span
                  className="bg-warning/15 text-warning rounded-full px-1.5 py-0.5 text-[10px]"
                  title={t('workspace.treeDue', { count: dueCards })}
                >
                  <Layers className="size-3" aria-hidden />
                  {dueCards}
                </span>
              ) : null,
          }
        })}
        value={effectiveTab}
        onChange={(next) => setTab(next as WorkspaceTab)}
      />

      {effectiveTab === 'overview' ? (
        <OverviewTab
          courseId={courseId}
          currentId={currentId}
          isRoot={node.is_root}
          workspace={data}
          tree={tree.data}
          onPractice={(targetId) => studyHere.mutate(targetId)}
          onAsk={(child) => askAbout.mutate({ targetId: child.id, title: child.title })}
          studyTargetId={studyTargetId}
          askTargetId={askTargetId}
          onOpenMaterial={openMaterialAt}
          onGoToMaterials={() => setTab('materials')}
          onStudyLauncher={() => setLauncherNode(currentId)}
          onAskHere={() => askAbout.mutate({ targetId: currentId, title: node.title })}
        />
      ) : null}
      {effectiveTab === 'materials' ? (
        <MaterialsTab
          courseId={courseId}
          currentId={currentId}
          workspace={data}
          folderId={search.folder ?? null}
          onOpenMaterial={openMaterialAt}
          onOpenFolder={openFolderInView}
          onCloseFolder={closeFolderView}
        />
      ) : null}
      {effectiveTab === 'notes' ? (
        <NotesTab
          courseId={courseId}
          currentId={currentId}
          titles={titles}
          onOpenNote={openNoteAt}
        />
      ) : null}
      {effectiveTab === 'concepts' ? (
        <CoverageTab
          courseId={courseId}
          currentId={currentId}
          workspace={data}
          titles={titles}
        />
      ) : null}
      {effectiveTab === 'practice' && rootId !== undefined ? (
        <PracticeTab
          courseId={courseId}
          currentId={currentId}
          rootId={rootId}
          titles={titles}
          initialSegment={parsedTab.cardsSegment ? 'flashcards' : undefined}
        />
      ) : null}
      {effectiveTab === 'tutor' ? (
        <TutorTab
          currentId={currentId}
          nodeTitle={node.title}
          onAsk={(targetId, title) => askAbout.mutate({ targetId, title })}
          askPending={askTargetId === currentId}
        />
      ) : null}
      {effectiveTab === 'planner' && node.is_root ? (
        <PlannerTab courseId={courseId} />
      ) : null}
      {effectiveTab === 'settings' && node.is_root && course !== null ? (
        <CourseSettingsTab courseId={courseId} course={course} />
      ) : null}
        </div>
      </div>
      {search.material !== undefined && search.study !== undefined ? (
        <SplitStudyPane
          courseId={courseId}
          materialId={search.material}
          study={search.study}
          onNoteCreated={studyNoteCreated}
          onClose={closeStudy}
          onCloseNotes={closeNotes}
        />
      ) : null}
      {launcherNode !== null && rootId !== undefined ? (
        <StudyLauncherDialog
          courseId={courseId}
          nodeId={launcherNode}
          rootNodeId={rootId}
          onClose={() => setLauncherNode(null)}
          onNoteCreated={onNoteCreated}
        />
      ) : null}
    </>
  )
}
