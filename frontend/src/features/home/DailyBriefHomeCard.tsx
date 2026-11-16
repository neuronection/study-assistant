import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { AudioLines, Loader2, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { NarrateDialog } from '@/features/artifacts/NarrateDialog'
import { listArtifacts, type Artifact } from '@/lib/api'

export function DailyBriefHomeCard({ courseId }: { courseId: string | null }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const artifacts = useQuery({
    queryKey: ['artifacts', courseId],
    queryFn: () => listArtifacts(courseId ?? undefined),
    enabled: courseId !== null,
  })
  if (courseId === null) {
    return null
  }
  const briefs = (artifacts.data ?? []).filter(
    (artifact: Artifact) => artifact.kind === 'audio_brief'
  )
  const latest = briefs[0]

  return (
    <Card className="mt-4">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <AudioLines className="text-primary size-4" aria-hidden />
          {t('home.dailyBrief')}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-wrap items-center gap-2">
        {latest ? (
          <p className="text-muted-foreground min-w-0 flex-1 text-xs">
            {latest.status === 'ready'
              ? t('home.dailyBriefReady')
              : latest.status === 'failed'
                ? t('home.dailyBriefFailed')
                : t('home.dailyBriefRendering')}
          </p>
        ) : (
          <p className="text-muted-foreground min-w-0 flex-1 text-xs">
            {t('home.dailyBriefEmpty')}
          </p>
        )}
        {latest?.status === 'ready' && latest.output_material_id ? (
          <Button size="sm" asChild>
            <Link to="/library/$materialId" params={{ materialId: latest.output_material_id }}>
              {t('home.dailyBriefOpen')}
            </Link>
          </Button>
        ) : (
          <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
            <Sparkles className="size-3.5" aria-hidden />
            {t('home.dailyBriefGenerate')}
          </Button>
        )}
        {latest?.status === 'pending' || latest?.status === 'rendering' ? (
          <Loader2 className="size-4 animate-spin" aria-hidden />
        ) : null}
      </CardContent>
      {open ? (
        <NarrateDialog
          courseId={courseId}
          nodeId={null}
          onClose={() => setOpen(false)}
        />
      ) : null}
    </Card>
  )
}
