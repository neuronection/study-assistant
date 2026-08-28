import { Monitor, Moon, Sun } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'

type Theme = 'light' | 'dark' | 'system'

const order: Theme[] = ['system', 'light', 'dark']

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

export function ThemeToggle() {
  const { t } = useTranslation()
  const [current, setCurrent] = useState<Theme>(() => readStoredTheme() ?? 'system')

  const next = order[(order.indexOf(current) + 1) % order.length]!

  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={() => {
        applyTheme(next)
        setCurrent(next)
      }}
      aria-label={t(`theme.${next}`)}
      title={t(`theme.${next}`)}
    >
      {current === 'system' ? <Monitor /> : current === 'light' ? <Sun /> : <Moon />}
      <span className="text-xs">{t(`theme.${current}`)}</span>
    </Button>
  )
}
