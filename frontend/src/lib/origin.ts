import { useCallback } from 'react'
import { useRouter, useRouterState } from '@tanstack/react-router'

export function parseOrigin(value: unknown): string | null {
  if (typeof value !== 'string' || value.length === 0) {
    return null
  }
  let decoded: string
  try {
    decoded = decodeURIComponent(value)
  } catch {
    return null
  }
  if (!decoded.startsWith('/') || decoded.startsWith('//')) {
    return null
  }
  return decoded
}

export function practiceFallback(
  courseId: number | null | undefined,
  nodeId: number | null | undefined
): string {
  if (courseId === null || courseId === undefined) {
    return '/courses'
  }
  if (nodeId === null || nodeId === undefined) {
    return `/courses/${courseId}?tab=practice`
  }
  return `/courses/${courseId}/n/${nodeId}?tab=practice`
}

export function useCurrentOrigin(): string {
  const href = useRouterState({ select: (state) => state.location.href })
  return href
}

export function useOriginBack(from: unknown, fallbackHref: string): () => void {
  const router = useRouter()
  return useCallback(() => {
    const origin = parseOrigin(from)
    router.history.push(origin ?? fallbackHref)
  }, [router, from, fallbackHref])
}
