import { useCallback, useState } from 'react'

export function useWidgetState<S extends Record<string, unknown>>(
  initial: S,
  onStateChange?: (state: Record<string, unknown>) => void,
) {
  const [state, setState] = useState<S>(initial)
  const update = useCallback(
    (patch: Partial<S>) => {
      setState((prev) => {
        const next = { ...prev, ...patch }
        onStateChange?.(next)
        return next
      })
    },
    [onStateChange],
  )
  return [state, update] as const
}
