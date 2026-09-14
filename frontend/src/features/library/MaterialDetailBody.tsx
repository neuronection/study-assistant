import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from '@tanstack/react-router'
import {
  FileDown,
  FileOutput,
  History,
  MoreHorizontal,
  NotebookPen,
  Printer,
  RefreshCw,
  Star,
  X,
} from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { InfoButton } from '@/components/ui/InfoButton'
import { ReExtractDialog } from '@/components/materials/ReExtractDialog'
import { exportMarkdownWithDrawings } from '@/components/materials/exportMarkdown'
import { MarkdownPrintDoc } from '@/components/print/MarkdownPrintDoc'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { PopoverMenu } from '@/components/ui/popover-menu'
import { cn } from '@/lib/utils'
import {
  deriveMaterial,
  getMaterial,
  getMaterialLinks,
  listCourses,
  listStudyStates,
  patchMaterial,
  setStudyState,
} from '@/lib/api'

import { AskAiPopover } from './AskAiPopover'
import { ExtractionHistoryDialog } from './ExtractionHistoryDialog'
import { ExtractionView } from './ExtractionView'
import { OriginalView } from './OriginalView'
import { RawTextView } from './RawTextView'
import { StudyStateMenu, type StudyStatus } from './StudyStateMenu'
import { ViewMenu } from './ViewMenu'
import { isTextMaterial } from './textMaterial'
import { StudyPaneHeader } from '@/components/layout/StudyPaneHeader'

export type DetailTab =
  | 'extraction'
  | 'original'
  | 'side-by-side'
  | 'formatted'
  | 'raw'
  | 'description'

export const DETAIL_TABS: DetailTab[] = [
  'extraction',
  'original',
  'side-by-side',
  'formatted',
  'raw',
  'description',
]

const TEXT_TABS: DetailTab[] = ['formatted', 'raw']
const EXTRACTION_TABS: DetailTab[] = ['extraction', 'original', 'side-by-side']

export function MaterialDetailBody({
  materialId,
  activeTab,
  onTabChange,
  showTitle = true,
  onTakeNotes,
  onQuoteSelection,
  onClose,
  closeLabel,
}: {
  materialId: number
  activeTab: DetailTab
  onTabChange: (tab: DetailTab) => void
  showTitle?: boolean
  onTakeNotes?: () => void
  onQuoteSelection?: (text: string) => void
  onClose?: () => void
  closeLabel?: string
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [printing, setPrinting] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [reExtractOpen, setReExtractOpen] = useState(false)
  const [derived, setDerived] = useState<{
    id: number
    title: string
    deduped: boolean
  } | null>(null)

  const detail = useQuery({
    queryKey: ['material', materialId],
    queryFn: () => getMaterial(materialId),
  })
  const links = useQuery({
    queryKey: ['material-links', materialId],
    queryFn: () => getMaterialLinks(materialId),
  })
  const courses = useQuery({ queryKey: ['courses'], queryFn: listCourses })
  const states = useQuery({ queryKey: ['study-states'], queryFn: listStudyStates })

  const material = detail.data?.material
  const course = (courses.data ?? []).find((entry) => entry.id === material?.course_id)
  const rawStatus = states.data?.[String(materialId)]?.status
  const status: StudyStatus =
    rawStatus === 'reading' || rawStatus === 'studied' ? rawStatus : 'unread'
  const scopeNodeId =
    links.data?.find((link) => !link.is_course_level)?.node_id ?? links.data?.[0]?.node_id
  const textMaterial = material !== undefined && isTextMaterial(material)
  const views = textMaterial ? TEXT_TABS : EXTRACTION_TABS
  const active: DetailTab = views.includes(activeTab)
    ? activeTab
    : textMaterial
      ? 'formatted'
      : 'extraction'

  const setState = useMutation({
    mutationFn: (next: StudyStatus) => setStudyState(materialId, next),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['study-states'] })
    },
  })

  const star = useMutation({
    mutationFn: (starred: boolean) => patchMaterial(materialId, { starred }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['material', materialId] })
      await queryClient.invalidateQueries({ queryKey: ['materials'] })
    },
  })

  const saveTags = useMutation({
    mutationFn: (tags: string[]) => patchMaterial(materialId, { tags }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['material', materialId] })
      await queryClient.invalidateQueries({ queryKey: ['materials'] })
    },
  })
  const [tagDraft, setTagDraft] = useState<string | null>(null)

  const exportMd = useMutation({
    mutationFn: async () => {
      const current = detail.data
      if (current === undefined) {
        return
      }
      const extraction = current.extraction
      if (extraction === null) {
        return
      }
      const resolved = await exportMarkdownWithDrawings(extraction.markdown, current.drawings)
      const safeTitle =
        current.material.title.replace(/[^\w\s-]/g, '').trim() || 'material'
      const blob = new Blob([resolved], { type: 'text/markdown' })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `${safeTitle}.md`
      anchor.click()
      URL.revokeObjectURL(url)
    },
  })

  const derive = useMutation({
    mutationFn: () => deriveMaterial(materialId, { nodeId: scopeNodeId ?? null }),
    onSuccess: async (result) => {
      setDerived({
        id: result.material.id,
        title: result.material.title,
        deduped: result.deduped,
      })
      await queryClient.invalidateQueries({ queryKey: ['materials'] })
      await queryClient.invalidateQueries({ queryKey: ['tree'] })
      await queryClient.invalidateQueries({ queryKey: ['node-workspace'] })
    },
  })

  if (detail.isLoading) {
    return (
      <p className="text-muted-foreground p-8 text-sm">{t('library.loading')}</p>
    )
  }
  if (!material) {
    return <p className="text-muted-foreground p-8 text-sm">{t('library.materialMissing')}</p>
  }

  const deriveFeedback = derived ? (
    <div className="bg-subtle border-border flex items-center justify-between gap-2 rounded-md border p-2 text-xs">
      <p>
        {derived.deduped
          ? t('library.deriveDuplicate')
          : t('library.deriveSuccess', { title: derived.title })}
      </p>
      <div className="flex items-center gap-1">
        <Button
          variant="ghost"
          size="sm"
          onClick={() =>
            navigate({
              to: '/library/$materialId',
              params: { materialId: String(derived.id) },
            })
          }
        >
          {t('library.deriveOpen')}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          aria-label={t('library.deriveDismiss')}
          onClick={() => setDerived(null)}
        >
          <X aria-hidden />
        </Button>
      </div>
    </div>
  ) : derive.isError ? (
    <p className="text-warning text-xs" role="alert">
      {t('library.deriveFailed')}
    </p>
  ) : null

  const printOverlay =
    printing && detail.data?.extraction ? (
      <div className="bg-background fixed inset-0 z-50 overflow-auto p-4">
        <MarkdownPrintDoc
          title={material.title}
          markdown={detail.data.extraction.markdown}
          autoPrint={false}
          onBack={() => setPrinting(false)}
        />
      </div>
    ) : null

  return (
    <>
      {printOverlay}
      {historyOpen ? (
        <ExtractionHistoryDialog
          materialId={materialId}
          onClose={() => setHistoryOpen(false)}
        />
      ) : null}
      <ReExtractDialog
        materialId={materialId}
        open={reExtractOpen}
        onClose={() => setReExtractOpen(false)}
      />
      <StudyPaneHeader
        title={showTitle ? material.title : null}
        meta={
          <>
            <span
              className={cn(
                'rounded-full px-2 py-0.5 text-[11px]',
                material.status === 'ready' && 'bg-success/15 text-success',
                material.status === 'failed' && 'bg-danger/15 text-danger',
                (material.status === 'pending' || material.status === 'processing') &&
                  'bg-warning/15 text-warning'
              )}
            >
              {material.status}
            </span>
            {course ? (
              <span className="bg-subtle text-muted-foreground rounded-full px-2 py-0.5 text-[11px]">
                {course.title}
              </span>
            ) : null}
            {(material.tags ?? []).map((tag) => (
              <span
                key={tag}
                className="bg-subtle text-muted-foreground group flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px]"
              >
                {tag}
                <button
                  type="button"
                  className="opacity-60 group-hover:opacity-100"
                  title={t('notes.removeTag')}
                  onClick={() =>
                    saveTags.mutate((material.tags ?? []).filter((entry) => entry !== tag))
                  }
                >
                  <X className="size-3" aria-hidden />
                </button>
              </span>
            ))}
            {tagDraft === null ? (
              <button
                type="button"
                className="text-muted-foreground hover:text-foreground text-[11px] underline"
                onClick={() => setTagDraft('')}
              >
                {t('notes.addTag')}
              </button>
            ) : (
              <form
                onSubmit={(event) => {
                  event.preventDefault()
                  const next = tagDraft.trim().toLowerCase()
                  if (next && !(material.tags ?? []).includes(next)) {
                    saveTags.mutate([...(material.tags ?? []), next])
                  } else {
                    setTagDraft(null)
                  }
                }}
              >
                <input
                  autoFocus
                  className="bg-surface border-border w-28 rounded-full border px-2 py-0.5 text-[11px]"
                  value={tagDraft}
                  placeholder={t('notes.addTag')}
                  onChange={(event) => setTagDraft(event.target.value)}
                  onBlur={() => setTagDraft(null)}
                />
              </form>
            )}
            {(links.data ?? []).map((link) => {
              const where =
                link.breadcrumb
                  .slice(1)
                  .map((crumb) => crumb.title)
                  .join(' · ') || link.owner_title
              const label = link.via_folder
                ? t('library.assignedViaFolderChip', {
                    folder: link.via_folder.name,
                    where,
                  })
                : t('library.assignedChip', { where })
              const chipTitle = link.via_folder
                ? `${link.via_folder.name} › ${link.breadcrumb.map((crumb) => crumb.title).join(' › ')}`
                : (link.rationale ?? link.breadcrumb.map((crumb) => crumb.title).join(' › '))
              const key = `${link.node_id}-${link.via_folder?.id ?? 'direct'}`
              return link.is_course_level ? (
                <span
                  key={key}
                  className="bg-primary/10 text-primary rounded-full px-2 py-0.5 text-[11px]"
                  title={chipTitle}
                >
                  {label}
                </span>
              ) : (
                <Link
                  key={key}
                  to="/courses/$courseId/n/$nodeId"
                  params={{
                    courseId: String(material.course_id),
                    nodeId: String(link.node_id),
                  }}
                  className="bg-primary/10 text-primary hover:bg-primary/20 rounded-full px-2 py-0.5 text-[11px]"
                  title={chipTitle}
                >
                  {label}
                </Link>
              )
            })}
            {material.description ? (
              <InfoButton
                label={t('library.descriptionInfo')}
                title={t('library.descriptionInfo')}
                showOnHover={false}
                className="opacity-100"
              >
                <span className="whitespace-pre-wrap">{material.description}</span>
              </InfoButton>
            ) : null}
          </>
        }
        tabs={
          <ViewMenu
            label={t('library.viewMenu')}
            value={active}
            views={views.map((view) => ({
              value: view,
              label: t(`library.tab_${view.replaceAll('-', '_')}`),
            }))}
            onChange={(next) => onTabChange(next as DetailTab)}
          />
        }
        primary={
          <>
            {detail.data?.extraction ? (
              <AskAiPopover
                material={material}
                scopeNodeId={scopeNodeId}
                kind={material.kind}
              />
            ) : null}
            {onTakeNotes ? (
              <Button variant="outline" size="sm" onClick={onTakeNotes}>
                <NotebookPen className="size-3.5" aria-hidden />
                {t('library.takeNotes')}
              </Button>
            ) : null}
            <Button
              variant="ghost"
              size="sm"
              title={material.starred ? t('library.unstarOne') : t('library.starOne')}
              disabled={star.isPending}
              onClick={() => star.mutate(!material.starred)}
            >
              <Star
                className={cn('size-4', material.starred && 'fill-warning text-warning')}
                aria-hidden
              />
            </Button>
            <StudyStateMenu
              status={status}
              pending={setState.isPending}
              onChange={(next) => setState.mutate(next)}
            />
          </>
        }
        overflow={
          detail.data?.extraction ? (
            <PopoverMenu
              label={t('library.moreMaterialActions')}
              trigger={<MoreHorizontal className="size-4" aria-hidden />}
              items={[
                {
                  key: 'export',
                  label: t('library.exportMarkdown'),
                  icon: FileDown,
                  pending: exportMd.isPending,
                  onSelect: () => exportMd.mutate(),
                },
                {
                  key: 'print',
                  label: t('library.printDoc'),
                  icon: Printer,
                  onSelect: () => setPrinting(true),
                },
                {
                  key: 'derive',
                  label: t('library.deriveMaterial'),
                  icon: FileOutput,
                  pending: derive.isPending,
                  onSelect: () => derive.mutate(),
                },
                ...((detail.data?.material.reextract_modes?.length ?? 1) > 1
                  ? [
                      {
                        key: 're-extract',
                        label: t('reextract.menuEntry'),
                        icon: RefreshCw,
                        onSelect: () => setReExtractOpen(true),
                      },
                    ]
                  : []),
                ...(material.provenance?.kind === 'mindmap'
                  ? []
                  : [
                      {
                        key: 'history',
                        label: t('library.extractionHistory'),
                        icon: History,
                        onSelect: () => setHistoryOpen(true),
                      },
                    ]),
              ]}
            />
          ) : null
        }
        onClose={onClose}
        closeLabel={closeLabel}
      />

      {deriveFeedback}

      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
        {active === 'extraction' || active === 'formatted' ? (
          <ExtractionView
            materialId={materialId}
            scopeNodeId={scopeNodeId}
            onQuoteSelection={onQuoteSelection}
          />
        ) : null}
        {active === 'original' ? <OriginalView materialId={materialId} /> : null}
        {active === 'raw' ? <RawTextView materialId={materialId} /> : null}
        {active === 'side-by-side' ? (
          <div className="grid grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">{t('library.original')}</CardTitle>
              </CardHeader>
              <CardContent>
                <OriginalView materialId={materialId} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">{t('library.extraction')}</CardTitle>
              </CardHeader>
              <CardContent>
                <ExtractionView
                  materialId={materialId}
                  scopeNodeId={scopeNodeId}
                  onQuoteSelection={onQuoteSelection}
                />
              </CardContent>
            </Card>
          </div>
        ) : null}
      </div>
    </>
  )
}
