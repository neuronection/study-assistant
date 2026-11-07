import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'
import {Loader2, Plus, Sparkles} from 'lucide-react'
import {useState} from 'react'
import {useTranslation} from 'react-i18next'
import {Button} from '@/components/ui/button'
import {Card, CardContent, CardHeader, CardTitle} from '@/components/ui/card'
import {ErrorBanner} from '@/components/ErrorBanner'
import {TabActionBar} from '@/components/layout/TabActionBar'
import {addNodeConcept, conceptGraph, extractConcepts, removeNodeConcept, type ConceptDraft} from '@/lib/api'
import {ConceptsPanel} from '../ConceptsPanel'
import { ScopeChip, type WorkspaceData } from './shared'

export function CoverageTab({
  courseId,
  currentId,
  workspace,
  titles,
}: {
  courseId: string
  currentId: string
  workspace: WorkspaceData
  titles: Map<string, string>
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [pickerId, setPickerId] = useState<string | null>(null)
  const [draft, setDraft] = useState<ConceptDraft | null>(null)

  const graph = useQuery({
    queryKey: ['concepts', courseId],
    queryFn: () => conceptGraph(courseId),
  })

  const generate = useMutation({
    mutationFn: () => extractConcepts(courseId),
    onSuccess: (result) => setDraft(result),
  })

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['node-workspace', String(currentId)] })
    await queryClient.invalidateQueries({ queryKey: ['concepts', courseId] })
  }

  const add = useMutation({
    mutationFn: (conceptId: string) => addNodeConcept(currentId, conceptId),
    onSuccess: async () => {
      setPickerId(null)
      await refresh()
    },
  })
  const remove = useMutation({
    mutationFn: (conceptId: string) => removeNodeConcept(currentId, conceptId),
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
                  const value = event.target.value
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

