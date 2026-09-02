import {
  BarChart3,
  BookOpen,
  Bot,
  GraduationCap,
  Home,
  type LucideIcon,
} from 'lucide-react'

export interface AppNavItem {
  to: string
  icon: LucideIcon
  labelKey: string
  exact: boolean
}

/** Primary sidebar destinations — the single registry for the app shell. */
export const PRIMARY_NAV: AppNavItem[] = [
  { to: '/', icon: Home, labelKey: 'nav.home', exact: true },
  { to: '/courses', icon: GraduationCap, labelKey: 'nav.courses', exact: false },
  { to: '/chat', icon: Bot, labelKey: 'nav.chat', exact: false },
  { to: '/library', icon: BookOpen, labelKey: 'nav.library', exact: false },
  { to: '/scores', icon: BarChart3, labelKey: 'nav.scores', exact: false },
]

/**
 * Resolve the active nav id for a pathname. Exact entries match only
 * themselves (so '/' does not shadow everything); prefix entries match by
 * prefix with the longest prefix winning.
 */
export function resolveActiveId(
  pathname: string,
  nav: AppNavItem[] = PRIMARY_NAV,
): string | null {
  const exact = nav.find((item) => item.exact && item.to === pathname)
  if (exact) return exact.to
  const prefix = nav
    .filter((item) => !item.exact && pathname.startsWith(item.to))
    .sort((a, b) => b.to.length - a.to.length)[0]
  return prefix?.to ?? null
}
