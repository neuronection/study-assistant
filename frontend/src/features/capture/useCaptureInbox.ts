import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'

import {
  ApiError,
  assembleCaptures,
  commitCapture,
  discardCapture,
  stageCaptures,
  type CaptureCommit,
  type CaptureStaging,
} from '@/lib/api'
import {
  JournalNonRetryableError,
  isCaptureOp,
  offlineJournal,
  type CaptureJournalOp,
} from '@/lib/offline/journal'

export interface CaptureInboxState {
  items: CaptureStaging[]
  queued: CaptureJournalOp[]
  durable: boolean
  open: boolean
  show: () => void
  busy: boolean
  error: string | null
  openFiles: (files: FileList | File[]) => Promise<void>
  commit: (captureId: string) => Promise<void>
  assemble: (
    items: Array<{ captureId: string; rotation: number }>,
    title?: string
  ) => Promise<void>
  discard: (captureId: string) => Promise<void>
  retryQueued: (opId: string) => Promise<void>
  retryAllQueued: () => Promise<void>
  removeQueued: (opId: string) => Promise<void>
  close: () => void
}

export function useCaptureInbox({
  courseId,
  folderId,
  nodeId,
  onCommitted,
}: {
  courseId: string | null
  folderId: string | null
  nodeId: string | null
  onCommitted?: (result: CaptureCommit) => void
}): CaptureInboxState {
  const queryClient = useQueryClient()
  const journal = useSyncExternalStore(
    offlineJournal.subscribe,
    offlineJournal.getSnapshot,
    offlineJournal.getSnapshot
  )
  const [items, setItems] = useState<CaptureStaging[]>([])
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const openedForQueue = useRef(false)

  const drain = useCallback(async () => {
    await offlineJournal.drain('capture', async (op, blob) => {
      if (!isCaptureOp(op) || blob === null) {
        return
      }
      const file = new File([blob], op.payload.filename, {
        type: op.payload.mime || 'application/octet-stream',
      })
      try {
        const rows = await stageCaptures([file], op.payload.sourceKind, op.id)
        setItems((previous) => {
          const known = new Set(previous.map((entry) => entry.id))
          return [...rows.filter((row) => !known.has(row.id)), ...previous]
        })
        setOpen(true)
      } catch (cause) {
        if (cause instanceof ApiError && cause.status >= 400 && cause.status < 500) {
          throw new JournalNonRetryableError(cause.message)
        }
        throw cause
      }
    })
  }, [])

  useEffect(() => {
    const onOnline = () => {
      void drain()
    }
    window.addEventListener('online', onOnline)
    if (navigator.onLine) {
      void drain()
    }
    return () => window.removeEventListener('online', onOnline)
  }, [drain])

  useEffect(() => {
    if (!openedForQueue.current && journal.ops.length > 0) {
      openedForQueue.current = true
      setOpen(true)
    }
  }, [journal.ops.length])

  useEffect(() => {
    const onQueued = () => {
      openedForQueue.current = true
      setOpen(true)
    }
    window.addEventListener('sa-capture-enqueued', onQueued)
    return () => window.removeEventListener('sa-capture-enqueued', onQueued)
  }, [])

  const openFiles = useCallback(
    async (files: FileList | File[]) => {
      const list = Array.from(files)
      if (list.length === 0) {
        return
      }
      setBusy(true)
      setError(null)
      try {
        for (const file of list) {
          await offlineJournal.enqueueCapture(file, 'camera')
        }
        setOpen(true)
        await drain()
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : String(cause))
        setOpen(true)
      } finally {
        setBusy(false)
      }
    },
    [drain]
  )

  const commit = useCallback(
    async (captureId: string) => {
      if (courseId === null) {
        setError('Open a course before adding a capture.')
        return
      }
      setBusy(true)
      setError(null)
      try {
        const result = await commitCapture(captureId, {
          courseId,
          folderId,
          nodeId,
        })
        setItems((previous) =>
          previous.map((item) =>
            item.id === captureId
              ? { ...item, status: 'committed', material_id: result.material_id }
              : item
          )
        )
        await queryClient.invalidateQueries({ queryKey: ['materials'] })
        await queryClient.invalidateQueries({ queryKey: ['folders'] })
        await queryClient.invalidateQueries({ queryKey: ['jobs-summary'] })
        onCommitted?.(result)
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : String(cause))
      } finally {
        setBusy(false)
      }
    },
    [courseId, folderId, nodeId, onCommitted, queryClient]
  )

  const assemble = useCallback(
    async (pages: Array<{ captureId: string; rotation: number }>, title?: string) => {
      setBusy(true)
      setError(null)
      try {
        const combined = await assembleCaptures(pages, title)
        const used = new Set(pages.map((page) => page.captureId))
        setItems((previous) => [
          combined,
          ...previous.filter((item) => !used.has(item.id)),
        ])
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : String(cause))
      } finally {
        setBusy(false)
      }
    },
    []
  )

  const discard = useCallback(async (captureId: string) => {
    setBusy(true)
    setError(null)
    try {
      await discardCapture(captureId)
      setItems((previous) =>
        previous.map((item) =>
          item.id === captureId ? { ...item, status: 'discarded' } : item
        )
      )
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy(false)
    }
  }, [])

  const retryQueued = useCallback(
    async (opId: string) => {
      setBusy(true)
      try {
        await offlineJournal.retry(opId)
        await drain()
      } finally {
        setBusy(false)
      }
    },
    [drain]
  )

  const retryAllQueued = useCallback(async () => {
    setBusy(true)
    try {
      for (const op of offlineJournal.getSnapshot().ops.filter(isCaptureOp)) {
        await offlineJournal.retry(op.id)
      }
      await drain()
    } finally {
      setBusy(false)
    }
  }, [drain])

  const removeQueued = useCallback(async (opId: string) => {
    setBusy(true)
    try {
      await offlineJournal.remove(opId)
    } finally {
      setBusy(false)
    }
  }, [])

  const show = useCallback(() => setOpen(true), [])

  const close = useCallback(() => {
    setOpen(false)
    setItems((previous) => previous.filter((item) => item.status === 'staged'))
    setError(null)
  }, [])

  return {
    items,
    queued: journal.ops.filter(isCaptureOp),
    durable: journal.durable,
    open,
    show,
    busy,
    error,
    openFiles,
    commit,
    assemble,
    discard,
    retryQueued,
    retryAllQueued,
    removeQueued,
    close,
  }
}
