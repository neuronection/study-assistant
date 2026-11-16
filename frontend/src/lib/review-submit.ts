import { ApiError, reviewFlashcard } from '@/lib/api'
import {
  JournalNonRetryableError,
  isReviewOp,
  offlineJournal,
} from '@/lib/offline/journal'

export type ReviewSubmitResult = 'sent' | 'queued'

export function isOfflineFailure(error: unknown): boolean {
  if (typeof navigator !== 'undefined' && navigator.onLine === false) {
    return true
  }
  return error instanceof TypeError
}

export async function submitReview(
  cardId: string,
  rating: number
): Promise<ReviewSubmitResult> {
  try {
    await reviewFlashcard(cardId, rating)
    return 'sent'
  } catch (cause) {
    if (cause instanceof ApiError || !isOfflineFailure(cause)) {
      throw cause
    }
    await offlineJournal.enqueueReview(cardId, rating)
    return 'queued'
  }
}

export async function drainReviewQueue(): Promise<number> {
  return offlineJournal.drain('review', async (op) => {
    if (!isReviewOp(op)) {
      return
    }
    try {
      await reviewFlashcard(op.payload.cardId, op.payload.rating, op.payload.reviewedAt)
    } catch (cause) {
      if (cause instanceof ApiError && cause.status >= 400 && cause.status < 500) {
        throw new JournalNonRetryableError(cause.message)
      }
      throw cause
    }
  })
}
