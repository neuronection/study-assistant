import { useQuery } from '@tanstack/react-query'

import { getInstanceConfig } from '@/lib/api'

export function useIdentityMode() {
  const query = useQuery({
    queryKey: ['instance-config'],
    queryFn: getInstanceConfig,
    staleTime: Infinity,
    retry: false,
  })

  return {
    identityMode: query.data?.identity_mode,
    isDesktop: query.data?.identity_mode === 'desktop',
    isPending: query.isPending,
    isError: query.isError,
  }
}
