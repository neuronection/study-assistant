import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Network, Sparkles, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { commitConcepts, conceptGraph, type ConceptDraft } from '@/lib/api'
import { cn } from '@/lib/utils'

export function ConceptsPanel({
  courseId,
  draft,
  onDraftChange,
}: {
  courseId: string
  draft: ConceptDraft | null
  onDraftChange: (draft: ConceptDraft | null) => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const graph = useQuery({
    queryKey: ['concepts', courseId],
    queryFn: () => conceptGraph(Number(courseId)),
  })

  const commit = useMutation({
    mutationFn: () => commitConcepts(Number(courseId), draft!),
    onSuccess: async () => {
      onDraftChange(null)
      await queryClient.invalidateQueries({ queryKey: ['concepts', courseId] })
    },
  })

  const removeConcept = (name: string) => {
    if (draft === null) {
      return
    }
    onDraftChange({
      concepts: draft.concepts.filter((entry) => entry.name !== name),
      links: draft.links.filter((link) => link.from !== name && link.to !== name),
      nodes: draft.nodes.map((entry) => ({
        ...entry,
        concepts: entry.concepts.filter((concept) => concept !== name),
      })),
    })
  }

  if (graph.isLoading) {
    return <Loader2 className="text-muted-foreground animate-spin" aria-label={t('library.loading')} />
  }
  const data = graph.data

  return (
    <div className="space-y-4">
      {draft !== null ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Sparkles className="size-4" aria-hidden />
              {t('concepts.draftTitle')}
            </CardTitle>
            <p className="text-muted-foreground text-xs">{t('concepts.draftHint')}</p>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap gap-1">
              {draft.concepts.map((entry) => (
                <span
                  key={entry.name}
                  title={entry.description ?? undefined}
                  className="bg-primary/10 text-primary group flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px]"
                >
                  {entry.name}
                  <button
                    type="button"
                    className="opacity-60 group-hover:opacity-100"
                    title={t('concepts.remove')}
                    onClick={() => removeConcept(entry.name)}
                  >
                    <X className="size-3" aria-hidden />
                  </button>
                </span>
              ))}
            </div>
            <p className="text-muted-foreground text-xs">
              {t('concepts.draftLinks', { count: draft.links.length })}
            </p>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={() => onDraftChange(null)}>
                {t('settings.cancel')}
              </Button>
              <Button size="sm" disabled={commit.isPending} onClick={() => commit.mutate()}>
                {commit.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
                {t('concepts.commit')}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {(data?.concepts.length ?? 0) === 0 ? (
        <div className="text-muted-foreground py-12 text-center text-sm">
          <Network className="mx-auto mb-2 size-8" aria-hidden />
          {t('concepts.empty')}
        </div>
      ) : (
        <div className="space-y-2">
          {(data?.concepts ?? []).map((concept) => {
            const outgoing = (data?.links ?? []).filter((link) => link.from === concept.name)
            const incoming = (data?.links ?? []).filter((link) => link.to === concept.name)
            return (
              <div
                key={concept.id}
                className="border-border bg-subtle/50 rounded-lg border p-3"
              >
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="text-sm font-semibold">{concept.name}</span>
                  {concept.aliases.map((alias) => (
                    <span key={alias} className="text-muted-foreground text-[11px] italic">
                      {alias}
                    </span>
                  ))}
                  {concept.nodes.map((entry) => (
                    <span
                      key={entry.node_id}
                      className="bg-primary/10 text-primary rounded-full px-2 py-0.5 text-[10px]"
                    >
                      {entry.node_title}
                    </span>
                  ))}
                </div>
                {concept.description ? (
                  <p className="text-muted-foreground mt-1 text-xs">{concept.description}</p>
                ) : null}
                {outgoing.length + incoming.length > 0 ? (
                  <ul className="text-muted-foreground mt-2 space-y-0.5 text-[11px]">
                    {outgoing.map((link, index) => (
                      <li key={`out-${index}`}>
                        <span className={cn(link.relation === 'prereq-of' && 'text-primary')}>
                          {t(`concepts.relation_${link.relation.replace(/-/g, '_')}`)}
                        </span>{' '}
                        {link.to}
                      </li>
                    ))}
                    {incoming.map((link, index) => (
                      <li key={`in-${index}`}>
                        {link.from}{' '}
                        <span className="text-muted-foreground/70">
                          {t('concepts.relation_inbound', {
                            relation: t(`concepts.relation_${link.relation.replace(/-/g, '_')}`),
                          })}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
