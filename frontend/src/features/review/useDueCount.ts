import { useQuery } from '@tanstack/react-query'

import { getReviewDue } from '@/lib/api'

/** Light cross-course due count for the rail badge (first batch capped at 1 card). */
export function useDueCount() {
  const due = useQuery({
    queryKey: ['review-due'],
    queryFn: () => getReviewDue(1),
    staleTime: 30_000,
  })
  return due.data?.total_due ?? 0
}
