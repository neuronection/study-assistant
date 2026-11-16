import { describe, expect, test, vi, beforeEach } from 'vitest'

import { reviewFlashcard } from '@/lib/api'
import { offlineJournal } from '@/lib/offline/journal'
import { drainReviewQueue, isOfflineFailure, submitReview } from './review-submit'

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return {
    ...actual,
    reviewFlashcard: vi.fn(),
  }
})

const reviewMock = vi.mocked(reviewFlashcard)

describe('review-submit', () => {
  beforeEach(async () => {
    reviewMock.mockReset()
    for (const op of offlineJournal.getSnapshot().ops) {
      await offlineJournal.remove(op.id)
    }
  })

  test('sends online and queues a network failure', async () => {
    reviewMock.mockResolvedValueOnce({
      interval_days: 1,
      due_at: '2026-11-11T00:00:00Z',
    } as never)
    await expect(submitReview('card-1', 3)).resolves.toBe('sent')

    reviewMock.mockRejectedValueOnce(new TypeError('fetch failed'))
    await expect(submitReview('card-2', 4)).resolves.toBe('queued')
    expect(offlineJournal.getSnapshot().ops).toHaveLength(1)
    expect(offlineJournal.getSnapshot().ops[0]).toMatchObject({
      entity: 'review',
      payload: { cardId: 'card-2', rating: 4 },
    })
  })

  test('drains queued ratings through the API', async () => {
    await offlineJournal.enqueueReview('card-3', 2, Date.now() - 1000)
    reviewMock.mockResolvedValueOnce({
      interval_days: 1,
      due_at: '2026-11-11T00:00:00Z',
    } as never)
    await expect(drainReviewQueue()).resolves.toBe(1)
    expect(reviewMock).toHaveBeenCalledWith('card-3', 2, expect.any(Number))
    expect(offlineJournal.getSnapshot().ops).toHaveLength(0)
  })

  test('classifies only network failures as offline', () => {
    expect(isOfflineFailure(new TypeError('fetch failed'))).toBe(true)
    expect(isOfflineFailure(new Error('bad'))).toBe(false)
  })
})
