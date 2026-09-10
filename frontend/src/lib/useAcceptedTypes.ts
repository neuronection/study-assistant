import { useQuery } from '@tanstack/react-query'

import { getAcceptedTypes } from '@/lib/api'

export function useAcceptedTypes(): string {
  const { data } = useQuery({
    queryKey: ['accepted-types'],
    queryFn: getAcceptedTypes,
    staleTime: Infinity,
  })
  return data?.accept ?? ''
}
