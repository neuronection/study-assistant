import { render, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { useDrawingOcrSync } from './useDrawingOcrSync'

const subscribe = vi.fn()
const unsubscribe = vi.fn()

vi.mock('@/lib/ws-client', () => ({
  getWsClient: () => ({
    subscribe: (topic: string, handler: (payload: unknown) => void) => {
      subscribe(topic, handler)
      return unsubscribe
    },
  }),
}))

type Handler = (payload: unknown) => void

function Harness({
  drawings,
  onSettled,
}: {
  drawings: { ocr_job_id?: number | null }[]
  onSettled: () => void
}) {
  useDrawingOcrSync(drawings, onSettled)
  return null
}

describe('useDrawingOcrSync', () => {
  beforeEach(() => {
    subscribe.mockClear()
    unsubscribe.mockClear()
  })

  test('subscribes to each pending job topic and reacts to done/failed', async () => {
    const onSettled = vi.fn()
    const handlers: Handler[] = []
    subscribe.mockImplementation((_topic: string, handler: Handler) => {
      handlers.push(handler)
      return unsubscribe
    })

    const { rerender } = render(
      <Harness
        drawings={[
          { ocr_job_id: 7 },
          { ocr_job_id: 9 },
          { ocr_job_id: null },
          {},
        ]}
        onSettled={onSettled}
      />
    )
    await waitFor(() => expect(subscribe).toHaveBeenCalledTimes(2))
    expect(subscribe).toHaveBeenCalledWith('jobs:7', expect.any(Function))
    expect(subscribe).toHaveBeenCalledWith('jobs:9', expect.any(Function))

    handlers[0]({ status: 'done' })
    handlers[1]({ status: 'failed', error: 'boom' })
    expect(onSettled).toHaveBeenCalledTimes(2)

    handlers[0]({ status: 'running' })
    expect(onSettled).toHaveBeenCalledTimes(2)

    rerender(
      <Harness drawings={[{ ocr_job_id: 7 }, { ocr_job_id: null }]} onSettled={onSettled} />
    )
    await waitFor(() => expect(unsubscribe).toHaveBeenCalled())
  })

  test('subscribes to nothing without pending jobs', () => {
    render(<Harness drawings={[{ ocr_job_id: null }]} onSettled={() => undefined} />)
    expect(subscribe).not.toHaveBeenCalled()
  })
})
