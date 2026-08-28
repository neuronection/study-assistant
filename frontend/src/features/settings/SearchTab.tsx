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

  return (
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
  )
}