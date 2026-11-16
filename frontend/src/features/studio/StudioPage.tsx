import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import {
  FileText,
  Loader2,
  Presentation,
  Printer,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { BlockRenderer } from '@/components/blocks/BlockRenderer'
import type { Block } from '@/components/blocks/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorBanner } from '@/components/ErrorBanner'
import {
  createStudioArtifact,
  deleteStudioArtifact,
  listMaterials,
  listStudioArtifacts,
  type Material,
  type StudioArtifact,
} from '@/lib/api'
import { useCloseFloatings } from '@/lib/ui-overlays'
import { useConfirm } from '@/lib/use-confirm'
import { useWorkspaceStore } from '@/lib/workspace-store'
import { cn } from '@/lib/utils'

function textBlock(md: string): Block[] {
  return [{ type: 'text', md }] as Block[]
}

function StudioCreateDialog({
  materials,
  onClose,
  onCreated,
}: {
  materials: Material[]
  onClose: () => void
  onCreated: (artifact: StudioArtifact) => void
}) {
  useCloseFloatings()
  const { t } = useTranslation()
  const [materialId, setMaterialId] = useState(materials[0]?.id ?? '')
  const [kind, setKind] = useState<'slide_deck' | 'handout'>('slide_deck')
  const [title, setTitle] = useState('')
  const create = useMutation({
    mutationFn: () =>
      createStudioArtifact({
        material_id: materialId,
        kind,
        title: title.trim() || null,
      }),
    onSuccess: (artifact) => {
      onCreated(artifact)
      onClose()
    },
  })

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={t('studio.createTitle')}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose()
        }
      }}
    >
      <div className="bg-surface border-border flex w-full max-w-lg flex-col rounded-lg border shadow-[var(--as-shadow-3)]">
        <header className="border-border flex items-center justify-between border-b px-4 py-2">
          <h2 className="text-sm font-semibold">{t('studio.createTitle')}</h2>
          <button
            type="button"
            aria-label={t('chat.close')}
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground rounded p-1"
          >
            <X className="size-4" aria-hidden />
          </button>
        </header>
        <div className="space-y-3 p-4">
          <label className="block space-y-1 text-xs">
            <span className="text-muted-foreground">{t('studio.sourceMaterial')}</span>
            <select
              value={materialId}
              onChange={(event) => setMaterialId(event.target.value)}
              className="bg-surface border-border w-full rounded-md border px-2 py-1.5 text-sm"
            >
              {materials.map((material) => (
                <option key={material.id} value={material.id}>
                  {material.title}
                </option>
              ))}
            </select>
          </label>
          <label className="block space-y-1 text-xs">
            <span className="text-muted-foreground">{t('studio.titleLabel')}</span>
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder={t('studio.titlePlaceholder')}
              className="bg-surface border-border w-full rounded-md border px-2 py-1.5 text-sm"
            />
          </label>
          <div className="space-y-1 text-xs">
            <span className="text-muted-foreground">{t('studio.kind')}</span>
            <div className="flex gap-1">
              {(['slide_deck', 'handout'] as const).map((entry) => (
                <button
                  key={entry}
                  type="button"
                  aria-pressed={kind === entry}
                  onClick={() => setKind(entry)}
                  className={cn(
                    'rounded-full border px-3 py-1',
                    kind === entry
                      ? 'border-primary bg-primary text-primary-foreground'
                      : 'border-border hover:bg-subtle',
                  )}
                >
                  {t(`studio.kind.${entry}`)}
                </button>
              ))}
            </div>
          </div>
          {materials.length === 0 ? (
            <p className="text-muted-foreground text-xs">{t('studio.noSources')}</p>
          ) : null}
          <ErrorBanner message={create.isError ? (create.error as Error).message : null} />
        </div>
        <footer className="border-border flex items-center justify-end border-t px-4 py-2">
          <Button
            size="sm"
            disabled={!materialId || create.isPending}
            onClick={() => create.mutate()}
          >
            {create.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {t('studio.create')}
          </Button>
        </footer>
      </div>
    </div>
  )
}

function StudioViewer({ artifact, onClose }: { artifact: StudioArtifact; onClose: () => void }) {
  useCloseFloatings()
  const { t } = useTranslation()
  const slides = artifact.spec.slides ?? []
  const pageSize = artifact.kind === 'slide_deck' ? '16in 9in' : 'A4'
  return (
    <div
      className="fixed inset-0 z-50 overflow-y-auto bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={artifact.title}
    >
      <style>{`
        @media print {
          body * { visibility: hidden; }
          #studio-print, #studio-print * { visibility: visible; }
          #studio-print { position: absolute; inset: 0; background: white; color: black; }
          #studio-print .studio-page { break-after: page; box-shadow: none !important; border: none !important; }
          @page { size: ${pageSize}; margin: 0; }
        }
      `}</style>
      <div className="mx-auto max-w-5xl space-y-3">
        <div className="flex items-center justify-between gap-2 text-white">
          <h2 className="text-sm font-semibold">{artifact.title}</h2>
          <div className="flex gap-1">
            <Button variant="secondary" size="sm" onClick={() => window.print()}>
              <Printer className="size-3.5" aria-hidden />
              {t('studio.print')}
            </Button>
            <Button variant="secondary" size="icon" aria-label={t('chat.close')} onClick={onClose}>
              <X className="size-4" aria-hidden />
            </Button>
          </div>
        </div>
        <div id="studio-print" className="space-y-3">
          {slides.map((slide, index) => (
            <section
              key={`${slide.title}-${index}`}
              className={cn(
                'studio-page bg-white text-black shadow-xl',
                artifact.kind === 'slide_deck'
                  ? 'flex aspect-video flex-col justify-center p-10'
                  : 'min-h-[29.7cm] p-12',
              )}
            >
              <h3
                className={cn(
                  'font-semibold',
                  artifact.kind === 'slide_deck' ? 'text-3xl' : 'text-xl',
                  slide.layout === 'title' && 'text-center text-4xl',
                )}
              >
                {slide.title}
              </h3>
              {slide.bullets && slide.bullets.length > 0 ? (
                <ul className="mt-6 list-disc space-y-3 pl-6 text-lg">
                  {slide.bullets.map((bullet) => (
                    <li key={bullet}>
                      <BlockRenderer blocks={textBlock(bullet)} />
                    </li>
                  ))}
                </ul>
              ) : null}
              {slide.body_md ? (
                <div className="mt-4">
                  <BlockRenderer blocks={textBlock(slide.body_md)} />
                </div>
              ) : null}
            </section>
          ))}
        </div>
      </div>
    </div>
  )
}

export function StudioPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const courseId = useWorkspaceStore((state) => state.courseId)
  const [creating, setCreating] = useState(false)
  const [viewing, setViewing] = useState<StudioArtifact | null>(null)
  const [confirm, confirmElement] = useConfirm()

  const artifacts = useQuery({
    queryKey: ['studio-artifacts', courseId],
    queryFn: () => listStudioArtifacts(courseId ?? undefined),
  })
  const materials = useQuery({
    queryKey: ['materials', 'studio', courseId],
    queryFn: () => listMaterials(undefined, courseId ?? undefined),
    enabled: courseId !== null,
  })
  const remove = useMutation({
    mutationFn: (id: string) => deleteStudioArtifact(id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['studio-artifacts'] })
    },
  })

  const sources = (materials.data ?? []).filter((material) => material.has_extraction)

  const askDelete = async (artifact: StudioArtifact) => {
    const ok = await confirm({
      title: t('studio.deleteTitle'),
      description: t('studio.deleteBody', { title: artifact.title }),
      confirmLabel: t('common.delete'),
      cancelLabel: t('common.cancel'),
      destructive: true,
    })
    if (ok) {
      remove.mutate(artifact.id)
    }
  }

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6 p-4 md:p-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold">
            <Presentation className="text-primary size-5" aria-hidden />
            {t('studio.title')}
          </h1>
          <p className="text-muted-foreground mt-1 max-w-2xl text-sm">{t('studio.subtitle')}</p>
        </div>
        <Button
          size="sm"
          disabled={courseId === null || sources.length === 0}
          onClick={() => setCreating(true)}
        >
          <Sparkles className="size-3.5" aria-hidden />
          {t('studio.new')}
        </Button>
      </header>

      {courseId === null ? (
        <Card>
          <CardContent className="p-6">
            <EmptyState title={t('studio.pickCourse')} />
            <div className="mt-3 text-center">
              <Link to="/courses" className="text-primary text-sm underline">
                {t('studio.openCourses')}
              </Link>
            </div>
          </CardContent>
        </Card>
      ) : (
        <>
          <ErrorBanner
            message={artifacts.isError ? (artifacts.error as Error).message : null}
          />
          {artifacts.data && artifacts.data.length === 0 ? (
            <EmptyState title={t('studio.empty')} />
          ) : (
            <ul className="grid gap-3 sm:grid-cols-2">
              {(artifacts.data ?? []).map((artifact) => (
                <li key={artifact.id}>
                  <Card className="h-full">
                    <CardHeader className="pb-2">
                      <CardTitle className="flex items-center gap-2 text-sm">
                        {artifact.kind === 'slide_deck' ? (
                          <Presentation className="text-primary size-4" aria-hidden />
                        ) : (
                          <FileText className="text-primary size-4" aria-hidden />
                        )}
                        {artifact.title}
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <p className="text-muted-foreground text-xs">
                        {t(`studio.kind.${artifact.kind}`)} ·{' '}
                        {t('studio.slideCount', {
                          count: artifact.spec.slides?.length ?? 0,
                        })}
                      </p>
                      <div className="flex flex-wrap gap-1">
                        <Button variant="outline" size="sm" onClick={() => setViewing(artifact)}>
                          {t('studio.open')}
                        </Button>
                        {artifact.material_id ? (
                          <Button variant="ghost" size="sm" asChild>
                            <Link to="/library/$materialId" params={{ materialId: artifact.material_id }}>
                              {t('studio.openMaterial')}
                            </Link>
                          </Button>
                        ) : null}
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={t('studio.deleteFor', { title: artifact.title })}
                          onClick={() => void askDelete(artifact)}
                        >
                          <Trash2 className="size-3.5" aria-hidden />
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      {creating && courseId !== null ? (
        <StudioCreateDialog
          materials={sources}
          onClose={() => setCreating(false)}
          onCreated={(artifact) => {
            void queryClient.invalidateQueries({ queryKey: ['studio-artifacts'] })
            setViewing(artifact)
          }}
        />
      ) : null}
      {viewing ? <StudioViewer artifact={viewing} onClose={() => setViewing(null)} /> : null}
      {confirmElement}
    </div>
  )
}
