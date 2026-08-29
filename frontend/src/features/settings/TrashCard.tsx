import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Trash2, Undo2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorBanner } from '@/components/ErrorBanner'
import { listDeletedItems, purgeDeletedItem, restoreDeletedItem } from '@/lib/api'

export function TrashCard() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const items = useQuery({
    queryKey: ['deleted-items'],
    queryFn: listDeletedItems,
  })

  const restore = useMutation({
    mutationFn: (id: number) => restoreDeletedItem(id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['deleted-items'] })
      await queryClient.invalidateQueries()
    },
  })

  const purge = useMutation({
    mutationFn: (id: number) => purgeDeletedItem(id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['deleted-items'] })
    },
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          <Trash2 className="size-4" aria-hidden />
          {t('trash.title')}
        </CardTitle>
        <CardDescription>{t('trash.hint')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {items.isLoading ? (
          <Loader2
            className="text-muted-foreground animate-spin"
            aria-label={t('library.loading')}
          />
        ) : (items.data ?? []).length === 0 ? (
          <p className="text-muted-foreground text-xs">{t('trash.empty')}</p>
        ) : (
          <ul className="divide-border divide-y rounded-md border">
            {(items.data ?? []).map((entry) => (
              <li key={entry.id} className="flex items-center gap-2 px-2 py-1.5 text-xs">
                <span className="bg-subtle rounded px-1.5 py-0.5 font-medium">
                  {t(`trash.entity.${entry.entity_type}`)}
                </span>
                <span className="min-w-0 flex-1 truncate font-medium">{entry.title}</span>
                <span className="text-muted-foreground shrink-0">
                  {new Date(entry.deleted_at).toLocaleString()}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={restore.isPending}
                  onClick={() => restore.mutate(entry.id)}
                >
                  {restore.isPending && restore.variables === entry.id ? (
                    <Loader2 className="animate-spin" aria-hidden />
                  ) : (
                    <Undo2 className="size-3.5" aria-hidden />
                  )}
                  {t('trash.restore')}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={purge.isPending}
                  title={t('trash.delete')}
                  onClick={() => purge.mutate(entry.id)}
                >
                  {purge.isPending && purge.variables === entry.id ? (
                    <Loader2 className="animate-spin" aria-hidden />
                  ) : (
                    <Trash2 className="size-3.5" aria-hidden />
                  )}
                </Button>
              </li>
            ))}
          </ul>
        )}
        <ErrorBanner message={restore.error?.message ?? purge.error?.message ?? null} />
      </CardContent>
    </Card>
  )
}
