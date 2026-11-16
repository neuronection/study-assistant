import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { BarChart3, BookOpen, Bot, Camera, GraduationCap, Home, MoreHorizontal, Presentation, RotateCcw, Search, Settings, Sigma } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'

export interface MobileNavAction {
  key: string
  label: string
  icon: typeof Home
  path: string
}

const PRIMARY: MobileNavAction[] = [
  { key: 'home', label: 'nav.home', icon: Home, path: '/' },
  { key: 'courses', label: 'nav.courses', icon: GraduationCap, path: '/courses' },
  { key: 'review', label: 'nav.review', icon: RotateCcw, path: '/review' },
  { key: 'solve', label: 'nav.solve', icon: Sigma, path: '/solve' },
  { key: 'studio', label: 'nav.studio', icon: Presentation, path: '/studio' },
]

const MORE: MobileNavAction[] = [
  { key: 'chat', label: 'nav.chat', icon: Bot, path: '/chat' },
  { key: 'library', label: 'nav.library', icon: BookOpen, path: '/library' },
  { key: 'scores', label: 'nav.scores', icon: BarChart3, path: '/scores' },
  { key: 'settings', label: 'settings.title', icon: Settings, path: '/settings' },
]

export function MobileBottomBar({
  activePath,
  dueCount,
  onNavigate,
  onCapture,
  onSearch,
}: {
  activePath: string
  dueCount: number
  onNavigate: (path: string) => void
  onCapture: (files: FileList) => void
  onSearch: () => void
}) {
  const { t } = useTranslation()
  const [moreOpen, setMoreOpen] = useState(false)
  const moreButtonRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setMoreOpen(false)
  }, [activePath])

  useEffect(() => {
    if (!moreOpen) {
      return
    }
    const closeOnPointerDown = (event: PointerEvent) => {
      const target = event.target
      if (!(target instanceof Node)) {
        return
      }
      if (menuRef.current?.contains(target) || moreButtonRef.current?.contains(target)) {
        return
      }
      setMoreOpen(false)
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setMoreOpen(false)
        moreButtonRef.current?.focus()
      }
    }
    document.addEventListener('pointerdown', closeOnPointerDown)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('pointerdown', closeOnPointerDown)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [moreOpen])

  const item = (action: MobileNavAction, extra?: string) => {
    const Icon = action.icon
    const active = activePath === action.path || (action.path !== '/' && activePath.startsWith(action.path))
    return (
      <button
        key={action.key}
        type="button"
        aria-current={active ? 'page' : undefined}
        className={cn(
          'relative flex min-w-0 flex-1 flex-col items-center gap-0.5 px-1 py-2 text-[10px] font-medium transition-colors',
          active ? 'text-primary' : 'text-muted-foreground hover:text-foreground'
        )}
        onClick={() => {
          setMoreOpen(false)
          onNavigate(action.path)
        }}
      >
        <Icon className="size-5" aria-hidden />
        <span className="truncate">{t(action.label)}</span>
        {extra !== undefined ? (
          <span className="bg-primary text-primary-foreground absolute right-4 top-1 rounded-full px-1 text-[9px] leading-4">
            {extra}
          </span>
        ) : null}
      </button>
    )
  }

  return (
    <>
      {moreOpen && typeof document !== 'undefined'
        ? createPortal(
            <>
              <div
                className="fixed inset-0 z-50 bg-black/10 md:hidden"
                aria-hidden
                onClick={() => setMoreOpen(false)}
              />
              <div
                ref={menuRef}
                id="mobile-more-menu"
                className="fixed inset-x-3 bottom-[calc(4.75rem+env(safe-area-inset-bottom))] z-[60] max-h-[min(60vh,24rem)] overflow-y-auto rounded-lg border border-border bg-surface p-1.5 shadow-[var(--as-shadow-3)] md:hidden"
                role="menu"
                aria-label={t('nav.more')}
              >
                {MORE.map((action) => {
                  const Icon = action.icon
                  return (
                    <button
                      key={action.key}
                      type="button"
                      role="menuitem"
                      className="hover:bg-subtle flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm"
                      onClick={() => {
                        setMoreOpen(false)
                        onNavigate(action.path)
                      }}
                    >
                      <Icon className="size-4" aria-hidden />
                      {t(action.label)}
                    </button>
                  )
                })}
                <button
                  type="button"
                  role="menuitem"
                  className="hover:bg-subtle flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm"
                  onClick={() => {
                    setMoreOpen(false)
                    onSearch()
                  }}
                >
                  <Search className="size-4" aria-hidden />
                  {t('nav.search')}
                </button>
              </div>
            </>,
            document.body
          )
        : null}
      <nav
        className="border-border bg-surface fixed inset-x-0 bottom-0 z-40 flex items-stretch border-t pb-[env(safe-area-inset-bottom)] md:hidden"
        aria-label={t('nav.mobile')}
      >
        {PRIMARY.map((action) =>
          item(action, action.key === 'review' && dueCount > 0 ? String(dueCount) : undefined)
        )}
        <label className="relative flex min-w-0 flex-1 cursor-pointer flex-col items-center gap-0.5 px-1 py-2 text-[10px] font-medium text-muted-foreground transition-colors hover:text-foreground">
          <span className="bg-primary text-primary-foreground -mt-3 flex size-9 items-center justify-center rounded-full shadow-[var(--as-shadow-2)]">
            <Camera className="size-5" aria-hidden />
          </span>
          <span className="truncate">{t('nav.capture')}</span>
          <input
            type="file"
            accept="image/*"
            capture="environment"
            multiple
            className="sr-only"
            aria-label={t('captureInbox.cameraInput')}
            onChange={(event) => {
              if (event.target.files && event.target.files.length > 0) {
                onCapture(event.target.files)
              }
              event.target.value = ''
            }}
          />
        </label>
        <button
          ref={moreButtonRef}
          type="button"
          aria-expanded={moreOpen}
          aria-haspopup="menu"
          aria-controls={moreOpen ? 'mobile-more-menu' : undefined}
          className={cn(
            'flex min-w-0 flex-1 flex-col items-center gap-0.5 px-1 py-2 text-[10px] font-medium transition-colors',
            moreOpen ? 'text-primary' : 'text-muted-foreground hover:text-foreground'
          )}
          onClick={() => setMoreOpen((previous) => !previous)}
        >
          <MoreHorizontal className="size-5" aria-hidden />
          <span className="truncate">{t('nav.more')}</span>
        </button>
      </nav>
    </>
  )
}
