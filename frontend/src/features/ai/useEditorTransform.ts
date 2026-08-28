import { useCallback, useEffect, useRef, useState } from 'react'

import {
  cancelEditorTransformJob,
  getEditorTransformJob,
  startEditorTransform,
  type EditorTransformRequest,
} from '@/lib/api'
import { getWsClient } from '@/lib/ws-client'

export type EditorTransformUiStatus = 'idle' | 'running' | 'done' | 'error' | 'cancelled'

interface EditorEvent {
  type?: string
  text?: string
  message?: string
  result_md?: string
}

const POLL_INTERVAL_MS = 800
const TIMEOUT_MS = 90_000

export function useEditorTransform() {
  const [status, setStatus] = useState<EditorTransformUiStatus>('idle')
  const [jobId, setJobId] = useState<number | null>(null)
  const [result, setResult] = useState('')
  const [error, setError] = useState<string | null>(null)
  const unsubscribeRef = useRef<(() => void) | null>(null)

  const detach = useCallback(() => {
    unsubscribeRef.current?.()
    unsubscribeRef.current = null
  }, [])

  const start = useCallback(
    async (params: EditorTransformRequest) => {
      detach()
      setStatus('running')
      setResult('')
      setError(null)
      setJobId(null)
      try {
        const { job_id } = await startEditorTransform(params)
        setJobId(job_id)
        unsubscribeRef.current = getWsClient().subscribe(`ai-editor:${job_id}`, (payload) => {
          const event = payload as EditorEvent
          if (event.type === 'editor_delta' && event.text) {
            setResult((current) => current + event.text)
          } else if (event.type === 'editor_done') {
            setResult(event.result_md ?? '')
            setStatus('done')
          } else if (event.type === 'editor_error') {
            setError(event.message ?? 'AI helper failed')
            setStatus('error')
          }
        })
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : String(cause))
        setStatus('error')
      }
    },
    [detach]
  )

  const stop = useCallback(async () => {
    if (jobId !== null) {
      detach()
      await cancelEditorTransformJob(jobId).catch(() => undefined)
    }
    setStatus('cancelled')
  }, [detach, jobId])

  const reset = useCallback(() => {
    detach()
    setJobId(null)
    setResult('')
    setError(null)
    setStatus('idle')
  }, [detach])

  useEffect(() => {
    if (status !== 'running' || jobId === null) {
      return
    }
    const timer = window.setInterval(() => {
      getEditorTransformJob(jobId)
        .then((job) => {
          if (job.status === 'done') {
            setResult(job.result_md)
            setStatus('done')
          } else if (job.status === 'error') {
            setError(job.error ?? 'AI helper failed')
            setStatus('error')
          } else if (job.status === 'cancelled') {
            setStatus('cancelled')
          }
        })
        .catch(() => undefined)
    }, POLL_INTERVAL_MS)
    const timeout = window.setTimeout(() => {
      setError('AI helper timed out')
      setStatus('error')
    }, TIMEOUT_MS)
    return () => {
      window.clearInterval(timer)
      window.clearTimeout(timeout)
    }
  }, [status, jobId])

  useEffect(() => detach, [detach])

  return { start, stop, reset, status, result, error }
}