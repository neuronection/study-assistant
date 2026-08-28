import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, PlusCircle, Target } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from '@tanstack/react-router'

import { useCurrentOrigin } from '@/lib/origin'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorBanner } from '@/components/ui/error-banner'
import { useRequiredCourse } from '@/components/workspace/CoursePicker'
import { createPattern, drillPatterns, proposePatterns, startDrill, type DrillPattern, type PatternProposal } from '@/lib/api'

function PatternRow({
  pattern,
  courseId,
  busyKey,
  onDrill,
}: {
  pattern: DrillPattern
  courseId: number
  busyKey: string | null
  onDrill: (pattern: string) => void
}) {
  const { t } = useTranslation()
  const busy = busyKey === pattern.pattern
  return (
    <div className="border-border flex items-center gap-3 rounded-lg border px-3 py-2">
      <div className="min-w-0 flex-1">
        <p className="flex items-center gap-2 text-sm font-medium">
          {pattern.name}
          {pattern.occurrences > 0 ? (
            <span className="bg-warning/15 text-warning rounded-full px-2 py-0.5 text-[11px]">
              {t('exercises.occurrences', { count: pattern.occurrences })}
            </span>
          ) : null}
        </p>
        <p className="text-muted-foreground truncate text-xs">{pattern.description}</p>
      </div>
      <Button
        variant="outline"
        size="sm"
        disabled={busy || courseId === 0}
        onClick={() => onDrill(pattern.pattern)}
      >
        {busy ? <Loader2 className="animate-spin" aria-hidden /> : <Target aria-hidden />}
        {t('exercises.startDrill')}
      </Button>
    </div>
  )
}

export function DrillsCard({ courseId }: { courseId?: number }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const from = useCurrentOrigin()
  const queryClient = useQueryClient()
  const required = useRequiredCourse()
  const resolvedCourseId = courseId ?? required.courseId
  const [proposals, setProposals] = useState<PatternProposal[]>([])
  const [proposeResult, setProposeResult] = useState<string | null>(null)

  const patterns = useQuery({
    queryKey: ['drill-patterns', resolvedCourseId],
    queryFn: () => drillPatterns(resolvedCourseId as number),
    enabled: resolvedCourseId !== null,
  })

  const drill = useMutation({
    mutationFn: ({ pattern, courseIdForBody }: { pattern: string; courseIdForBody: number }) =>
      startDrill(pattern, courseIdForBody),
    onSuccess: async (exercise) => {
      navigate({ to: '/exercises/$exerciseId', params: { exerciseId: String(exercise.id) }, search: { from } })
    },
  })

  const propose = useMutation({
    mutationFn: (courseIdForBody: number) => proposePatterns(courseIdForBody),
    onSuccess: (result) => {
      setProposals(result)
      setProposeResult(result.length > 0 ? null : 'empty')
    },
  })

  const approve = useMutation({
    mutationFn: ({
      courseIdForBody,
      proposal,
    }: {
      courseIdForBody: number
      proposal: PatternProposal
    }) => createPattern(courseIdForBody, proposal),
    onSuccess: (_created, { proposal }) => {
      setProposals((prev) => prev.filter((entry) => entry.key !== proposal.key))
      queryClient.invalidateQueries({ queryKey: ['drill-patterns'] })
    },
  })

  if (resolvedCourseId === null) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Target className="size-4" aria-hidden />
            {t('exercises.drillsTitle')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ErrorBanner message={required.needsPicker ? t('workspace.openCourseFirst') : null} />
        </CardContent>
      </Card>
    )
  }

  const list = patterns.data ?? []
  const seeded = list.filter((entry) => entry.source === 'seeded')
  const discovered = list.filter((entry) => entry.source === 'discovered')
  const isEmpty = list.length === 0

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Target className="size-4" aria-hidden />
          {t('exercises.drillsTitle')}
        </CardTitle>
        <p className="text-muted-foreground text-xs">{t('exercises.drillsHint')}</p>
      </CardHeader>
      <CardContent className="space-y-3">
        {patterns.isLoading ? (
          <Loader2 className="animate-spin" aria-label={t('library.loading')} />
        ) : isEmpty ? (
          <p className="text-muted-foreground text-sm">{t('exercises.drillsEmpty')}</p>
        ) : (
          <>
            <div className="space-y-2">
              {seeded.map((pattern) => (
                <PatternRow
                  key={pattern.pattern}
                  pattern={pattern}
                  courseId={resolvedCourseId}
                  busyKey={drill.isPending ? drill.variables?.pattern ?? null : null}
                  onDrill={(patternKey) =>
                    drill.mutate({ pattern: patternKey, courseIdForBody: resolvedCourseId })
                  }
                />
              ))}
            </div>
            {discovered.length > 0 ? (
              <div className="space-y-2">
                <p className="text-muted-foreground text-xs font-medium">
                  {t('exercises.discoveredSection')}
                </p>
                {discovered.map((pattern) => (
                  <PatternRow
                    key={pattern.pattern}
                    pattern={pattern}
                    courseId={resolvedCourseId}
                    busyKey={drill.isPending ? drill.variables?.pattern ?? null : null}
                    onDrill={(patternKey) =>
                      drill.mutate({ pattern: patternKey, courseIdForBody: resolvedCourseId })
                    }
                  />
                ))}
              </div>
            ) : null}
          </>
        )}

        {proposals.map((proposal) => (
          <div
            key={proposal.key}
            className="border-border bg-muted/40 flex flex-col gap-2 rounded-lg border px-3 py-2"
          >
            <p className="text-sm font-medium">{proposal.name}</p>
            <p className="text-muted-foreground text-xs">{proposal.description}</p>
            {proposal.example ? (
              <p className="text-muted-foreground text-xs italic">{proposal.example}</p>
            ) : null}
            <div className="flex gap-2">
              <Button
                variant="default"
                size="sm"
                disabled={approve.isPending && approve.variables?.proposal.key === proposal.key}
                onClick={() =>
                  approve.mutate({ courseIdForBody: resolvedCourseId, proposal })
                }
              >
                {t('ai.proposals.approve')}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() =>
                  setProposals((prev) => prev.filter((entry) => entry.key !== proposal.key))
                }
              >
                {t('ai.proposals.dismiss')}
              </Button>
            </div>
          </div>
        ))}
        {proposeResult === 'empty' ? (
          <p className="text-muted-foreground text-xs">{t('exercises.drillsNoProposals')}</p>
        ) : null}

        <div className="flex justify-end">
          <Button
            variant="ghost"
            size="sm"
            disabled={propose.isPending || approve.isPending}
            onClick={() => {
              setProposeResult(null)
              propose.mutate(resolvedCourseId)
            }}
          >
            {propose.isPending ? (
              <Loader2 className="animate-spin" aria-hidden />
            ) : (
              <PlusCircle aria-hidden />
            )}
            {t('exercises.findMorePatterns')}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}