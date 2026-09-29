import { useSyncExternalStore } from 'react'

export type Theme = 'light' | 'dark' | 'system'

function readStoredTheme(): Theme | null {
  try {
    const stored = localStorage.getItem('ca.theme')
    return stored === 'light' || stored === 'dark' || stored === 'system' ? stored : null
  } catch {
    return null
  }
}

function storeTheme(theme: Theme): void {
  try {
    localStorage.setItem('ca.theme', theme)
  } catch {
    return
  }
}

function applyTheme(theme: Theme) {
  const dark =
    theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  document.documentElement.classList.toggle('dark', dark)
  storeTheme(theme)
}

/** Tiny pub/sub so the theme preference is one shared state — the
 * `UserMenu` appearance section (Theme submenu) renders from it
 * (boot-time application itself lives in index.html). localStorage
 * stays the single source of truth; `setThemePreference` applies and
 * notifies the subscribers. */
const subscribers = new Set<() => void>()

function getTheme(): Theme {
  return readStoredTheme() ?? 'system'
}

function setThemePreference(theme: Theme): void {
  applyTheme(theme)
  for (const notify of subscribers) notify()
}

function subscribeTheme(onChange: () => void): () => void {
  subscribers.add(onChange)
  return () => {
    subscribers.delete(onChange)
  }
}

/** Controlled theme preference — `[theme, setTheme]`, shared app-wide. */
export function useThemePreference(): [Theme, (theme: Theme) => void] {
  const theme = useSyncExternalStore(subscribeTheme, getTheme)
  return [theme, setThemePreference]
}
