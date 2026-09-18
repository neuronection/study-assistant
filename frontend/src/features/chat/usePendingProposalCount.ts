import { useQuery } from '@tanstack/react-query'

import { getNotifications } from '@/lib/api'

/** Light pending-proposal count for the chat rail badge; shares the
 * notification bell's query cache. */
export function usePendingProposalCount() {
  const pending = useQuery({
    queryKey: ['notifications'],
    queryFn: getNotifications,
    staleTime: 30_000,
  })
  return pending.data?.pending_proposals ?? 0
}
