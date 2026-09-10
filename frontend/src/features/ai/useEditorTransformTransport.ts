import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'

import type { AiTextTransformTransport } from '@/components/ui/ai-text-transform'
import { getWsClient } from '@/lib/ws-client'
import {
  cancelEditorTransformJob,
  getEditorTransformJob,
  startEditorTransform,
  type EditorTransformRequest,
} from '@/lib/api'

interface EditorEvent {
  type?: string
  text?: string
  message?: string
  result_md?: string
}

export function useEditorTransformTransport(
  requestRef: { current: EditorTransformRequest | null }
): AiTextTransformTransport {
  const { t } = useTranslation()
  return useMemo<AiTextTransformTransport>(
    () => ({
      start: async () => {
        const request = requestRef.current
        if (request === null) {
          throw new Error('missing editor transform request')
        }
        const { job_id } = await startEditorTransform(request)
        return String(job_id)
      },
      subscribe: (jobId, handlers) =>
        getWsClient().subscribe(`ai-editor:${jobId}`, (payload) => {
          const event = payload as EditorEvent
          if (event.type === 'editor_delta' && event.text) {
            handlers.onDelta(event.text)
          } else if (event.type === 'editor_done') {
            handlers.onDone(event.result_md ?? '')
          } else if (event.type === 'editor_error') {
            handlers.onError(event.message ?? t('editor.ai.flowFailed'))
          }
        }),
      cancel: async (jobId) => {
        await cancelEditorTransformJob(Number(jobId)).catch(() => undefined)
      },
      poll: async (jobId) => {
        const job = await getEditorTransformJob(Number(jobId))
        return {
          status: job.status === 'queued' ? 'running' : job.status,
          result: job.result_md,
          error: job.error ?? undefined,
        }
      },
    }),
    [requestRef, t]
  )
}
