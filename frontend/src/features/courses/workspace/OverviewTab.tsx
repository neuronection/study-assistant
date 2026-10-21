import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'
import {Link} from '@tanstack/react-router'
import {BookOpen, ClipboardList, FolderClosed, GitBranch, Loader2, MessageSquare, Plus, ScrollText, Sparkles, X} from 'lucide-react'
import {useState} from 'react'
import {useTranslation} from 'react-i18next'
import {BlockRenderer} from '@/components/blocks/BlockRenderer'
import type {Block} from '@/components/blocks/types'
import {Button} from '@/components/ui/button'
import {Card, CardContent, CardHeader, CardTitle} from '@/components/ui/card'
import {ErrorBanner} from '@/components/ErrorBanner'
import {TabActionBar, type TabAction} from '@/components/layout/TabActionBar'
import {type PopoverMenuItem} from '@/components/ui/popover-menu'
import {GenerateDialog as AIGenerateDialog} from '@/features/ai/GenerateDialog'
import {addNode, getMaterial, getNodeArtifacts, outlineCommit, outlineDraft, reviewNode, type ComposeKind, type Material, type NodeInfo, type OrganizerFinding, type OutlineDraftChapter, type WorkspaceChild} from '@/lib/api'
import {NodeRecentStrip} from '@/features/courses/NodeRecentStrip'
import type { WorkspaceData } from './shared'

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
  studyTargetId: string | null
  askTargetId: string | null
  onPractice: (childId: string) => void
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
    mutationFn: () => outlineCommit(courseId, chapters),
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
  nodeId: string
  courseId: string
  onOpenMaterial: (materialId: string) => void
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
    mutationFn: (materialId: string) => getMaterial(materialId),
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
          courseId={courseId}
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


export function OverviewTab({
  courseId,
  currentId,
  isRoot,
  workspace,
  tree,
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
  currentId: string
  isRoot: boolean
  workspace: WorkspaceData
  tree: NodeInfo[] | undefined
  onPractice: (nodeId: string) => void
  onAsk: (child: WorkspaceChild) => void
  studyTargetId: string | null
  askTargetId: string | null
  onOpenMaterial: (materialId: string) => void
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
    mutationFn: () => addNode(courseId, currentId, title.trim()),
    onSuccess: async () => {
      setAdding(false)
      setTitle('')
      await queryClient.invalidateQueries({ queryKey: ['tree', courseId] })
      await queryClient.invalidateQueries({ queryKey: ['node-workspace', String(currentId)] })
    },
  })

  const generateDraft = useMutation({
    mutationFn: () => outlineDraft(courseId),
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

      {isRoot ? <NodeRecentStrip courseId={courseId} tree={tree} /> : null}

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

