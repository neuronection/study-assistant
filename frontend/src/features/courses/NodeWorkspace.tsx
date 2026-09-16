import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useSearch } from '@tanstack/react-router'
import {
  BookOpen,
  CalendarClock,
  ChevronRight,
  ClipboardList,
  Dumbbell,
  ExternalLink,
  FolderClosed,
  GitBranch,
  Layers,
  LayoutDashboard,
  Loader2,
  MessageSquare,
  NotebookPen,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  ScrollText,
  Settings,
  Sparkles,
  Upload,
  X,
} from 'lucide-react'
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { useTranslation } from 'react-i18next'

import { BlockRenderer } from '@/components/blocks/BlockRenderer'
import type { Block } from '@/components/blocks/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import {
  ContextMenu,
  type ContextMenuItem,
} from '@/components/ui/ContextMenu'
import { ErrorBanner } from '@/components/ErrorBanner'
import { AssignToNodeDialog } from './AssignToNodeDialog'
import { RenameDialog } from '@/components/RenameDialog'
import { EmptyState } from '@/components/ui/empty-state'
import { ExpandableSearch } from '@/components/ui/ExpandableSearch'
import { ViewToggle } from '@/components/ui/ViewToggle'
import { useStoredView } from '@/lib/useStoredView'
import { EntityItems, type EntityItemEntry } from '@/components/entity-list/EntityItems'
import { TabActionBar, type TabAction } from '@/components/layout/TabActionBar'
import { type PopoverMenuItem } from '@/components/ui/popover-menu'
import { UndoDeleteNotice } from '@/components/UndoDeleteNotice'
import { isKeyboardClick, useSelection } from '@/lib/useSelection'
import { MaterialBrowser, MaterialBrowserSkeleton, type MaterialFolderSpec } from '@/components/materials/MaterialBrowser'
import { type Crumb } from '@/features/library/LibraryBreadcrumbs'
import { KindIcon } from '@/features/library/KindIcon'
import { MaterialRow } from '@/components/materials/MaterialRow'
import { MaterialTile } from '@/components/materials/MaterialTile'
import { MaterialUploadDropzone } from '@/components/materials/MaterialUploadDropzone'
import { ReExtractDialog } from '@/components/materials/ReExtractDialog'
import { DiscoverDialog } from '@/features/discovery/DiscoverDialog'
import { useMaterialUpload } from '@/components/materials/materialUpload'
import { useWindowDropRegistration } from '@/lib/window-drop-store'
import { useImportUrlStore } from '@/lib/import-url-store'
import { useCreateMaterialMenu } from '@/components/materials/createMaterialMenu'
import { NewFolderDialog } from '@/components/materials/NewFolderDialog'
import {
  NewTextFileDialog,
  type TextFileCreateInput,
  type TextFileSaveInput,
} from '@/features/library/NewTextFileDialog'
import { MarqueeSurface } from '@/components/ui/Marquee'
import { GenerateDialog as AIGenerateDialog } from '@/features/ai/GenerateDialog'
import { StudyLauncherDialog } from '@/features/ai/StudyLauncherDialog'
import { NoteEditorDrawer, closeNote, openNote } from '@/features/notes/NoteEditorDrawer'
import { SplitStudyPane } from '@/features/library/SplitStudyPane'
import { PlannerTab } from '@/features/planner/PlannerTab'
import { MaterialDetailDrawer } from '@/features/library/MaterialDetailDrawer'
import { useCurrentOrigin } from '@/lib/origin'
import { fuzzyFilter } from '@/lib/fuzzy'
import { useConfirm } from '@/lib/use-confirm'
import {
  addNode,
  addNodeConcept,
  allocateMaterial,
  allocateNodeFolder,
  browseSource,
  conceptGraph,
  courseTree,
  createChatSession,
  createFolder,
  createNote,
  createTextMaterial,
  deallocateMaterial,
  deallocateNodeFolder,
  deriveMaterials,
  ingestSourceFile,
  moveNote,
  deleteNote,
  draftNodeNote,
  extractConcepts,
  generateQuiz,
  getCourse,
  getMaterial,
  getNodeArtifacts,
  getPlacementSuggestions,
  getUnassignedMaterials,
  mirrorFolder as mirrorFolderApi,
   listChatSessions,
   listFolders,
   listMaterials,
   listNoteTags,
  listNotes,
  nodeWorkspace,
  outlineCommit,
  outlineDraft,
  removeNodeConcept,
  reviewNode,
  updateNote,
   type ComposeKind,
   type ConceptDraft,
   type Folder,
   type Material,
  type NodeCounts,
  type NodeInfo,
  type OrganizerFinding,
  type OutlineDraftChapter,
  type WorkspaceChild,
  type WorkspaceFolder,
  type WorkspaceMaterial,
  type PlacementSuggestion,
  type TextFileEditState,
  updateTextMaterial,
 } from '@/lib/api'
import { useChatStore } from '@/lib/chat-store'
import { formatDate } from '@/lib/format'
import { SegmentedControl } from '@/components/motion/SegmentedControl'
import { cn } from '@/lib/utils'
import { buildDragPayload } from '@/lib/dragPayload'

import { ConceptsPanel } from './ConceptsPanel'
import { CourseSettingsTab } from './CourseSettingsTab'
import { MaterialPickerDialog } from './MaterialPickerDialog'
import { NodeSettingsMenu } from './NodeSettingsMenu'
import { NodeTreeSidebar } from './NodeTreeSidebar'
import { PracticeTab } from '@/features/practice/PracticeTab'
import { storageKeys } from '@/lib/constants'

const TABS = [
  'overview',
  'materials',
  'notes',
  'concepts',
  'practice',
  'planner',
  'tutor',
  'settings',
] as const

type WorkspaceTab = (typeof TABS)[number]

function parseTab(
  value: string | undefined
): { tab: WorkspaceTab; cardsSegment?: boolean } {
  if (value === 'cards') {
    return { tab: 'practice', cardsSegment: true }
  }
  if (value !== undefined && (TABS as readonly string[]).includes(value)) {
    return { tab: value as WorkspaceTab }
  }
  return { tab: 'overview' }
}

const TAB_META: Record<WorkspaceTab, { icon: typeof LayoutDashboard }> = {
  overview: { icon: LayoutDashboard },
  materials: { icon: FolderClosed },
  notes: { icon: NotebookPen },
  concepts: { icon: GitBranch },
  practice: { icon: Dumbbell },
  planner: { icon: CalendarClock },
  tutor: { icon: MessageSquare },
  settings: { icon: Settings },
}

function findNodeCounts(nodes: NodeInfo[], nodeId: number): NodeCounts | undefined {
  const walk = (entries: NodeInfo[]): NodeCounts | undefined => {
    for (const entry of entries) {
      if (entry.id === nodeId) {
        return entry.counts
      }
      const found = walk(entry.children)
      if (found !== undefined) {
        return found
      }
    }
    return undefined
  }
  return walk(nodes)
}

function tabCount(tab: WorkspaceTab, counts: NodeCounts | undefined): number | null {
  if (counts === undefined) {
    return null
  }
  switch (tab) {
    case 'materials':
      return counts.materials
    case 'notes':
      return counts.notes
    case 'practice':
      return counts.quizzes + counts.exercises
    default:
      return null
  }
}

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

function buildTitleMap(nodes: { id: number; title: string; children: unknown[] }[]): Map<number, string> {
  const map = new Map<number, string>()
  const walk = (entries: { id: number; title: string; children: unknown[] }[]) => {
    for (const entry of entries) {
      map.set(entry.id, entry.title)
      walk(entry.children as { id: number; title: string; children: unknown[] }[])
    }
  }
  walk(nodes)
  return map
}

function WorkspaceMaterialRow({
  entry,
  onUnassign,
  unassignTitle,
  onOpen,
  onContextMenu,
  selectionState,
  onPointerDown,
  onDragStart,
}: {
  entry: WorkspaceMaterial
  onUnassign?: (materialId: number) => void
  unassignTitle?: string
  onOpen: (materialId: number, event: React.MouseEvent<Element>) => void
  onContextMenu?: (event: React.MouseEvent<HTMLDivElement>) => void
  selectionState?: 'none' | 'selected' | 'cut'
  onPointerDown?: (event: React.MouseEvent<HTMLDivElement>) => void
  onDragStart?: (event: React.DragEvent<HTMLDivElement>) => void
}) {
  const { t } = useTranslation()
  const viaBadge = entry.via_folder_name ? (
    <span
      className="bg-subtle text-muted-foreground flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[10px]"
      title={t('workspace.viaFolderTitle', { name: entry.via_folder_name })}
    >
      <FolderClosed className="size-3" aria-hidden />
      {entry.via_folder_name}
    </span>
  ) : null
  return (
    <MaterialRow
      material={{
        id: entry.material_id,
        title: entry.title,
        kind: entry.kind,
        aiComposed: entry.provenance?.source === 'ai-composed',
        readStatus: entry.read_status,
        progress: entry.progress,
        rationale: entry.rationale ?? undefined,
      }}
      className="group"
      draggable
      onDragStart={onDragStart}
      title={t('workspace.materialDragHint')}
      selectionState={selectionState}
      onMouseDown={onPointerDown}
      onOpen={(event) => onOpen(entry.material_id, event)}      onContextMenu={onContextMenu}
      action={
        <>
          {viaBadge}
          {onUnassign ? (
            <button
              type="button"
              className="text-muted-foreground hidden shrink-0 group-hover:block"
              title={unassignTitle ?? t('courses.deallocate')}
              onClick={() => onUnassign(entry.material_id)}
            >
              <X className="size-3.5" aria-hidden />
            </button>
          ) : null}
        </>
      }
    />
  )
}

function ChildCard({
  courseId,
  child,
  materialCount,
  studyTargetId,
  askTargetId,
  onPractice,
  onAsk,
}: {
  courseId: string
  child: WorkspaceChild
  materialCount: number
  studyTargetId: number | null
  askTargetId: number | null
  onPractice: (childId: number) => void
  onAsk: (child: WorkspaceChild) => void
}) {
  const { t } = useTranslation()
  const practicePending = studyTargetId === child.id
  const askPending = askTargetId === child.id
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Link
            to="/courses/$courseId/n/$nodeId"
            params={{ courseId, nodeId: String(child.id) }}
            className="truncate hover:underline"
          >
            {child.title}
          </Link>
        </CardTitle>
        <p className="text-muted-foreground text-xs">
          {t('workspace.objectiveCount', { count: child.objectives.length })} ·{' '}
          {t('workspace.materialCount', { count: materialCount })}
        </p>
        {child.summary ? (
          <p className="text-muted-foreground mt-1 line-clamp-2 text-xs" title={child.summary}>
            {child.summary}
          </p>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" asChild>
          <Link to="/courses/$courseId/n/$nodeId" params={{ courseId, nodeId: String(child.id) }}>
            <BookOpen aria-hidden />
            {t('workspace.open')}
          </Link>
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={studyTargetId !== null}
          onClick={() => onPractice(child.id)}
        >
          {practicePending ? <Loader2 className="animate-spin" aria-hidden /> : <Sparkles aria-hidden />}
          {t('workspace.quickPractice')}
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={askTargetId !== null}
          onClick={() => onAsk(child)}
        >
          {askPending ? <Loader2 className="animate-spin" aria-hidden /> : <MessageSquare aria-hidden />}
          {t('workspace.askChild')}
        </Button>
      </CardContent>
    </Card>
  )
}

function OutlineDraftView({
  courseId,
  draft,
  onDone,
}: {
  courseId: string
  draft: { chapters: OutlineDraftChapter[] }
  onDone: () => void
}) {
  const { t } = useTranslation()
  const [chapters, setChapters] = useState<OutlineDraftChapter[]>(draft.chapters)
  const commit = useMutation({
    mutationFn: () => outlineCommit(Number(courseId), chapters),
    onSuccess: () => onDone(),
  })

  const removeChapter = (index: number) =>
    setChapters(chapters.filter((_, i) => i !== index))
  const removeSection = (chapterIndex: number, sectionIndex: number) =>
    setChapters(
      chapters.map((chapter, i) =>
        i === chapterIndex
          ? { ...chapter, sections: chapter.sections.filter((_, j) => j !== sectionIndex) }
          : chapter
      )
    )

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Sparkles className="size-4" aria-hidden />
          {t('courses.outlineDraftTitle')}
        </CardTitle>
        <p className="text-muted-foreground text-xs">{t('courses.outlineDraftHint')}</p>
      </CardHeader>
      <CardContent className="space-y-3">
        {commit.isError ? (
          <p className="text-danger text-xs">{(commit.error as Error).message}</p>
        ) : null}
        {chapters.map((chapter, chapterIndex) => (
          <div key={chapterIndex} className="border-border rounded-lg border p-3">
            <div className="mb-2 flex items-center gap-2">
              <span className="flex-1 text-sm font-semibold">{chapter.title}</span>
              <button
                type="button"
                className="text-muted-foreground hover:text-danger"
                aria-label={t('common.remove')}
                onClick={() => removeChapter(chapterIndex)}
              >
                <X className="size-4" aria-hidden />
              </button>
            </div>
            {chapter.summary ? (
              <p className="text-muted-foreground mb-2 text-xs">{chapter.summary}</p>
            ) : null}
            <div className="space-y-1">
              {chapter.sections.map((section, sectionIndex) => (
                <div key={sectionIndex} className="bg-subtle rounded-md px-2 py-1.5 text-xs">
                  <div className="flex items-center gap-2">
                    <span className="flex-1 truncate font-medium">{section.title}</span>
                    <button
                      type="button"
                      className="text-muted-foreground hover:text-danger"
                      aria-label={t('common.remove')}
                      onClick={() => removeSection(chapterIndex, sectionIndex)}
                    >
                      <X className="size-3" aria-hidden />
                    </button>
                  </div>
                  {section.material_ids.length > 0 ? (
                    <p className="text-muted-foreground mt-0.5">
                      {t('courses.draftMaterials', { count: section.material_ids.length })}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        ))}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onDone}>
            {t('settings.cancel')}
          </Button>
          <Button size="sm" disabled={commit.isPending} onClick={() => commit.mutate()}>
            {commit.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <GitBranch aria-hidden />}
            {t('courses.commitOutline')}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function CourseOnboardingCard({
  courseTitle,
  outlinePending,
  onAddMaterials,
  onGenerateOutline,
  onAddNode,
  onStudy,
  onAsk,
}: {
  courseTitle: string
  outlinePending: boolean
  onAddMaterials: () => void
  onGenerateOutline: () => void
  onAddNode: () => void
  onStudy: () => void
  onAsk: () => void
}) {
  const { t } = useTranslation()
  const steps = [
    {
      title: t('workspace.onboardStep1Title'),
      description: t('workspace.onboardStep1Desc'),
      actions: (
        <Button size="sm" onClick={onAddMaterials}>
          <FolderClosed aria-hidden />
          {t('workspace.onboardAddMaterials')}
        </Button>
      ),
    },
    {
      title: t('workspace.onboardStep2Title'),
      description: t('workspace.onboardStep2Desc'),
      actions: (
        <>
          <Button
            size="sm"
            variant="outline"
            disabled={outlinePending}
            onClick={onGenerateOutline}
          >
            {outlinePending ? (
              <Loader2 className="animate-spin" aria-hidden />
            ) : (
              <Sparkles aria-hidden />
            )}
            {t('workspace.onboardGenerateOutline')}
          </Button>
          <Button size="sm" variant="outline" onClick={onAddNode}>
            <Plus aria-hidden />
            {t('courses.addNode')}
          </Button>
        </>
      ),
    },
    {
      title: t('workspace.onboardStep3Title'),
      description: t('workspace.onboardStep3Desc'),
      actions: (
        <>
          <Button size="sm" variant="outline" onClick={onStudy}>
            <Sparkles aria-hidden />
            {t('workspace.onboardStudy')}
          </Button>
          <Button size="sm" variant="outline" onClick={onAsk}>
            <MessageSquare aria-hidden />
            {t('workspace.onboardAsk')}
          </Button>
        </>
      ),
    },
  ]
  return (
    <Card data-testid="course-onboarding">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Sparkles className="text-primary size-4" aria-hidden />
          {t('workspace.onboardTitle', { title: courseTitle })}
        </CardTitle>
        <p className="text-muted-foreground text-xs">{t('workspace.onboardSubtitle')}</p>
      </CardHeader>
      <CardContent className="space-y-3">
        {steps.map((step, index) => (
          <div key={step.title} className="border-border flex gap-3 rounded-lg border p-3">
            <span className="bg-primary/10 text-primary flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold">
              {index + 1}
            </span>
            <div className="min-w-0 flex-1 space-y-2">
              <p className="text-sm font-medium">{step.title}</p>
              <p className="text-muted-foreground text-xs">{step.description}</p>
              <div className="flex flex-wrap gap-2 pt-1">{step.actions}</div>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

function NodeCreateForm({
  title,
  setTitle,
  pending,
  onSubmit,
}: {
  title: string
  setTitle: (value: string) => void
  pending: boolean
  onSubmit: () => void
}) {
  const { t } = useTranslation()
  return (
    <form
      className="border-border flex items-center gap-2 rounded-lg border border-dashed p-2"
      onSubmit={(event) => {
        event.preventDefault()
        if (title.trim()) {
          onSubmit()
        }
      }}
    >
      <input
        autoFocus
        className="bg-surface min-w-0 flex-1 rounded px-2 py-1 text-sm"
        placeholder={t('courses.nodeTitle')}
        aria-label={t('courses.nodeTitle')}
        value={title}
        onChange={(event) => setTitle(event.target.value)}
      />
      <Button type="submit" size="sm" disabled={pending}>
        {pending ? <Loader2 className="animate-spin" aria-hidden /> : null}
        {t('settings.add')}
      </Button>
    </form>
  )
}

function OrganizerCard({
  nodeId,
  courseId,
  onOpenMaterial,
  extraActions,
}: {
  nodeId: number
  courseId: string
  onOpenMaterial: (materialId: number) => void
  extraActions?: TabAction[]
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [findings, setFindings] = useState<OrganizerFinding[] | null>(null)
  const [cheatsheet, setCheatsheet] = useState<string | null>(null)
  const [composeDialog, setComposeDialog] = useState<{
    kind?: ComposeKind
    preview: boolean
  } | null>(null)

  const artifacts = useQuery({
    queryKey: ['node-artifacts', nodeId],
    queryFn: () => getNodeArtifacts(nodeId),
  })

  const refreshArtifacts = async () => {
    await queryClient.invalidateQueries({ queryKey: ['node-artifacts', nodeId] })
  }

  const review = useMutation({
    mutationFn: () => reviewNode(nodeId),
    onSuccess: (result) => {
      setFindings(result.findings)
      void refreshArtifacts()
    },
  })
  const sheetPreview = useMutation({
    mutationFn: (materialId: number) => getMaterial(materialId),
    onSuccess: (detail) => {
      setCheatsheet(detail.extraction?.markdown ?? null)
      void refreshArtifacts()
    },
  })

  const existingSheet = artifacts.data?.cheat_sheet ?? null
  const reviews = artifacts.data?.reviews ?? []

  const cheatSheetMenu: PopoverMenuItem[] = existingSheet
    ? [
        {
          key: 'open',
          label: t('generate.openExisting'),
          icon: BookOpen,
          onSelect: () => onOpenMaterial(existingSheet.material_id),
        },
        {
          key: 'regenerate',
          label: t('chapter.cheatsheetRegenerate'),
          icon: ScrollText,
          onSelect: () => setComposeDialog({ kind: 'cheat_sheet', preview: true }),
        },
      ]
    : [
        {
          key: 'generate',
          label: t('chapter.cheatsheetGenerate'),
          icon: ScrollText,
          onSelect: () => setComposeDialog({ kind: 'cheat_sheet', preview: true }),
        },
      ]

  return (
    <div className="space-y-4">
      <TabActionBar
        actions={[
          {
            label: t('workspace.composeMaterial'),
            icon: BookOpen,
            onAction: () => setComposeDialog({ preview: false }),
            primary: true,
          },
          {
            label: t('chapter.review'),
            icon: ClipboardList,
            onAction: () => review.mutate(),
            pending: review.isPending,
          },
          {
            label: t('chapter.cheatsheet'),
            icon: ScrollText,
            menu: cheatSheetMenu,
          },
          ...(extraActions ?? []),
        ]}
      />
      {reviews.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1 text-[11px]">
          <span className="text-muted-foreground">{t('chapter.reviewHistory')}:</span>
          {reviews.map((entry) => (
            <button
              key={entry.material_id}
              type="button"
              className="bg-primary/10 text-primary hover:bg-primary/20 rounded-full px-2 py-0.5"
              onClick={() => onOpenMaterial(entry.material_id)}
            >
              {entry.title}
            </button>
          ))}
        </div>
      ) : null}
      {composeDialog !== null ? (
        <AIGenerateDialog
          task="compose"
          courseId={Number(courseId)}
          scopeNodeId={nodeId}
          rootNodeId={undefined}
          initial={
            composeDialog.kind ? { composeKind: composeDialog.kind } : undefined
          }
          onClose={() => setComposeDialog(null)}
          onSuccess={(result) => {
            const preview = composeDialog.preview
            setComposeDialog(null)
            if (preview) {
              sheetPreview.mutate((result as Material).id)
            } else {
              void refreshArtifacts()
            }
          }}
        />
      ) : null}
      {review.isError ? <ErrorBanner message={(review.error as Error).message} /> : null}

      {findings !== null ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <ClipboardList className="size-4" aria-hidden />
              {t('chapter.reviewTitle')}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {findings.length === 0 ? (
              <p className="text-muted-foreground text-sm">{t('chapter.reviewClean')}</p>
            ) : (
              findings.map((finding, index) => (
                <div key={index} className="bg-subtle rounded-md p-2 text-xs">
                  <div className="flex items-center gap-2">
                    <span className="bg-primary/10 text-primary rounded-full px-2 py-0.5 text-[10px]">
                      {t(`chapter.finding_${finding.kind}`)}
                    </span>
                    <span className="font-medium">{finding.title}</span>
                  </div>
                  {finding.detail ? (
                    <p className="text-muted-foreground mt-1">{finding.detail}</p>
                  ) : null}
                  {finding.suggestion ? (
                    <p className="text-primary mt-1">→ {finding.suggestion}</p>
                  ) : null}
                </div>
              ))
            )}
          </CardContent>
        </Card>
      ) : null}

      {cheatsheet !== null ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <ScrollText className="size-4" aria-hidden />
              {t('chapter.cheatsheetTitle')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <BlockRenderer blocks={[{ type: 'text', md: cheatsheet }] as Block[]} />
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}

function OverviewTab({
  courseId,
  currentId,
  isRoot,
  workspace,
  onPractice,
  onAsk,
  studyTargetId,
  askTargetId,
  onOpenMaterial,
  onGoToMaterials,
  onStudyLauncher,
  onAskHere,
}: {
  courseId: string
  currentId: number
  isRoot: boolean
  workspace: NonNullable<ReturnType<typeof useWorkspaceQuery>['data']>
  onPractice: (nodeId: number) => void
  onAsk: (child: WorkspaceChild) => void
  studyTargetId: number | null
  askTargetId: number | null
  onOpenMaterial: (materialId: number) => void
  onGoToMaterials: () => void
  onStudyLauncher: () => void
  onAskHere: () => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [adding, setAdding] = useState(false)
  const [title, setTitle] = useState('')
  const [draft, setDraft] = useState<{ chapters: OutlineDraftChapter[] } | null>(null)

  const addNodeHere = useMutation({
    mutationFn: () => addNode(Number(courseId), currentId, title.trim()),
    onSuccess: async () => {
      setAdding(false)
      setTitle('')
      await queryClient.invalidateQueries({ queryKey: ['tree', courseId] })
      await queryClient.invalidateQueries({ queryKey: ['node-workspace', String(currentId)] })
    },
  })

  const generateDraft = useMutation({
    mutationFn: () => outlineDraft(Number(courseId)),
    onSuccess: (result) => setDraft(result),
  })

  const nodeActions: TabAction[] = isRoot
    ? [
        {
          label: t('courses.generateOutline'),
          icon: Sparkles,
          onAction: () => generateDraft.mutate(),
          pending: generateDraft.isPending,
        },
        {
          label: t('courses.addNode'),
          icon: Plus,
          onAction: () => setAdding((current) => !current),
        },
      ]
    : [
        {
          label: t('courses.addChild'),
          icon: Plus,
          onAction: () => setAdding((current) => !current),
        },
      ]

  const childrenGrid =
    workspace.children.length > 0 ? (
      <div className="grid gap-3 md:grid-cols-2">
        {workspace.children.map((child) => (
          <ChildCard
            key={child.id}
            courseId={courseId}
            child={child}
            materialCount={(workspace.child_materials[String(child.id)] ?? []).length}
            studyTargetId={studyTargetId}
            askTargetId={askTargetId}
            onPractice={onPractice}
            onAsk={onAsk}
          />
        ))}
      </div>
    ) : null

  const courseIsEmpty =
    isRoot &&
    workspace.children.length === 0 &&
    workspace.materials.length === 0 &&
    workspace.folders.length === 0

  return (
    <div className="space-y-6">
      {workspace.node.objectives.length > 0 ? (
        <div className="flex flex-wrap gap-1">
          {workspace.node.objectives.map((objective, index) => (
            <span
              key={index}
              className="bg-subtle text-muted-foreground rounded-full px-2 py-0.5 text-[11px]"
            >
              {objective}
            </span>
          ))}
        </div>
      ) : null}

      {courseIsEmpty ? (
        <CourseOnboardingCard
          courseTitle={workspace.node.title}
          outlinePending={generateDraft.isPending}
          onAddMaterials={onGoToMaterials}
          onGenerateOutline={() => generateDraft.mutate()}
          onAddNode={() => setAdding(true)}
          onStudy={onStudyLauncher}
          onAsk={onAskHere}
        />
      ) : (
        <OrganizerCard
          nodeId={currentId}
          courseId={courseId}
          onOpenMaterial={onOpenMaterial}
          extraActions={nodeActions}
        />
      )}

      {adding ? (
        <NodeCreateForm
          title={title}
          setTitle={setTitle}
          pending={addNodeHere.isPending}
          onSubmit={() => addNodeHere.mutate()}
        />
      ) : null}
      {addNodeHere.isError ? (
        <p className="text-danger text-xs">{(addNodeHere.error as Error).message}</p>
      ) : null}
      {isRoot && draft ? (
        <OutlineDraftView
          courseId={courseId}
          draft={draft}
          onDone={() => {
            setDraft(null)
            void queryClient.invalidateQueries({ queryKey: ['tree', courseId] })
          }}
        />
      ) : null}

      {!isRoot ? (
        <section className="space-y-3" aria-label={t('courses.childrenTitle')}>
          <h2 className="text-muted-foreground text-sm font-medium">
            {t('courses.childrenTitle')}
          </h2>
          {childrenGrid ?? (
            <p className="text-muted-foreground text-sm">{t('courses.noChildren')}</p>
          )}
        </section>
      ) : (
        childrenGrid
      )}
    </div>
  )
}

function MaterialsTab({
  courseId,
  currentId,
  workspace,
  folderId,
  onOpenMaterial,
  onOpenFolder,
  onCloseFolder,
}: {
  courseId: string
  currentId: number
  workspace: NonNullable<ReturnType<typeof useWorkspaceQuery>['data']>
  folderId: number | null
  onOpenMaterial: (materialId: number) => void
  onOpenFolder: (folderId: number) => void
  onCloseFolder: () => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [pickerOpen, setPickerOpen] = useState(false)
  const [reExtractTarget, setReExtractTarget] = useState<number | null>(null)
  const [view, setView] = useStoredView(storageKeys.materialsView, 'list')
  const [menu, setMenu] = useState<{
    x: number
    y: number
    entry: WorkspaceMaterial
    canUnassign: boolean
  } | null>(null)
  const [folderMenu, setFolderMenu] = useState<{
    x: number
    y: number
    folder: WorkspaceFolder
  } | null>(null)
  const [browseFolderMenu, setBrowseFolderMenu] = useState<{
    x: number
    y: number
    folder: Folder
  } | null>(null)
  const [browseMenu, setBrowseMenu] = useState<{
    x: number
    y: number
    material: { id: number; title: string }
  } | null>(null)
  const [assignOpen, setAssignOpen] = useState(false)
  const [textDialog, setTextDialog] = useState<'txt' | 'md' | null>(null)
  const [folderDialog, setFolderDialog] = useState(false)
  const [paneMenu, setPaneMenu] = useState<{ x: number; y: number } | null>(null)
  const [createError, setCreateError] = useState<string | null>(null)
  const [materialQuery, setMaterialQuery] = useState('')
  const [discoverOpen, setDiscoverOpen] = useState(false)
  const [unassignedOpen, setUnassignedOpen] = useState(false)
  const [unassignedTarget, setUnassignedTarget] = useState<number | null>(null)
  const unassigned = useQuery({
    queryKey: ['materials', 'unassigned', Number(courseId)],
    queryFn: () => getUnassignedMaterials(Number(courseId)),
    enabled: workspace.node.is_root && folderId === null,
  })
  const allFoldersQuery = useQuery({
    queryKey: ['folders', Number(courseId)],
    queryFn: () => listFolders(Number(courseId)),
    enabled: folderId !== null,
  })
  const folderMaterialsQuery = useQuery({
    queryKey: ['materials', folderId, Number(courseId)],
    queryFn: () => listMaterials(folderId as number),
    enabled: folderId !== null,
  })
  const allFolders = useMemo(() => allFoldersQuery.data ?? [], [allFoldersQuery.data])
  const browseFolder =
    folderId !== null ? (allFolders.find((entry) => entry.id === folderId) ?? null) : null
  const linkedSourceId = browseFolder?.source_id ?? null
  const [sourceSubdir, setSourceSubdir] = useState('')
  useEffect(() => {
    setSourceSubdir('')
  }, [folderId])
  const sourceBrowseQuery = useQuery({
    queryKey: ['source-browse', linkedSourceId, sourceSubdir],
    queryFn: () => browseSource(linkedSourceId as number, sourceSubdir),
    enabled: linkedSourceId !== null,
  })
  const sourceBrowse = linkedSourceId !== null ? (sourceBrowseQuery.data ?? null) : null
  const browseActive =
    folderId !== null && allFoldersQuery.data !== undefined && browseFolder !== null
  const browseSubfolders = useMemo(
    () =>
      browseActive
        ? allFolders
            .filter((entry) => entry.parent_id === folderId)
            .sort((a, b) => a.name.localeCompare(b.name))
        : [],
    [allFolders, browseActive, folderId]
  )
  const browseMaterials = useMemo(
    () => (browseActive ? (folderMaterialsQuery.data ?? []) : []),
    [browseActive, folderMaterialsQuery.data]
  )
  const browseCrumbs: Crumb[] = useMemo(() => {
    if (!browseActive || browseFolder === null) {
      return []
    }
    const items: Crumb[] = [
      {
        key: 'materials-root',
        label: t('workspace.materialsCrumbRoot'),
        onClick: onCloseFolder,
      },
    ]
    if (linkedSourceId !== null) {
      items.push({
        key: `f${browseFolder.id}`,
        label: browseFolder.name,
        onClick: sourceSubdir === '' ? undefined : () => setSourceSubdir(''),
      })
      const parts = sourceSubdir ? sourceSubdir.split('/') : []
      parts.forEach((part, index) => {
        items.push({
          key: `sub-${index}-${part}`,
          label: part,
          onClick: () => setSourceSubdir(parts.slice(0, index + 1).join('/')),
        })
      })
      return items
    }
    const chain: Folder[] = []
    let walker: Folder | null = browseFolder
    while (walker !== null) {
      chain.unshift(walker)
      walker = allFolders.find((entry) => entry.id === walker?.parent_id) ?? null
    }
    return [
      ...items,
      ...chain.map((entry) => ({
        key: `f${entry.id}`,
        label: entry.name,
        onClick:
          entry.id === browseFolder.id
            ? undefined
            : () => {
                if (entry.parent_id === null) {
                  onCloseFolder()
                } else {
                  onOpenFolder(entry.id)
                }
              },
      })),
    ]
  }, [
    browseActive,
    browseFolder,
    allFolders,
    t,
    onCloseFolder,
    onOpenFolder,
    linkedSourceId,
    sourceSubdir,
  ])
  const [suggestions, setSuggestions] = useState<PlacementSuggestion[] | null>(null)
  const [suggestPending, setSuggestPending] = useState(false)
  const suggestPlacementsMutation = async (): Promise<void> => {
    setSuggestPending(true)
    try {
      const result = await getPlacementSuggestions(
        Number(courseId),
        (unassigned.data?.materials ?? []).map((entry) => entry.id),
      )
      setSuggestions(result.suggestions)
    } finally {
      setSuggestPending(false)
    }
  }
  const assignUnassigned = useMutation({
    mutationFn: async ({ nodeId, materialId }: { nodeId: number; materialId: number }) => {
      await allocateMaterial(nodeId, materialId)
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['materials'] })
      await refresh()
    },
    onError: (error: Error) => setCreateError(error.message),
  })
  const normalizedQuery = materialQuery.trim()
  const visibleFolders = useMemo(
    () =>
      normalizedQuery
        ? fuzzyFilter(workspace.folders, normalizedQuery, (folder) => folder.name)
        : workspace.folders,
    [workspace.folders, normalizedQuery]
  )
  const visibleMaterials = useMemo(
    () =>
      normalizedQuery
        ? fuzzyFilter(workspace.materials, normalizedQuery, (entry) => entry.title)
        : workspace.materials,
    [workspace.materials, normalizedQuery]
  )
  const visibleBrowseMaterials = useMemo(
    () =>
      normalizedQuery
        ? fuzzyFilter(browseMaterials, normalizedQuery, (entry) => entry.title)
        : browseMaterials,
    [browseMaterials, normalizedQuery]
  )
  const linkedMaterials = useMemo(
    () =>
      normalizedQuery
        ? fuzzyFilter(sourceBrowse?.materials ?? [], normalizedQuery, (entry) => entry.title)
        : (sourceBrowse?.materials ?? []),
    [sourceBrowse, normalizedQuery]
  )
  const ingestLinked = useMutation({
    mutationFn: ({ sourceId, relpath }: { sourceId: number; relpath: string }) =>
      ingestSourceFile(sourceId, relpath),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['source-browse'] })
    },
    onError: (error: Error) => setCreateError(error.message),
  })

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['node-workspace', String(currentId)] })
    await queryClient.invalidateQueries({ queryKey: ['tree', courseId] })
  }

  const unassign = useMutation({
    mutationFn: (materialId: number) => deallocateMaterial(currentId, materialId),
    onSuccess: () => void refresh(),
  })

  const [deriveNotice, setDeriveNotice] = useState<string | null>(null)
  const derive = useMutation({
    mutationFn: (ids: number[]) => deriveMaterials(ids),
    onSuccess: (result) => {
      void refresh()
      const parts: string[] = []
      if (result.created > 0) {
        parts.push(t('library.deriveBatchSaved', { count: result.created }))
      }
      if (result.deduped > 0) {
        parts.push(t('library.deriveBatchDeduped', { count: result.deduped }))
      }
      if (result.skipped > 0) {
        parts.push(t('library.deriveBatchSkipped', { count: result.skipped }))
      }
      setDeriveNotice(parts.join(' · '))
    },
    onError: (error: Error) => setDeriveNotice(error.message),
  })

  const onCreateText = async (
    input: TextFileCreateInput
  ): Promise<TextFileEditState | null> => {
    const state = await createTextMaterial({
      course_id: Number(courseId),
      folder_id: null,
      filename: input.filename,
      content: input.content,
      description: input.description,
      drawings: input.drawings,
    })
    if (state !== null) {
      await allocateMaterial(currentId, state.materialId)
      await refresh()
      await queryClient.invalidateQueries({ queryKey: ['materials'] })
    }
    return state
  }
  const onSaveText = async (
    input: TextFileSaveInput
  ): Promise<TextFileEditState> => {
    const next = await updateTextMaterial({
      materialId: input.state.materialId,
      content: input.content,
      description: input.description,
      drawings: input.drawings,
    })
    await refresh()
    return next
  }

  const createFolderAndAssign = useMutation({
    mutationFn: async (name: string) => {
      const folder = await createFolder(name, null, Number(courseId))
      await allocateNodeFolder(currentId, folder.id)
      return folder
    },
    onSuccess: async () => {
      setFolderDialog(false)
      setCreateError(null)
      await refresh()
      await queryClient.invalidateQueries({ queryKey: ['folders'] })
    },
    onError: (error: Error) => setCreateError(error.message),
  })

  const unassignFolder = useMutation({
    mutationFn: (folderId: number) => deallocateNodeFolder(currentId, folderId),
    onSuccess: () => void refresh(),
  })

  const assignSelection = useMutation({
    mutationFn: async ({ nodeId }: { nodeId: number }) => {
      for (const materialId of selectedMaterialIds) {
        await allocateMaterial(nodeId, materialId)
      }
      for (const folderId of selectedFolderIds) {
        await allocateNodeFolder(nodeId, folderId)
      }
    },
    onSuccess: async () => {
      setAssignOpen(false)
      await queryClient.invalidateQueries({ queryKey: ['tree'] })
      await queryClient.invalidateQueries({ queryKey: ['node-workspace'] })
    },
  })

  const materialOrder = useMemo(
    () =>
      browseActive
        ? linkedSourceId !== null
          ? linkedMaterials.map((entry) => `m${entry.id}`)
          : [
              ...browseSubfolders.map((entry) => `f${entry.id}`),
              ...visibleBrowseMaterials.map((entry) => `m${entry.id}`),
            ]
        : workspace.materials.map((entry) => `m${entry.material_id}`),
    [
      browseActive,
      linkedSourceId,
      linkedMaterials,
      browseSubfolders,
      visibleBrowseMaterials,
      workspace.materials,
    ]
  )
  const selection = useSelection(materialOrder)
  const selectedMaterialIds = useMemo(
    () =>
      [...selection.selected]
        .filter((key) => key.startsWith('m'))
        .map((key) => Number(key.slice(1))),
    [selection.selected]
  )
  const selectedFolderIds = useMemo(
    () =>
      [...selection.selected]
        .filter((key) => key.startsWith('f'))
        .map((key) => Number(key.slice(1))),
    [selection.selected]
  )
  const liveSelection = useRef(selection.selected)
  liveSelection.current = selection.selected

  const unassignSelected = () => {
    const viaFolder = new Set(workspace.folder_material_ids)
    const materialIds = [...liveSelection.current]
      .filter((key) => key.startsWith('m'))
      .map((key) => Number(key.slice(1)))
      .filter((materialId) => !viaFolder.has(materialId))
    for (const materialId of materialIds) {
      unassign.mutate(materialId)
    }
    const folderIds = [...liveSelection.current]
      .filter((key) => key.startsWith('f'))
      .map((key) => Number(key.slice(1)))
    for (const folderId of folderIds) {
      unassignFolder.mutate(folderId)
    }
    selection.clear()
  }

  const upload = useMaterialUpload({
    courseId: Number(courseId),
    getTargetNodeId: () => currentId,
    onFolderCreated: async (folder) => {
      await allocateNodeFolder(currentId, folder.id)
      await refresh()
      await queryClient.invalidateQueries({ queryKey: ['folders'] })
    },
    onUploaded: async () => {
      await refresh()
    },
  })

  useWindowDropRegistration(true, workspace.node.title, () => upload)

  const createMenu = useCreateMaterialMenu({
    upload,
    onNewText: (kind) => setTextDialog(kind),
    onNewFolder: () => setFolderDialog(true),
    onNewUrl: () =>
      useImportUrlStore.getState().openImport(undefined, currentId),
    onDiscover: () => setDiscoverOpen(true),
  })

  const openContextMenu = (
    event: React.MouseEvent,
    entry: WorkspaceMaterial,
    canUnassign: boolean,
  ) => {
    event.preventDefault()
    if (!selection.selected.has(`m${entry.material_id}`)) {
      selection.set([`m${entry.material_id}`])
    }
    setMenu({ x: event.clientX, y: event.clientY, entry, canUnassign })
  }

  const openFolderContextMenu = useCallback(
    (event: React.MouseEvent, folder: WorkspaceFolder) => {
      event.preventDefault()
      if (!selection.selected.has(`f${folder.folder_id}`)) {
        selection.set([`f${folder.folder_id}`])
      }
      setFolderMenu({ x: event.clientX, y: event.clientY, folder })
    },
    [selection]
  )

  const openFolderInLibrary = useCallback(
    (folder: WorkspaceFolder) => {
      void navigate({
        to: '/library',
        search: {
          course: Number(courseId),
          folder: folder.folder_id,
          source: folder.source_id ?? undefined,
        },
      })
    },
    [navigate, courseId]
  )

  const openBrowseFolderInLibrary = useCallback(
    (folder: Folder) => {
      void navigate({
        to: '/library',
        search: {
          course: Number(courseId),
          folder: folder.id,
          source: folder.source_id ?? undefined,
        },
      })
    },
    [navigate, courseId]
  )

  const openInLibraryCrumb =
    browseActive && browseFolder !== null ? (
      <Button
        variant="outline"
        size="sm"
        onClick={() => openBrowseFolderInLibrary(browseFolder)}
      >
        <ExternalLink aria-hidden />
        {t('workspace.openFolderInLibrary')}
      </Button>
    ) : undefined

  const folderSpecs: MaterialFolderSpec[] = useMemo(() => {
    if (browseActive) {
      if (linkedSourceId !== null) {
        return (sourceBrowse?.subdirs ?? []).map((entry) => ({
          key: `sub-${entry.name}`,
          name: entry.name,
          onOpen: () =>
            setSourceSubdir(sourceSubdir ? `${sourceSubdir}/${entry.name}` : entry.name),
        }))
      }
      return browseSubfolders.map((entry) => ({
        key: `f${entry.id}`,
        name: entry.name,
        linked: entry.source_id !== null,
        selectionState: selection.selected.has(`f${entry.id}`) ? 'selected' : 'none',
        onPointerDown: (event) => selection.pointerDown(`f${entry.id}`, event),
        onOpen: () => onOpenFolder(entry.id),
        onContextMenu: (event) => {
          event.preventDefault()
          if (!selection.selected.has(`f${entry.id}`)) {
            selection.set([`f${entry.id}`])
          }
          setBrowseFolderMenu({ x: event.clientX, y: event.clientY, folder: entry })
        },
      }))
    }
    return visibleFolders.map((folder) => ({
      key: `f${folder.folder_id}`,
      name: folder.name,
      linked: folder.source_id !== null,
      title: t('workspace.folderMembers', { count: folder.member_count }),
      selectionState: selection.selected.has(`f${folder.folder_id}`) ? 'selected' : 'none',
      onPointerDown: (event) => selection.pointerDown(`f${folder.folder_id}`, event),
      onOpen: () => onOpenFolder(folder.folder_id),
      onContextMenu: (event) => openFolderContextMenu(event, folder),
      gridMeta: (
        <span className="text-muted-foreground text-[10px]">{folder.member_count}</span>
      ),
      trailing: (
        <>
          <span className="text-muted-foreground shrink-0 text-[10px]">
            {folder.member_count}
          </span>
          <button
            type="button"
            className="text-muted-foreground hidden shrink-0 group-hover:block"
            title={t('workspace.unassignFolder')}
            onClick={() => unassignFolder.mutate(folder.folder_id)}
          >
            <X className="size-3.5" aria-hidden />
          </button>
        </>
      ),
    }))
  }, [
    browseActive,
    linkedSourceId,
    sourceBrowse,
    sourceSubdir,
    browseSubfolders,
    selection,
    onOpenFolder,
    visibleFolders,
    t,
    unassignFolder,
    openFolderContextMenu,
  ])

  const renderLinkedEntry = (entry: {
    id: number
    title: string
    kind: string
    status: string
  }) => {
    const key = `m${entry.id}`
    return view === 'grid' ? (
      <MaterialTile
        key={entry.id}
        data-selectable-id={key}
        material={{
          id: entry.id,
          title: entry.title,
          kind: entry.kind,
          status: entry.status,
        }}
        selectionState={selection.selected.has(key) ? 'selected' : 'none'}
        className="w-full"
        onMouseDown={(event) => selection.pointerDown(key, event)}
        onClick={(event) => {
          if (isKeyboardClick(event)) {
            onOpenMaterial(entry.id)
          }
        }}
        onDoubleClick={() => onOpenMaterial(entry.id)}
        onContextMenu={(event) => {
          event.preventDefault()
          setBrowseMenu({
            x: event.clientX,
            y: event.clientY,
            material: entry,
          })
        }}
      />
    ) : (
      <div key={entry.id} data-selectable-id={key}>
        <MaterialRow
          material={{
            id: entry.id,
            title: entry.title,
            kind: entry.kind,
            status: entry.status,
          }}
          selectionState={selection.selected.has(key) ? 'selected' : 'none'}
          onMouseDown={(event) => selection.pointerDown(key, event)}
          onOpen={() => onOpenMaterial(entry.id)}
          action={
            <span className="text-muted-foreground shrink-0 text-xs">{entry.kind}</span>
          }
          onContextMenu={(event) => {
            event.preventDefault()
            setBrowseMenu({
              x: event.clientX,
              y: event.clientY,
              material: entry,
            })
          }}
        />
      </div>
    )
  }

  const renderBrowseEntry = (entry: Material) => {
    const key = `m${entry.id}`
    return view === 'grid' ? (
      <MaterialTile
        key={entry.id}
        data-selectable-id={key}
        material={{
          id: entry.id,
          title: entry.title,
          kind: entry.kind,
          status: entry.status,
          aiComposed: entry.provenance?.source === 'ai-composed',
        }}
        selectionState={selection.selected.has(key) ? 'selected' : 'none'}
        className="w-full"
        onMouseDown={(event) => selection.pointerDown(key, event)}
        onClick={(event) => {
          if (isKeyboardClick(event)) {
            onOpenMaterial(entry.id)
          }
        }}
        onDoubleClick={() => onOpenMaterial(entry.id)}
        onContextMenu={(event) => {
          event.preventDefault()
          if (!selection.selected.has(key)) {
            selection.set([key])
          }
          setBrowseMenu({ x: event.clientX, y: event.clientY, material: entry })
        }}
      />
    ) : (
      <div key={entry.id} data-selectable-id={key}>
        <MaterialRow
          material={{
            id: entry.id,
            title: entry.title,
            kind: entry.kind,
            status: entry.status,
            aiComposed: entry.provenance?.source === 'ai-composed',
          }}
          selectionState={selection.selected.has(key) ? 'selected' : 'none'}
          onMouseDown={(event) => selection.pointerDown(key, event)}
          onOpen={() => onOpenMaterial(entry.id)}
          action={
            <span className="text-muted-foreground shrink-0 text-xs">{entry.kind}</span>
          }
          onContextMenu={(event) => {
            event.preventDefault()
            if (!selection.selected.has(key)) {
              selection.set([key])
            }
            setBrowseMenu({ x: event.clientX, y: event.clientY, material: entry })
          }}
        />
      </div>
    )
  }

  const entryMenu = (
    entry: WorkspaceMaterial,
    canUnassign: boolean,
  ): ContextMenuItem[] => {
    const multi = selection.selected.size > 1
    const items: ContextMenuItem[] = []
    if (!multi) {
      items.push({
        key: 'open',
        label: t('common.open'),
        onSelect: () => onOpenMaterial(entry.material_id),
      })
    }
    const selectedIds = [...selection.selected]
      .filter((key) => key.startsWith('m'))
      .map((key) => Number(key.slice(1)))
    const pool =
      multi && selection.selected.has(`m${entry.material_id}`)
        ? selectedIds
        : [entry.material_id]
    const derivable = pool.filter((id) =>
      (workspace.materials ?? []).some(
        (candidate) => candidate.material_id === id && candidate.has_extraction
      )
    )
    if (derivable.length > 0) {
      items.push({
        key: 'derive',
        label: multi
          ? t('library.deriveMany', { count: derivable.length })
          : t('library.deriveMaterial'),
        disabled: derive.isPending,
        onSelect: () => derive.mutate(derivable),
      })
    }
    if (
      !multi &&
      (entry.reextract_modes?.length ?? 0) > 1 &&
      entry.status !== 'pending' &&
      entry.status !== 'processing'
    ) {
      items.push({
        key: 're-extract',
        label: t('reextract.menuEntry'),
        onSelect: () => setReExtractTarget(entry.material_id),
      })
    }
    items.push({
      key: 'assign',
      label: t('workspace.assignSelection'),
      onSelect: () => setAssignOpen(true),
    })
    if (canUnassign && entry.via_folder_id === null) {
      items.push({
        key: 'unassign',
        label: multi ? t('workspace.unassignSelection') : t('courses.deallocate'),
        danger: true,
        onSelect: multi
          ? unassignSelected
          : () => unassign.mutate(entry.material_id),
      })
    }
    return items
  }

  const mirrorFolder = useMutation({
    mutationFn: ({ folderId }: { folderId: number }) =>
      mirrorFolderApi(currentId, folderId),
    onSuccess: () => void refresh(),
  })

  const mirrorFeedback = (
    created: number,
    reused: number,
    skipped: string[],
  ): void => {
    const parts: string[] = []
    if (created > 0) {
      parts.push(t('workspace.mirrorCreated', { count: created }))
    }
    if (reused > 0) {
      parts.push(t('workspace.mirrorReused', { count: reused }))
    }
    if (parts.length === 0) {
      parts.push(t('workspace.mirrorNone'))
    }
    if (skipped.length > 0) {
      parts.push(t('workspace.mirrorSkipped', { count: skipped.length }))
    }
    setDeriveNotice(parts.join(' · '))
  }

  const folderMenuItems = (folder: WorkspaceFolder): ContextMenuItem[] => {
    const multi = selection.selected.size > 1
    const items: ContextMenuItem[] = [
      {
        key: 'open',
        label: t('common.open'),
        onSelect: () => onOpenFolder(folder.folder_id),
      },
      {
        key: 'open-in-library',
        label: t('workspace.openFolderInLibrary'),
        onSelect: () => openFolderInLibrary(folder),
      },
      {
        key: 'assign',
        label: t('workspace.assignSelection'),
        onSelect: () => setAssignOpen(true),
      },
      {
        key: 'mirror',
        label: t('workspace.mirrorFolder'),
        onSelect: () =>
          mirrorFolder.mutate(
            { folderId: folder.folder_id },
            {
              onSuccess: (result) =>
                mirrorFeedback(
                  result.created_nodes,
                  result.reused_nodes,
                  result.skipped_folders,
                ),
            },
          ),
      },
    ]
    if (multi) {
      items.push({
        key: 'unassign',
        label: t('workspace.unassignSelection'),
        danger: true,
        onSelect: unassignSelected,
      })
    } else {
      items.push({
        key: 'unassign-folder',
        label: t('workspace.unassignFolder'),
        danger: true,
        onSelect: () => unassignFolder.mutate(folder.folder_id),
      })
    }
    return items
  }

  const renderEntry = (entry: WorkspaceMaterial, canUnassign: boolean) => {
    const key = `m${entry.material_id}`
    const materialIds = [...liveSelection.current]
      .filter((entry2) => entry2.startsWith('m'))
      .map((entry2) => Number(entry2.slice(1)))
    const dragMaterialIds = selection.selected.has(key)
      ? materialIds
      : [entry.material_id]
    const rowCanUnassign = canUnassign && entry.via_folder_id === null
    return view === 'grid' ? (
      <div
        key={entry.material_id}
        data-selectable-id={key}
        draggable
        onDragStart={(event) =>
          buildDragPayload(event, {
            key,
            id: entry.material_id,
            kind: 'material',
            selected: selection.selected,
            selectedPayload: {
              folderIds: [],
              materialIds: dragMaterialIds,
              noteIds: [],
            },
            setSelection: (keys) => selection.set(keys),
            countLabel: (count) => t('drag.items', { count }),
          })
        }
        title={t('workspace.materialDragHint')}
      >
        <MaterialTile
          material={{
            id: entry.material_id,
            title: entry.title,
            kind: entry.kind,
            aiComposed: entry.provenance?.source === 'ai-composed',
          }}
          selectionState={selection.selected.has(key) ? 'selected' : 'none'}
          className="w-full"
          onMouseDown={(event) => selection.pointerDown(key, event)}
          onClick={(event) => {
            if (isKeyboardClick(event)) {
              onOpenMaterial(entry.material_id)
            }
          }}
          onDoubleClick={() => onOpenMaterial(entry.material_id)}
          onContextMenu={(event) => openContextMenu(event, entry, canUnassign)}
        />
      </div>
    ) : (
      <div key={entry.material_id} data-selectable-id={key}>
        <WorkspaceMaterialRow
          entry={entry}
          selectionState={selection.selected.has(key) ? 'selected' : 'none'}
          onPointerDown={(event) => selection.pointerDown(key, event)}
          onDragStart={(event) =>
            buildDragPayload(event, {
              key,
              id: entry.material_id,
              kind: 'material',
              selected: selection.selected,
              selectedPayload: {
                folderIds: [],
                materialIds: dragMaterialIds,
                noteIds: [],
              },
              setSelection: (keys) => selection.set(keys),
              countLabel: (count) => t('drag.items', { count }),
            })
          }
          onUnassign={
            rowCanUnassign ? (materialId) => unassign.mutate(materialId) : undefined
          }
          onOpen={(materialId) => onOpenMaterial(materialId)}
          onContextMenu={(event) => openContextMenu(event, entry, canUnassign)}
        />
      </div>
    )
  }

  return (
    <MarqueeSurface
      className="min-h-0 flex-1 space-y-4"
      selection={selection}
      clearBlocked={() =>
        menu !== null ||
        folderMenu !== null ||
        browseFolderMenu !== null ||
        browseMenu !== null ||
        paneMenu !== null ||
        textDialog !== null ||
        folderDialog ||
        pickerOpen ||
        assignOpen
      }
      onContextMenu={(event) => {
        if (event.defaultPrevented) {
          return
        }
        const target = event.target as HTMLElement
        if (
          target.closest(
            '[data-selectable-id], button, input, textarea, select, a, [data-no-marquee]'
          ) !== null
        ) {
          return
        }
        event.preventDefault()
        setPaneMenu({ x: event.clientX, y: event.clientY })
      }}
    >
      {createMenu.inputs}
      {!browseActive ? (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            aria-haspopup="menu"
            disabled={upload.uploading}
            onClick={(event) => {
              const rect = event.currentTarget.getBoundingClientRect()
              setPaneMenu({ x: rect.left, y: rect.bottom + 4 })
            }}
          >
            {upload.uploading ? (
              <Loader2 className="animate-spin" aria-hidden />
            ) : (
              <Plus aria-hidden />
            )}
            {t('library.create')}
          </Button>
          <Button variant="outline" size="sm" onClick={() => setPickerOpen(true)}>
            <BookOpen aria-hidden />
            {t('workspace.assignMaterial')}
          </Button>
          {createError !== null ? (
            <p className="text-warning text-xs" role="alert">
              {createError}
            </p>
          ) : null}
          {deriveNotice !== null ? (
            <p className="text-muted-foreground text-xs" role="status">
              {deriveNotice}
            </p>
          ) : null}
        </div>
      ) : null}
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">
            {browseActive && browseFolder !== null
              ? browseFolder.name
              : t('chapter.nodeMaterials')}
          </h2>
          <div className="flex items-center gap-2">
            <ExpandableSearch
              value={materialQuery}
              onChange={setMaterialQuery}
              placeholder={t('workspace.searchPlaceholder')}
              ariaLabel={t('workspace.searchPlaceholder')}
              clearLabel={t('library.clearSearch')}
            />
            <ViewToggle view={view} onChange={setView} />
          </div>
        </div>
        {workspace.node.is_root &&
        (unassigned.data?.count ?? 0) > 0 &&
        !unassignedOpen ? (
          <button
            type="button"
            data-testid="needs-placement-strip"
            className="text-warning hover:bg-subtle flex w-full items-center justify-between rounded-md border border-dashed px-3 py-2 text-xs"
            onClick={() => setUnassignedOpen(true)}
          >
            <span>
              {t('workspace.needsPlacement', { count: unassigned.data?.count ?? 0 })}
            </span>
            <ChevronRight className="size-3.5 shrink-0" aria-hidden />
          </button>
        ) : null}
        {unassignedOpen && workspace.node.is_root ? (
          <div
            data-testid="needs-placement-panel"
            className="border-border space-y-1 rounded-md border border-dashed p-2"
          >
            {(unassigned.data?.materials ?? []).map((entry) => {
              const candidates =
                suggestions?.find((item) => item.material_id === entry.id)
                  ?.candidates ?? []
              return (
                <div key={entry.id} className="flex items-center justify-between gap-2 py-0.5">
                  <span className="min-w-0 flex-1 truncate text-xs">{entry.title}</span>
                  <div className="flex shrink-0 items-center gap-1">
                    {candidates.map((candidate) => (
                      <button
                        key={candidate.node_id}
                        type="button"
                        title={candidate.matched_on.join(', ')}
                        className="border-border hover:bg-subtle text-muted-foreground rounded-md border border-dashed px-1.5 py-0.5 text-[11px]"
                        disabled={assignUnassigned.isPending}
                        onClick={() =>
                          assignUnassigned.mutate(
                            { nodeId: candidate.node_id, materialId: entry.id },
                            {
                              onSuccess: () => setSuggestions(
                                (current) =>
                                  (current ?? []).filter(
                                    (item) => item.material_id !== entry.id,
                                  ),
                              ),
                            },
                          )
                        }
                      >
                        {candidate.breadcrumb.length > 1
                          ? `${candidate.breadcrumb[candidate.breadcrumb.length - 2].title} › ${candidate.node_title}`
                          : candidate.node_title}
                      </button>
                    ))}
                    <Button
                      size="sm"
                      variant="outline"
                      data-testid={`needs-placement-assign-${entry.id}`}
                      onClick={() => setUnassignedTarget(entry.id)}
                    >
                      {t('workspace.assignNeedsPlacement')}
                    </Button>
                  </div>
                </div>
              )
            })}
            <div className="flex items-center justify-between">
              <button
                type="button"
                className="text-muted-foreground text-left text-xs"
                onClick={() =>
                  void suggestPlacementsMutation()
                }
                disabled={suggestPending}
              >
                {suggestPending
                  ? t('workspace.suggestPending')
                  : t('workspace.suggestForAll')}
              </button>
              <button
                type="button"
                className="text-muted-foreground text-left text-xs"
                onClick={() => setUnassignedOpen(false)}
              >
                {t('workspace.needsPlacementCollapse')}
              </button>
            </div>
          </div>
        ) : null}
        {browseActive ? (
          linkedSourceId !== null ? (
            sourceBrowseQuery.isLoading || sourceBrowse === null ? (
              <MaterialBrowserSkeleton view={view} count={6} />
            ) : (
              <MaterialBrowser
                view={view}
                folders={folderSpecs}
                crumbs={browseCrumbs}
                crumbsExtra={openInLibraryCrumb}
                className={view === 'grid' ? 'gap-2' : 'gap-1'}
              >
                {createError !== null ? (
                  <p className="text-warning col-span-full p-2 text-xs" role="alert">
                    {createError}
                  </p>
                ) : null}
                {sourceBrowse.missing_target ? (
                  <p className="text-danger col-span-full flex flex-wrap items-center gap-2 p-2 text-xs">
                    <span>
                      {t('library.targetMissing', { path: sourceBrowse.path })}
                    </span>
                  </p>
                ) : null}
                {sourceBrowse.last_scan_error ? (
                  <p
                    className="text-warning col-span-full p-2 text-xs"
                    title={sourceBrowse.last_scan_error}
                  >
                    {t('library.scanError', { message: sourceBrowse.last_scan_error })}
                  </p>
                ) : null}
                {linkedMaterials.map(renderLinkedEntry)}
                {sourceBrowse.uningested.map((entry) => (
                  <button
                    key={entry.relpath}
                    type="button"
                    className={cn(
                      'group border-border flex cursor-pointer select-none flex-col items-center gap-2 rounded-lg border border-dashed p-3 text-center transition-colors hover:bg-subtle',
                      view === 'list' &&
                        'flex w-full flex-row items-center gap-2 rounded-md px-3 py-2 text-left text-sm'
                    )}
                    title={t('library.ingestHint')}
                    onClick={() =>
                      ingestLinked.mutate({
                        sourceId: linkedSourceId as number,
                        relpath: entry.relpath,
                      })
                    }
                  >
                    <KindIcon
                      kind="doc"
                      className="text-muted-foreground/60 shrink-0"
                    />
                    <span
                      className={cn(
                        'text-xs',
                        view === 'grid' ? 'line-clamp-2' : 'min-w-0 flex-1 truncate'
                      )}
                    >
                      {entry.name}
                    </span>
                    <span className="bg-warning/15 text-warning shrink-0 rounded-full px-2 py-0.5 text-[10px]">
                      {t('library.pendingIngest')}
                    </span>
                  </button>
                ))}
                {!sourceBrowse.missing_target &&
                sourceBrowse.subdirs.length === 0 &&
                linkedMaterials.length === 0 &&
                sourceBrowse.uningested.length === 0 ? (
                  normalizedQuery ? (
                    <p className="text-muted-foreground py-2 text-center text-sm">
                      {t('workspace.noSearchResults')}
                    </p>
                  ) : (
                    <EmptyState
                      icon={FolderClosed}
                      compact
                      title={t('workspace.folderEmpty')}
                    />
                  )
                ) : null}
              </MaterialBrowser>
            )
          ) : folderMaterialsQuery.isLoading ? (
            <MaterialBrowserSkeleton view={view} count={6} />
          ) : browseSubfolders.length === 0 && visibleBrowseMaterials.length === 0 ? (
            normalizedQuery ? (
              <p className="text-muted-foreground py-2 text-center text-sm">
                {t('workspace.noSearchResults')}
              </p>
            ) : (
              <EmptyState icon={FolderClosed} compact title={t('workspace.folderEmpty')} />
            )
          ) : (
            <MaterialBrowser
              view={view}
              folders={folderSpecs}
              crumbs={browseCrumbs}
              crumbsExtra={openInLibraryCrumb}
            >
              {visibleBrowseMaterials.map(renderBrowseEntry)}
            </MaterialBrowser>
          )
        ) : workspace.materials.length === 0 && workspace.folders.length === 0 ? (
          <EmptyState
            icon={Upload}
            title={t('workspace.uploadEmptyLabel')}
            description={t('workspace.uploadEmptyHint')}
            action={
              <MaterialUploadDropzone
                upload={upload}
                hint={t('workspace.uploadEmptyHint')}
              />
            }
          />
        ) : visibleFolders.length === 0 && visibleMaterials.length === 0 ? (
          <p className="text-muted-foreground py-2 text-center text-sm">
            {t('workspace.noSearchResults')}
          </p>
        ) : (
          <MaterialBrowser view={view} folders={folderSpecs}>
            {visibleMaterials.map((entry) => renderEntry(entry, true))}
          </MaterialBrowser>
        )}
      </div>

      {menu !== null ? (
        <ContextMenu
          x={menu.x}
          y={menu.y}
          items={entryMenu(menu.entry, menu.canUnassign)}
          onClose={() => setMenu(null)}
        />
      ) : null}
      {folderMenu !== null ? (
        <ContextMenu
          x={folderMenu.x}
          y={folderMenu.y}
          items={folderMenuItems(folderMenu.folder)}
          onClose={() => setFolderMenu(null)}
        />
      ) : null}
      {browseFolderMenu !== null ? (
        <ContextMenu
          x={browseFolderMenu.x}
          y={browseFolderMenu.y}
          items={[
            {
              key: 'open',
              label: t('common.open'),
              onSelect: () => onOpenFolder(browseFolderMenu.folder.id),
            },
            {
              key: 'open-in-library',
              label: t('workspace.openFolderInLibrary'),
              onSelect: () => openBrowseFolderInLibrary(browseFolderMenu.folder),
            },
            {
              key: 'assign',
              label: t('workspace.assignSelection'),
              onSelect: () => setAssignOpen(true),
            },
          ]}
          onClose={() => setBrowseFolderMenu(null)}
        />
      ) : null}
      {browseMenu !== null ? (
        <ContextMenu
          x={browseMenu.x}
          y={browseMenu.y}
          items={[
            {
              key: 'open',
              label: t('common.open'),
              onSelect: () => onOpenMaterial(browseMenu.material.id),
            },
            {
              key: 'assign',
              label: t('workspace.assignSelection'),
              onSelect: () => setAssignOpen(true),
            },
          ]}
          onClose={() => setBrowseMenu(null)}
        />
      ) : null}
      {paneMenu !== null ? (
        <ContextMenu
          x={paneMenu.x}
          y={paneMenu.y}
          items={createMenu.items}
          onClose={() => setPaneMenu(null)}
        />
      ) : null}

      {textDialog !== null ? (
        <NewTextFileDialog
          defaultKind={textDialog}
          courseId={Number(courseId)}
          onCreate={onCreateText}
          onSave={onSaveText}
          onCancel={() => setTextDialog(null)}
        />
      ) : null}
      {folderDialog ? (
        <NewFolderDialog
          title={t('library.newFolder')}
          namePlaceholder={t('library.folderName')}
          onConfirm={(name) => createFolderAndAssign.mutate(name)}
          onCancel={() => setFolderDialog(false)}
        />
      ) : null}

      {reExtractTarget !== null ? (
        <ReExtractDialog
          materialId={reExtractTarget}
          open
          onClose={() => setReExtractTarget(null)}
          onSuccess={async () => {
            await refresh()
          }}
        />
      ) : null}
      <DiscoverDialog
        open={discoverOpen}
        onClose={() => setDiscoverOpen(false)}
        courseId={Number(courseId)}
        nodeId={currentId}
        defaultQuery={workspace.node.is_root ? '' : workspace.node.title}
      />
      {pickerOpen ? (
        <MaterialPickerDialog
          courseId={Number(courseId)}
          nodeId={currentId}
          nodeTitle={workspace.node.title}
          assignedIds={new Set([
            ...workspace.materials.map((entry) => entry.material_id),
            ...workspace.folder_material_ids,
          ])}
          assignedFolderIds={
            new Set(workspace.folders.map((entry) => entry.folder_id))
          }
          onClose={() => setPickerOpen(false)}
        />
      ) : null}
      {assignOpen ? (
        <AssignToNodeDialog
          courseId={Number(courseId)}
          title={t('assignToNode.title')}
          countText={t('assignToNode.materialCount', {
            count: selection.selected.size,
          })}
          confirmLabel={t('assignToNode.assign')}
          onDone={(nodeId) => assignSelection.mutateAsync({ nodeId })}
          onClose={() => setAssignOpen(false)}
        />
      ) : null}
      {unassignedTarget !== null ? (
        <AssignToNodeDialog
          courseId={Number(courseId)}
          title={t('workspace.assignNeedsPlacement')}
          countText={
            (unassigned.data?.materials ?? []).find(
              (entry) => entry.id === unassignedTarget,
            )?.title ?? ''
          }
          confirmLabel={t('assignToNode.assign')}
          onDone={async (nodeId) => {
            await assignUnassigned.mutateAsync({
              nodeId,
              materialId: unassignedTarget,
            })
            setUnassignedTarget(null)
          }}
          onClose={() => setUnassignedTarget(null)}
        />
      ) : null}
    </MarqueeSurface>
  )
}

function NotesTab({
  courseId,
  currentId,
  titles,
  onOpenNote,
}: {
  courseId: string
  currentId: number
  titles: Map<number, string>
  onOpenNote: (noteId: number) => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [query, setQuery] = useState('')
  const [submitted, setSubmitted] = useState('')
  const [activeTag, setActiveTag] = useState<string | null>(null)
  const [view, setView] = useStoredView(storageKeys.notesView, 'list')
  const [renaming, setRenaming] = useState<{ id: number; title: string } | null>(null)
  const [undoItem, setUndoItem] = useState<number | null>(null)
  const [moveOpen, setMoveOpen] = useState(false)
  const [paneMenu, setPaneMenu] = useState<{ x: number; y: number } | null>(null)
  const [confirm, confirmElement] = useConfirm()
  const pageSize = 50

  useEffect(() => {
    const id = setTimeout(() => setSubmitted(query.trim()), 250)
    return () => clearTimeout(id)
  }, [query])

  const notes = useInfiniteQuery({
    queryKey: ['notes', 'node', currentId, submitted, activeTag],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      listNotes(submitted || undefined, Number(courseId), {
        tag: activeTag ?? undefined,
        node_id: currentId,
        limit: pageSize,
        cursor: pageParam,
      }),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  })
  const tags = useQuery({
    queryKey: ['note-tags', Number(courseId)],
    queryFn: () => listNoteTags(Number(courseId)),
  })

  const create = useMutation({
    mutationFn: () =>
      createNote({
        title: t('notes.defaultTitle'),
        course_id: Number(courseId),
        node_id: currentId,
        tags: activeTag ? [activeTag] : [],
      }),
    onSuccess: async (note) => {
      await queryClient.invalidateQueries({ queryKey: ['notes'] })
      await queryClient.invalidateQueries({ queryKey: ['note-tags'] })
      onOpenNote(note.id)
    },
  })
  const draft = useMutation({
    mutationFn: () => draftNodeNote(currentId),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ['notes'] })
      onOpenNote(result.note_id)
    },
  })
  const rename = useMutation({
    mutationFn: ({ id, title }: { id: number; title: string }) =>
      updateNote(id, { title }),
    onSuccess: async () => {
      setRenaming(null)
      await queryClient.invalidateQueries({ queryKey: ['notes'] })
    },
  })
  const remove = useMutation({
    mutationFn: (noteId: number) => deleteNote(noteId),
    onSuccess: async (result) => {
      setUndoItem(result.deleted_item_id)
      await queryClient.invalidateQueries({ queryKey: ['notes'] })
      await queryClient.invalidateQueries({ queryKey: ['note-tags'] })
      await queryClient.invalidateQueries({ queryKey: ['tree'] })
    },
  })

  const flatNotes = useMemo(
    () => notes.data?.pages.flatMap((page) => page.items) ?? [],
    [notes.data]
  )
  const noteOrder = useMemo(() => flatNotes.map((note) => String(note.id)), [flatNotes])
  const selection = useSelection(noteOrder)
  const selectedNoteIds = useMemo(
    () => [...selection.selected].map((key) => Number(key)),
    [selection.selected]
  )
  const liveSelection = useRef(selection.selected)
  liveSelection.current = selection.selected

  const moveNotes = useMutation({
    mutationFn: async ({ nodeId, noteIds }: { nodeId: number; noteIds: number[] }) => {
      for (const noteId of noteIds) {
        await moveNote(noteId, nodeId)
      }
    },
    onSuccess: async () => {
      setMoveOpen(false)
      selection.clear()
      await queryClient.invalidateQueries({ queryKey: ['notes'] })
      await queryClient.invalidateQueries({ queryKey: ['tree'] })
    },
  })

  const deleteSelectedNotes = async () => {
    const noteIds = [...liveSelection.current].map((key) => Number(key))
    if (noteIds.length === 0) {
      return
    }
    const ok = await confirm({
      title: t('workspace.deleteSelection'),
      description: t('notes.confirmDeleteSelection', { count: noteIds.length }),
      confirmLabel: t('workspace.deleteSelection'),
      cancelLabel: t('common.cancel'),
      destructive: true,
    })
    if (!ok) {
      return
    }
    for (const noteId of noteIds) {
      remove.mutate(noteId)
    }
    selection.clear()
  }

  const allTags = (tags.data ?? []).map((entry) => entry.tag)

  const noteItems: Array<EntityItemEntry & { noteId: number }> = flatNotes.map((note) => ({
    key: String(note.id),
    noteId: note.id,
    title: note.title,
    icon: NotebookPen,
    meta: formatDate(note.updated_at),
    onClick: () => onOpenNote(note.id),
    trailing: <ScopeChip nodeId={note.node_id} courseId={courseId} titles={titles} />,
  }))

  const noteMenu = (item: EntityItemEntry & { noteId: number }): ContextMenuItem[] => {
    const multi = selection.selected.size > 1 && selection.selected.has(item.key)
    const items: ContextMenuItem[] = []
    if (!multi) {
      items.push({
        key: 'open',
        label: t('common.open'),
        onSelect: () => onOpenNote(item.noteId),
      })
      items.push({
        key: 'rename',
        label: t('common.rename'),
        onSelect: () => {
          const note = flatNotes.find((entry) => entry.id === item.noteId)
          setRenaming({ id: item.noteId, title: note?.title ?? '' })
        },
      })
    }
    items.push({
      key: 'move',
      label: t('workspace.moveToNode'),
      onSelect: () => {
        if (!selection.selected.has(item.key)) {
          selection.set([item.key])
        }
        setMoveOpen(true)
      },
    })
    if (multi) {
      items.push({
        key: 'delete-selection',
        label: t('workspace.deleteSelection'),
        danger: true,
        onSelect: deleteSelectedNotes,
      })
    } else {
      items.push({
        key: 'delete',
        label: t('notes.delete'),
        danger: true,
        onSelect: async () => {
          const note = flatNotes.find((entry) => entry.id === item.noteId)
          const ok = await confirm({
            title: t('notes.delete'),
            description: t('notes.confirmDelete', { title: note?.title ?? '' }),
            confirmLabel: t('notes.delete'),
            cancelLabel: t('common.cancel'),
            destructive: true,
          })
          if (ok) remove.mutate(item.noteId)
        },
      })
    }
    return items
  }

  return (
    <MarqueeSurface
      className="min-h-0 flex-1 space-y-3"
      selection={selection}
      clearBlocked={() => moveOpen || renaming !== null || paneMenu !== null}
      onContextMenu={(event) => {
        if (event.defaultPrevented) {
          return
        }
        const target = event.target as HTMLElement
        if (
          target.closest(
            '[data-selectable-id], button, input, textarea, select, a, [data-no-marquee]'
          ) !== null
        ) {
          return
        }
        event.preventDefault()
        setPaneMenu({ x: event.clientX, y: event.clientY })
      }}
    >
      <UndoDeleteNotice deletedItemId={undoItem} onDismiss={() => setUndoItem(null)} />
      <TabActionBar
        actions={[
          {
            label: t('workspace.newNoteHere'),
            icon: Plus,
            onAction: () => create.mutate(),
            pending: create.isPending,
            primary: true,
          },
          {
            label: t('chapter.draftNote'),
            icon: Sparkles,
            onAction: () => draft.mutate(),
            pending: draft.isPending,
            title: t('chapter.draftNoteHint'),
          },
        ]}
      />
      <ErrorBanner
        message={
          create.isError || draft.isError
            ? [create.error, draft.error]
                .filter((error) => error !== null)
                .map((error) => (error as Error).message)
                .join(' · ')
            : null
        }
      />

      <div className="flex items-center justify-end gap-2">
        <ExpandableSearch
          value={query}
          onChange={setQuery}
          onClear={() => setSubmitted('')}
          placeholder={t('notes.searchPlaceholder')}
          ariaLabel={t('notes.searchPlaceholder')}
          clearLabel={t('notes.clearSearch')}
          onSubmit={() => setSubmitted(query.trim())}
        />
        <ViewToggle view={view} onChange={setView} />
      </div>

      {allTags.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1" role="group" aria-label={t('notes.tagFilter')}>
          <button
            type="button"
            className={cn(
              'rounded-full px-2 py-0.5 text-[11px]',
              activeTag === null
                ? 'bg-primary/15 text-primary font-medium'
                : 'text-muted-foreground hover:bg-subtle'
            )}
            onClick={() => setActiveTag(null)}
          >
            {t('notes.allTags')}
          </button>
          {allTags.map((tag) => (
            <button
              key={tag}
              type="button"
              className={cn(
                'rounded-full px-2 py-0.5 text-[11px]',
                activeTag === tag
                  ? 'bg-primary/15 text-primary font-medium'
                  : 'text-muted-foreground hover:bg-subtle'
              )}
              onClick={() => setActiveTag(activeTag === tag ? null : tag)}
            >
              {tag}
            </button>
          ))}
        </div>
      ) : null}

      <div>
        {notes.data && flatNotes.length === 0 ? (
          submitted || activeTag ? (
            <p className="text-muted-foreground py-8 text-center text-sm">
              {t('workspace.noSearchResults')}
            </p>
          ) : (
            <EmptyState
              icon={NotebookPen}
              title={t('chapter.noNotes')}
              description={t('workspace.notesEmptyDesc')}
              action={
                <Button size="sm" disabled={create.isPending} onClick={() => create.mutate()}>
                  {create.isPending ? (
                    <Loader2 className="animate-spin" aria-hidden />
                  ) : (
                    <Plus aria-hidden />
                  )}
                  {t('workspace.firstNote')}
                </Button>
              }
            />
          )
        ) : (
          <EntityItems
            items={noteItems}
            layout={view}
            menuItems={noteMenu}
            selection={{
              isSelected: (key) => selection.selected.has(key),
              onPointerDown: (key, event) => selection.pointerDown(key, event),
            }}
            onDragStart={(event, item) =>
              buildDragPayload(event, {
                key: item.key,
                id: item.noteId,
                kind: 'note',
                selected: selection.selected,
                selectedPayload: { folderIds: [], materialIds: [], noteIds: selectedNoteIds },
                setSelection: (keys) => selection.set(keys),
                countLabel: (count) => t('drag.items', { count }),
              })
            }
          />
        )}
      </div>
      {moveOpen ? (
        <AssignToNodeDialog
          courseId={Number(courseId)}
          title={t('workspace.moveToNode')}
          countText={t('moveToNode.count', { count: selectedNoteIds.length })}
          confirmLabel={t('moveToNode.confirm')}
          onDone={(nodeId) =>
            moveNotes.mutateAsync({ nodeId, noteIds: selectedNoteIds })
          }
          onClose={() => setMoveOpen(false)}
        />
      ) : null}
      {renaming !== null ? (
        <RenameDialog
          title={t('notes.renameTitle')}
          initialName={renaming.title}
          onClose={() => setRenaming(null)}
          onConfirm={(title) =>
            rename.mutate({ id: renaming.id, title })
          }
        />
      ) : null}
      {notes.hasNextPage ? (
        <div className="flex justify-center">
          <Button
            variant="outline"
            size="sm"
            disabled={notes.isFetchingNextPage}
            onClick={() => void notes.fetchNextPage()}
          >
            {notes.isFetchingNextPage ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {t('notes.loadMore')}
          </Button>
        </div>
      ) : null}
      {paneMenu !== null ? (
        <ContextMenu
          x={paneMenu.x}
          y={paneMenu.y}
          items={[
            {
              key: 'new-note',
              label: t('workspace.newNoteHere'),
              onSelect: () => create.mutate(),
            },
            {
              key: 'draft-note',
              label: t('chapter.draftNote'),
              onSelect: () => draft.mutate(),
            },
          ]}
          onClose={() => setPaneMenu(null)}
        />
      ) : null}
      {confirmElement}
    </MarqueeSurface>
  )
}

function CoverageTab({
  courseId,
  currentId,
  workspace,
  titles,
}: {
  courseId: string
  currentId: number
  workspace: NonNullable<ReturnType<typeof useWorkspaceQuery>['data']>
  titles: Map<number, string>
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [pickerId, setPickerId] = useState<number | null>(null)
  const [draft, setDraft] = useState<ConceptDraft | null>(null)

  const graph = useQuery({
    queryKey: ['concepts', courseId],
    queryFn: () => conceptGraph(Number(courseId)),
  })

  const generate = useMutation({
    mutationFn: () => extractConcepts(Number(courseId)),
    onSuccess: (result) => setDraft(result),
  })

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['node-workspace', String(currentId)] })
    await queryClient.invalidateQueries({ queryKey: ['concepts', courseId] })
  }

  const add = useMutation({
    mutationFn: (conceptId: number) => addNodeConcept(currentId, conceptId),
    onSuccess: async () => {
      setPickerId(null)
      await refresh()
    },
  })
  const remove = useMutation({
    mutationFn: (conceptId: number) => removeNodeConcept(currentId, conceptId),
    onSuccess: () => void refresh(),
  })

  const pickable = (graph.data?.concepts ?? []).filter(
    (concept) => !concept.nodes.some((entry) => entry.node_id === currentId)
  )

  return (
    <div className="space-y-6">
      <TabActionBar
        actions={[
          {
            label: t('concepts.extract'),
            icon: Sparkles,
            onAction: () => generate.mutate(),
            pending: generate.isPending,
            primary: true,
          },
        ]}
        info={t('concepts.summary', {
          concepts: graph.data?.concepts.length ?? 0,
          links: graph.data?.links.length ?? 0,
        })}
      />
      <ErrorBanner message={generate.isError ? (generate.error as Error).message : null} />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t('workspace.coverageTitle')}</CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            {pickable.length > 0 ? (
              <select
                className="bg-surface border-border rounded-md border px-2 py-1.5 text-xs"
                value={pickerId ?? ''}
                aria-label={t('workspace.addCoverage')}
                onChange={(event) => {
                  const value = Number(event.target.value)
                  if (value) {
                    add.mutate(value)
                  }
                }}
              >
                <option value="">{t('workspace.addCoverage')}</option>
                {pickable.map((concept) => (
                  <option key={concept.id} value={concept.id}>
                    {concept.name}
                  </option>
                ))}
              </select>
            ) : null}
            {add.isError ? (
              <p className="text-danger text-xs">{(add.error as Error).message}</p>
            ) : null}
            {remove.isError ? (
              <p className="text-danger text-xs">{(remove.error as Error).message}</p>
            ) : null}
          </div>
        </CardHeader>
        <CardContent className="space-y-2">
          {workspace.concepts.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t('workspace.noCoverage')}</p>
          ) : (
            workspace.concepts.map((concept) => (
              <div
                key={concept.id}
                className="border-border bg-subtle/50 flex flex-wrap items-center gap-2 rounded-lg border p-3"
              >
                <span className="text-sm font-semibold">{concept.name}</span>
                {concept.node_ids.map((nodeId) => (
                  <ScopeChip key={nodeId} nodeId={nodeId} courseId={courseId} titles={titles} />
                ))}
                {concept.direct ? (
                  <Button
                    variant="outline"
                    size="sm"
                    className="ml-auto"
                    disabled={remove.isPending}
                    onClick={() => remove.mutate(concept.id)}
                  >
                    {remove.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
                    {t('workspace.coversNode')}
                  </Button>
                ) : (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="ml-auto"
                    disabled={add.isPending}
                    onClick={() => add.mutate(concept.id)}
                  >
                    {add.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Plus className="size-3.5" aria-hidden />}
                    {t('workspace.coverHere')}
                  </Button>
                )}
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <ConceptsPanel courseId={courseId} draft={draft} onDraftChange={setDraft} />
    </div>
  )
}

function TutorTab({
  currentId,
  nodeTitle,
  onAsk,
  askPending,
}: {
  currentId: number
  nodeTitle: string
  onAsk: (targetId: number, title: string) => void
  askPending: boolean
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const sessions = useQuery({
    queryKey: ['chat-sessions', 'node', currentId],
    queryFn: () => listChatSessions(currentId),
  })

  return (
    <div className="space-y-4">
      <TabActionBar
        actions={[
          {
            label: t('workspace.askAbout'),
            icon: MessageSquare,
            onAction: () => onAsk(currentId, nodeTitle),
            pending: askPending,
            primary: true,
          },
        ]}
      />
      <div className="space-y-1">
        {(sessions.data ?? []).length === 0 ? (
          <EmptyState
            icon={MessageSquare}
            title={t('workspace.noSessions')}
            description={t('workspace.tutorEmptyDesc')}
            action={
              <Button size="sm" disabled={askPending} onClick={() => onAsk(currentId, nodeTitle)}>
                {askPending ? (
                  <Loader2 className="animate-spin" aria-hidden />
                ) : (
                  <MessageSquare aria-hidden />
                )}
                {t('workspace.tutorStartChat')}
              </Button>
            }
          />
        ) : (
          (sessions.data ?? []).map((session) => (
            <button
              key={session.id}
              type="button"
              className="hover:bg-subtle flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm"
              onClick={() =>
                void navigate({ to: '/chat/$chatId', params: { chatId: session.public_id } })
              }
            >
              <MessageSquare className="text-muted-foreground size-4 shrink-0" aria-hidden />
              <span className="flex-1 truncate">{session.title}</span>
              <span className="text-muted-foreground shrink-0 text-xs">
                {t('chat.sessionLabel', { title: '', id: session.id })}
              </span>
            </button>
          ))
        )}
      </div>
    </div>
  )
}

function useWorkspaceQuery(nodeId: number | undefined) {
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
    note?: number
    material?: number
    study?: number | 'new'
    folder?: number
  }
  const navigate = useNavigate()
  const from = useCurrentOrigin()
  const queryClient = useQueryClient()
  const parsedTab = parseTab(search.tab)
  const [alongsidePickerFor, setAlongsidePickerFor] = useState<number | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(() => {
    try {
      return window.localStorage.getItem(storageKeys.treeSidebarOpen) !== '0'
    } catch {
      return true
    }
  })
  useEffect(() => {
    try {
      window.localStorage.setItem(storageKeys.treeSidebarOpen, sidebarOpen ? '1' : '0')
    } catch {
      // preference persistence is best-effort only
    }
  }, [sidebarOpen])

  const tree = useQuery({
    queryKey: ['tree', courseId],
    queryFn: () => courseTree(Number(courseId)),
  })
  const courseQuery = useQuery({
    queryKey: ['course', courseId],
    queryFn: () => getCourse(Number(courseId)),
  })
  const rootId = tree.data?.[0]?.id
  const currentId = nodeId !== undefined ? Number(nodeId) : rootId
  const workspace = useWorkspaceQuery(currentId)
  const currentNodeCounts = useMemo(
    () => (currentId !== undefined ? findNodeCounts(tree.data ?? [], currentId) : undefined),
    [tree.data, currentId]
  )
  const dueCards = currentNodeCounts?.cards_due

  const studyHere = useMutation({
    mutationFn: (targetId: number) =>
      generateQuiz({ course_id: Number(courseId), node_id: targetId, count: 8 }),
    onSuccess: async (activity) => {
      await queryClient.invalidateQueries({ queryKey: ['quizzes'] })
      void navigate({ to: '/quiz/$activityId', params: { activityId: String(activity.id) }, search: { from } })
    },
  })
  const [launcherNode, setLauncherNode] = useState<number | null>(null)
  const openChatSession = useChatStore((state) => state.openSession)
  const askAbout = useMutation({
    mutationFn: ({ targetId, title }: { targetId: number; title: string }) =>
      createChatSession(Number(courseId), targetId, title),
    onSuccess: async (session) => {
      await queryClient.invalidateQueries({ queryKey: ['chat-sessions'] })
      openChatSession({ id: session.id, publicId: session.public_id })
    },
  })
  const studyTargetId = studyHere.isPending ? (studyHere.variables ?? null) : null
  const askTargetId = askAbout.isPending ? (askAbout.variables?.targetId ?? null) : null

  const setTab = (next: WorkspaceTab) => {
    const nextSearch = { tab: next === 'overview' ? undefined : next }
    if (nodeId !== undefined) {
      void navigate({
        to: '/courses/$courseId/n/$nodeId',
        params: { courseId, nodeId },
        search: nextSearch,
      })
    } else {
      void navigate({ to: '/courses/$courseId', params: { courseId }, search: nextSearch })
    }
  }

  const openNoteAt = (noteId: number) => {
    const nextSearch = openNote(noteId)
    if (nodeId !== undefined) {
      void navigate({
        to: '/courses/$courseId/n/$nodeId',
        params: { courseId, nodeId },
        search: nextSearch,
      })
    } else {
      void navigate({ to: '/courses/$courseId', params: { courseId }, search: nextSearch })
    }
  }

  const closeOpenNote = () => {
    if (nodeId !== undefined) {
      void navigate({
        to: '/courses/$courseId/n/$nodeId',
        params: { courseId, nodeId },
        search: closeNote,
      })
    } else {
      void navigate({ to: '/courses/$courseId', params: { courseId }, search: closeNote })
    }
  }

  const openMaterialAt = (materialId: number) => {
    const nextSearch = (prev: { tab?: string; note?: number; material?: number; study?: number | 'new' }) => ({
      ...prev,
      material: materialId,
    })
    if (nodeId !== undefined) {
      void navigate({
        to: '/courses/$courseId/n/$nodeId',
        params: { courseId, nodeId },
        search: nextSearch,
      })
    } else {
      void navigate({ to: '/courses/$courseId', params: { courseId }, search: nextSearch })
    }
  }

  const closeOpenMaterial = () => {
    const nextSearch = (prev: { tab?: string; note?: number; material?: number; study?: number | 'new' }) => {
      const rest = { ...prev }
      delete rest.material
      return rest
    }
    if (nodeId !== undefined) {
      void navigate({
        to: '/courses/$courseId/n/$nodeId',
        params: { courseId, nodeId },
        search: nextSearch,
      })
    } else {
      void navigate({ to: '/courses/$courseId', params: { courseId }, search: nextSearch })
    }
  }

  const openFolderInView = (folderId: number) => {
    const nextSearch = (
      prev: {
        tab?: string
        note?: number
        material?: number
        study?: number | 'new'
        folder?: number
      },
    ) => ({ ...prev, tab: 'materials' as const, folder: folderId })
    if (nodeId !== undefined) {
      void navigate({
        to: '/courses/$courseId/n/$nodeId',
        params: { courseId, nodeId },
        search: nextSearch,
      })
    } else {
      void navigate({ to: '/courses/$courseId', params: { courseId }, search: nextSearch })
    }
  }

  const closeFolderView = () => {
    const nextSearch = (
      prev: {
        tab?: string
        note?: number
        material?: number
        study?: number | 'new'
        folder?: number
      },
    ) => {
      const rest = { ...prev }
      delete rest.folder
      return rest
    }
    if (nodeId !== undefined) {
      void navigate({
        to: '/courses/$courseId/n/$nodeId',
        params: { courseId, nodeId },
        search: nextSearch,
      })
    } else {
      void navigate({ to: '/courses/$courseId', params: { courseId }, search: nextSearch })
    }
  }

  const openStudyAt = (materialId: number) => {
    const nextSearch = (prev: { tab?: string; note?: number; material?: number; study?: number | 'new' }) => ({
      ...prev,
      material: materialId,
      study: 'new' as const,
    })
    if (nodeId !== undefined) {
      void navigate({
        to: '/courses/$courseId/n/$nodeId',
        params: { courseId, nodeId },
        search: nextSearch,
      })
    } else {
      void navigate({ to: '/courses/$courseId', params: { courseId }, search: nextSearch })
    }
  }

  const studyNoteCreated = (noteId: number) => {
    const nextSearch = (prev: { tab?: string; note?: number; material?: number; study?: number | 'new' }) => ({
      ...prev,
      study: noteId,
    })
    if (nodeId !== undefined) {
      void navigate({
        to: '/courses/$courseId/n/$nodeId',
        params: { courseId, nodeId },
        search: nextSearch,
      })
    } else {
      void navigate({ to: '/courses/$courseId', params: { courseId }, search: nextSearch })
    }
  }

  const studyAlongside = (noteId: number, materialId: number) => {
    const nextSearch = (prev: { tab?: string; note?: number; material?: number; study?: number | 'new' }) => {
      const rest = { ...prev }
      delete rest.note
      return { ...rest, material: materialId, study: noteId }
    }
    if (nodeId !== undefined) {
      void navigate({
        to: '/courses/$courseId/n/$nodeId',
        params: { courseId, nodeId },
        search: nextSearch,
      })
    } else {
      void navigate({ to: '/courses/$courseId', params: { courseId }, search: nextSearch })
    }
  }

  const closeStudy = () => {
    const nextSearch = (prev: { tab?: string; note?: number; material?: number; study?: number | 'new' }) => {
      const rest = { ...prev }
      delete rest.material
      delete rest.study
      return rest
    }
    if (nodeId !== undefined) {
      void navigate({
        to: '/courses/$courseId/n/$nodeId',
        params: { courseId, nodeId },
        search: nextSearch,
      })
    } else {
      void navigate({ to: '/courses/$courseId', params: { courseId }, search: nextSearch })
    }
  }

  const closeNotes = () => {
    const nextSearch = (prev: { tab?: string; note?: number; material?: number; study?: number | 'new' }) => {
      const rest = { ...prev }
      delete rest.study
      return rest
    }
    if (nodeId !== undefined) {
      void navigate({
        to: '/courses/$courseId/n/$nodeId',
        params: { courseId, nodeId },
        search: nextSearch,
      })
    } else {
      void navigate({ to: '/courses/$courseId', params: { courseId }, search: nextSearch })
    }
  }

  const onNoteCreated = async (noteId: number) => {
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
        {sidebarOpen ? (
          <NodeTreeSidebar
            courseId={courseId}
            currentId={currentId}
            tab={effectiveTab}
            courseOrigin={courseQuery.data?.origin ?? null}
          />
        ) : null}
        <div className="mx-auto flex min-w-0 max-w-5xl flex-1 flex-col space-y-4 self-stretch p-8">
      <header className="flex flex-wrap items-center gap-x-2 gap-y-2">
        <Button
          variant="ghost"
          size="icon"
          className="hidden md:inline-flex"
          title={t('workspace.toggleTree')}
          aria-pressed={sidebarOpen}
          onClick={() => setSidebarOpen((current) => !current)}
        >
          {sidebarOpen ? <PanelLeftClose aria-hidden /> : <PanelLeftOpen aria-hidden />}
        </Button>
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
      {search.note !== undefined ? (
        <NoteEditorDrawer
          noteId={search.note}
          onClose={closeOpenNote}
          onStudyAlongside={() => setAlongsidePickerFor(search.note!)}
        />
      ) : null}
      {search.material !== undefined && search.study !== undefined ? (
        <SplitStudyPane
          courseId={Number(courseId)}
          materialId={search.material}
          study={search.study}
          onNoteCreated={studyNoteCreated}
          onClose={closeStudy}
          onCloseNotes={closeNotes}
        />
      ) : null}
      {search.material !== undefined && search.study === undefined ? (
        <MaterialDetailDrawer
          materialId={search.material}
          onClose={closeOpenMaterial}
          onTakeNotes={() => openStudyAt(search.material!)}
        />
      ) : null}
      {alongsidePickerFor !== null ? (
        <MaterialPickerDialog
          courseId={Number(courseId)}
          nodeId={currentId}
          nodeTitle={node.title}
          assignedIds={new Set<number>()}
          mode="select"
          onClose={() => setAlongsidePickerFor(null)}
          onSelect={(ids) => {
            const picked = ids[0]
            setAlongsidePickerFor(null)
            if (picked !== undefined) {
              studyAlongside(alongsidePickerFor, picked)
            }
          }}
        />
      ) : null}
      {launcherNode !== null && rootId !== undefined ? (
        <StudyLauncherDialog
          courseId={Number(courseId)}
          nodeId={launcherNode}
          rootNodeId={rootId}
          onClose={() => setLauncherNode(null)}
          onNoteCreated={onNoteCreated}
        />
      ) : null}
    </>
  )
}
