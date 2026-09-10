import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'

import { UndoNotice } from '@neuronection/assistant-ui'
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
    <UndoNotice
      message={t('trash.undoDelete')}
      actionLabel={t('trash.undo')}
      undoing={restore.isPending}
      onUndo={() => restore.mutate()}
      onDismiss={onDismiss}
    />
  )
}
