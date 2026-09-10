import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { getProfilePreferences, updateProfilePreferences } from '@/lib/api'

const MAX_EDGE_OPTIONS = [0, 1024, 1568, 2048] as const

export function SearchTab() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const preferences = useQuery({
    queryKey: ['profile-preferences'],
    queryFn: getProfilePreferences,
  })
  const save = useMutation({
    mutationFn: updateProfilePreferences,
    onSuccess: async (data) => {
      queryClient.setQueryData(['profile-preferences'], data)
    },
  })

  const enabled = preferences.data?.use_embeddings ?? true
  const maxEdge = preferences.data?.ocr_image_max_edge ?? 1568

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t('settings.searchTitle')}</CardTitle>
          <CardDescription>{t('settings.searchDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={enabled}
              disabled={preferences.isLoading || save.isPending}
              onChange={(event) => save.mutate({ use_embeddings: event.target.checked })}
            />
            {t('settings.searchUseEmbeddings')}
            {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
          </label>
          <p className="text-muted-foreground text-[11px]">
            {t('settings.searchUseEmbeddingsHint')}
          </p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t('settings.ocrImageTitle')}</CardTitle>
          <CardDescription>{t('settings.ocrImageDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <label className="flex items-center gap-2 text-sm">
            {t('settings.ocrImageLabel')}
            <select
              aria-label={t('settings.ocrImageLabel')}
              value={maxEdge}
              disabled={preferences.isLoading || save.isPending}
              onChange={(event) =>
                save.mutate({ ocr_image_max_edge: Number(event.target.value) })
              }
              className="border-border bg-surface rounded-md border px-2 py-1 text-sm"
            >
              {MAX_EDGE_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option === 0
                    ? t('settings.ocrImageOff')
                    : t('settings.ocrImagePx', { px: option })}
                </option>
              ))}
            </select>
            {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
          </label>
          <p className="text-muted-foreground text-[11px]">
            {t('settings.ocrImageHint')}
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
