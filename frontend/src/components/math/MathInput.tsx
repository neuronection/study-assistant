import { useEffect, useRef, useState } from 'react'
import type { MathfieldElement } from 'mathlive'

let registration: Promise<void> | null = null

export function ensureMathlive(): Promise<void> {
  registration ??= import('mathlive').then(() => undefined)
  return registration
}

export function MathInput({
  value,
  onChange,
}: {
  value: string
  onChange: (value: string) => void
}) {
  const ref = useRef<MathfieldElement>(null)
  const [ready, setReady] = useState(() =>
    typeof window !== 'undefined' && window.customElements.get('math-field') != null
  )

  useEffect(() => {
    if (ready) {
      return undefined
    }
    let cancelled = false
    void ensureMathlive().then(() => {
      if (!cancelled) {
        setReady(true)
      }
    })
    return () => {
      cancelled = true
    }
  }, [ready])

  useEffect(() => {
    const element = ref.current
    if (element && element.value !== value) {
      element.value = value
    }
  }, [value, ready])

  if (!ready) {
    return <div className="bg-subtle h-9 animate-pulse rounded-md" aria-hidden />
  }

  return (
    <math-field
      ref={ref}
      onInput={(event) => onChange((event.target as MathfieldElement).value)}
      style={{ display: 'block' }}
    />
  )
}
