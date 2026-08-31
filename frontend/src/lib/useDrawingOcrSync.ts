import { useEffect, useRef } from 'react'

import { getWsClient } from '@/lib/ws-client'
import { WsTopic } from '@/lib/constants'

export function useDrawingOcrSync(
  drawings: { ocr_job_id?: number | null }[] | undefined,
  onSettled: () => void
): void {
  const onSettledRef = useRef(onSettled)
  onSettledRef.current = onSettled
  const key = (drawings ?? [])
    .map((drawing) => drawing.ocr_job_id)
    .filter((id): id is number => typeof id === 'number')
    .join(',')

  useEffect(() => {
    if (key === '') {
      return
    }
    const jobIds = key.split(',').map(Number)
    const unsubscribes = jobIds.map((jobId) =>
      getWsClient().subscribe(WsTopic.jobs(jobId), (payload) => {
        const status = (payload as { status?: string }).status
        if (status === 'done' || status === 'failed') {
          onSettledRef.current()
        }
      })
    )
    return () => {
      for (const unsubscribe of unsubscribes) {
        unsubscribe()
      }
    }
  }, [key])
}
