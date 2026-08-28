import { useMutation, useQueryClient } from '@tanstack/react-query'
import { History, Loader2, Undo2 } from 'lucide-react'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { restoreDeletedItem } from '@/lib/api'

export function UndoDeleteNotice({
  deletedItemId,
  onDismiss,
}: {
  deletedItemId: number | null
  onDismiss: () => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  useEffect(() => {
    if (deletedItemId === null) {
      return
    }
    const timer = window.setTimeout(onDismiss, 8000)
    return () => window.clearTimeout(timer)
  }, [deletedItemId, onDismiss])

  const restore = useMutation({
    mutationFn: () => restoreDeletedItem(deletedItemId as number),
    onSuccess: async () => {
      onDismiss()
      await queryClient.invalidateQueries()
    },
  })

  if (deletedItemId === null) {
    return null
  }

  return (
    <div className="bg-subtle border-border flex items-center justify-between gap-2 rounded-md border px-3 py-1.5 text-xs">
      <span className="flex items-center gap-1.5">
        <History className="size-3.5" aria-hidden />
        {t('trash.undoDelete')}
      </span>
      <Button
        variant="outline"
        size="sm"
        disabled={restore.isPending}
        onClick={() => restore.mutate()}
      >
        {restore.isPending ? (
          <Loader2 className="animate-spin" aria-hidden />
        ) : (
          <Undo2 aria-hidden />
        )}
        {t('trash.undo')}
      </Button>
    </div>
  )
}
