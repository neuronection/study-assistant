import { useCallback, useEffect, useRef, useState } from 'react'

const FLUSH_INTERVAL_MS = 33

export interface StreamBuffer {
  text: string | null
  append: (delta: string) => void
  reset: () => void
}

export function useStreamBuffer(): StreamBuffer {
  const [text, setText] = useState<string | null>(null)
  const bufferRef = useRef('')
  const rafRef = useRef<number | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const cancel = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const flush = useCallback(() => {
    rafRef.current = null
    timerRef.current = null
    setText(bufferRef.current)
  }, [])

  const schedule = useCallback(() => {
    if (rafRef.current !== null || timerRef.current !== null) {
      return
    }
    if (typeof requestAnimationFrame === 'function') {
      rafRef.current = requestAnimationFrame(() => flush())
    } else {
      timerRef.current = setTimeout(() => flush(), FLUSH_INTERVAL_MS)
    }
  }, [flush])

  const append = useCallback(
    (delta: string) => {
      bufferRef.current += delta
      schedule()
    },
    [schedule],
  )

  const reset = useCallback(() => {
    cancel()
    bufferRef.current = ''
    setText(null)
  }, [cancel])

  useEffect(() => cancel, [cancel])

  return { text, append, reset }
}
