import { useEffect, useState } from 'react'

/** Whether a CSS media query currently matches (re-evaluates on change).
 * Environments without `matchMedia` (jsdom) resolve to `false`. */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => {
    if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
      return window.matchMedia(query).matches
    }
    return false
  })

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const mql = window.matchMedia(query)
    const onChange = (event: MediaQueryListEvent) => setMatches(event.matches)
    setMatches(mql.matches)
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [query])

  return matches
}

/** True on short viewports — the sidebar drops to the compact density and
 * hides the footer project block so the nav list stays fully visible. */
export function useIsShortViewport(): boolean {
  return useMediaQuery('(max-height: 720px)')
}
