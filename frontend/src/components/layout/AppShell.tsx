import {
  useLocation,
  Link,
  useNavigate,
  useParams,
  useSearch,
} from '@tanstack/react-router'
import {
  Check,
  ChevronDown,
  ChevronRight,
  Dumbbell,
  FlaskConical,
  FolderClosed,
  GraduationCap,
  Home,
  Info,
  Keyboard,
  AudioLines,
  Layers,
  MessageSquare,
  NotebookPen,
  Plus,
  Search,
  Settings,
  Download,
  X,
} from 'lucide-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Suspense, createContext, lazy, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { CommandPalette, useCommandPaletteOpen } from './CommandPalette'
import { fileDockOpen } from '@/lib/file-dock-open'
import { FocusTimer } from './FocusTimer'
import { RouteFade } from './RouteFade'
import { loadUpdateCheck } from './UpdateBadge'
import { ShortcutsDialog } from './ShortcutsDialog'
import { DatastoreQuarantineDialog, useQuarantineNotice } from './DatastoreQuarantineDialog'
import { QuickCapture } from '@/components/capture/QuickCapture'
import { SnapIntoNote } from '@/components/capture/SnapIntoNote'
import { UrlImportDialog } from '@/components/capture/UrlImportDialog'
import { WindowDropOverlay } from './WindowDropOverlay'
import { MobileBottomBar } from './MobileBottomBar'
import { ReviewSyncNotice } from '@/features/review/ReviewSyncNotice'
import { ActivityButton } from './ActivityPopover'
import { NotificationBell } from './NotificationBell'
import { ProfileSwitcherMenu } from './ProfileSwitcherMenu'
import { SidebarFooter } from './SidebarFooter'
import { useThemePreference } from '@/components/theme/use-theme-preference'

const FileDock = lazy(() =>
  import('./FileDock').then((module) => ({ default: module.FileDock }))
)
import { UserMenu } from '@/components/ui/user-menu'
import { Popover } from '@/components/ui/popover'
import { AudioPlayerBar } from './AudioPlayerBar'
import { AudioPlayerProvider } from '@/lib/audio-player'
import { applySessionScopeChange } from '@/lib/audio-offline'
import { resolveSessionScope } from '@/lib/session-scope'
import { SidebarNav } from '@/components/ui/sidebar-nav'
import { Button } from '@/components/ui/button'
import { LectureRecorderDialog } from '@/features/lectures/LectureRecorderDialog'
import { loadLectureDraft, type LectureDraft } from '@/features/lectures/lectureDraft'
import { StudyChatPanel } from '@/features/chat/StudyChatPanel'
import { StudyChatProvider } from '@/features/chat/useStudyChat'
import { useActiveChatSession } from '@/features/chat/useChatSession'
import { useDueCount } from '@/features/review/useDueCount'
import { usePendingProposalCount } from '@/features/chat/usePendingProposalCount'
import { useReviewNudgeInterval } from '@/lib/review-nudges'
import { isTypingTarget } from '@/lib/shortcuts'
import {
  navigateWorkspaceSearch,
  stripFileParams,
} from '@/lib/workspace-search'
import { OnboardingWizard } from '@/features/onboarding/OnboardingWizard'
import {
  getScratchpad,
  listCourses,
  listProfiles,
  markProfileSettled,
  setActiveProfile,
  type ChatSession,
  type Course,
} from '@/lib/api'
import { getCurrentUser, logoutSession } from '@/lib/auth-session'
import { setLocale } from '@/lib/i18n'
import { availableLocales } from '@/lib/locales'
import { loadDemoMode, loadInstanceConfig } from './DemoBanner'
import { useChatStore } from '@/lib/chat-store'
import { useChatFitsAlongsideFile, useRailLayout } from '@/lib/dock-store'
import { useWorkspaceStore } from '@/lib/workspace-store'
import { fuzzyFilter } from '@/lib/fuzzy'
import { offlineJournal } from '@/lib/offline/journal'

import { cn } from '@/lib/utils'
import { storageKeys } from '@/lib/constants'
import { useIsShortViewport } from '@/lib/use-media-query'
import { PRIMARY_NAV, resolveActiveId } from '@/config/nav'

const DESTINATIONS: Array<{
  key: string
  icon: typeof Home
  labelKey: string
  tab?: string
}> = [
  { key: 'workspace', icon: Home, labelKey: 'nav.destWorkspace' },
  { key: 'materials', icon: FolderClosed, labelKey: 'nav.destMaterials', tab: 'materials' },
  { key: 'notes', icon: NotebookPen, labelKey: 'nav.destNotes', tab: 'notes' },
  { key: 'practice', icon: Dumbbell, labelKey: 'nav.destPractice', tab: 'practice' },
]

function CourseDot({ color }: { color: string | null }) {
  return (
    <span
      className="border-border size-2.5 shrink-0 rounded-full border"
      style={color ? { backgroundColor: color } : undefined}
      aria-hidden
    />
  )
}

function CourseOptionRow({
  course,
  selected,
  onPick,
}: {
  course: Course
  selected: boolean
  onPick: () => void
}) {
  const { t } = useTranslation()
  return (
    <button
      type="button"
      role="option"
      aria-selected={selected}
      className={cn(
        'hover:bg-subtle flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-xs',
        selected ? 'bg-primary/10 font-medium' : ''
      )}
      onClick={onPick}
    >
      <span
        className="flex size-6 shrink-0 items-center justify-center rounded text-[10px] font-semibold"
        style={{
          backgroundColor: `${course.color ?? '#6366f1'}22`,
          color: course.color ?? '#6366f1',
        }}
        aria-hidden
      >
        {(course.title.trim()[0] ?? '?').toUpperCase()}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate leading-tight">{course.title}</span>
        <span className="text-muted-foreground block truncate text-[10px] font-normal leading-tight">
          {course.subject ?? t('courses.noSubject')} · {t('courses.materialCount', { count: course.material_count })}
        </span>
      </span>
      <Check className={cn('size-3.5 shrink-0', selected ? 'text-primary' : 'text-transparent')} aria-hidden />
    </button>
  )
}

function CourseSwitcher({
  courses,
  courseId,
  selectLabel,
  allLabel,
  manageLabel,
  searchLabel,
  emptyLabel,
  label,
  onPick,
}: {
  courses: Course[]
  courseId: string | null
  selectLabel: string
  allLabel: string
  manageLabel: string
  searchLabel: string
  emptyLabel: string
  label: string
  onPick: (courseId: string | null) => void
}) {
  const [closeSignal, setCloseSignal] = useState(0)
  const [query, setQuery] = useState('')
  const pick = (nextId: string | null) => {
    setCloseSignal((current) => current + 1)
    onPick(nextId)
  }
  const filtered = useMemo(
    () => fuzzyFilter(courses, query, (course) => course.title),
    [courses, query]
  )
  return (
    <Popover
      label={label}
      align="start"
      panelClassName="w-72 p-2"
      closeSignal={closeSignal}
      triggerClassName="bg-surface border-border hover:bg-subtle focus-visible:outline-ring focus-visible:outline-2 focus-visible:outline-offset-1 group/switcher flex w-full items-center gap-2 rounded-md border px-2 py-2 text-left text-xs"
      trigger={
        <>
          <CourseDot color={courses.find((course) => course.id === courseId)?.color ?? null} />
          <span
            className={cn(
              'min-w-0 flex-1 truncate font-medium',
              courseId === null && 'text-muted-foreground'
            )}
          >
            {courseId === null
              ? selectLabel
              : (courses.find((course) => course.id === courseId)?.title ?? allLabel)}
          </span>
          <GraduationCap className="text-muted-foreground group-hover/switcher:text-foreground hidden size-4 shrink-0 sm:block" aria-hidden />
          <ChevronDown className="text-muted-foreground size-3.5 shrink-0 transition-transform" aria-hidden />
        </>
      }
    >
      <div className="space-y-2">
        {courses.length > 5 ? (
          <div className="border-border bg-surface flex items-center gap-2 rounded-md border px-2.5 py-1.5">
            <Search className="text-muted-foreground size-3.5 shrink-0" aria-hidden />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={searchLabel}
              aria-label={searchLabel}
              className="min-w-0 flex-1 bg-transparent text-xs outline-none"
            />
            {query ? (
              <button type="button" aria-label={searchLabel} onClick={() => setQuery('')}>
                <X className="text-muted-foreground hover:text-foreground size-3.5" aria-hidden />
              </button>
            ) : null}
          </div>
        ) : null}
        <div role="listbox" aria-label={label} className="max-h-64 space-y-0.5 overflow-y-auto">
          {filtered.map((course) => (
            <CourseOptionRow
              key={course.id}
              course={course}
              selected={course.id === courseId}
              onPick={() => pick(course.id)}
            />
          ))}
          {filtered.length > 0 ? (
            <div className="border-border my-1 border-t" aria-hidden />
          ) : null}
          <button
            type="button"
            role="option"
            aria-selected={courseId === null}
            className="hover:bg-subtle flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs"
            onClick={() => pick(null)}
          >
            <Layers className="text-muted-foreground size-3.5 shrink-0" aria-hidden />
            <span className="min-w-0 flex-1 truncate">{allLabel}</span>
            <Check className={cn('size-3.5 shrink-0', courseId === null ? 'text-primary' : 'text-transparent')} aria-hidden />
          </button>
          {filtered.length === 0 ? (
            <p className="text-muted-foreground px-2 py-3 text-center text-xs">{emptyLabel}</p>
          ) : null}
        </div>
        <div className="border-border space-y-0.5 border-t pt-2">
          <Link
            to="/courses"
            onClick={() => setCloseSignal((current) => current + 1)}
            className="hover:bg-subtle flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs"
          >
            <GraduationCap className="text-muted-foreground size-3.5 shrink-0" aria-hidden />
            <span className="min-w-0 flex-1 truncate">{manageLabel}</span>
            <ChevronRight className="text-muted-foreground size-3.5 shrink-0" aria-hidden />
          </Link>
        </div>
      </div>
    </Popover>
  )
}

function QuickDestinations({ courseId }: { courseId: string }) {
  const { t } = useTranslation()
  const search = useSearch({ strict: false }) as { tab?: string }
  const params = useParams({ strict: false }) as { courseId?: string }
  const activeTab = search.tab
  return (
    <div
      className="grid grid-cols-2 gap-1"
      role="group"
      aria-label={t('nav.quickDestinations')}
    >
      {DESTINATIONS.map((dest) => {
        const active =
          dest.tab === undefined
            ? !activeTab || activeTab === 'overview'
            : activeTab === dest.tab
        return (
          <Link
            key={dest.key}
            to="/courses/$courseId"
            params={{ courseId }}
            search={dest.tab ? { tab: dest.tab } : {}}
            aria-current={active && params.courseId === courseId ? 'page' : undefined}
            title={t(dest.labelKey)}
            className={cn(
              'focus-visible:outline-ring flex min-w-0 items-center gap-1.5 rounded-lg border px-2 py-1.5 text-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-1',
              active
                ? 'border-primary/30 bg-primary/10 font-medium'
                : 'border-transparent hover:border-border hover:bg-subtle'
            )}
          >
            <dest.icon className="size-3.5 shrink-0" aria-hidden />
            <span className="min-w-0 truncate">{t(dest.labelKey)}</span>
          </Link>
        )
      })}
    </div>
  )
}

function AppLogo() {
  const { t } = useTranslation()
  return (
    <Link
      to="/"
      className="focus-visible:outline-ring hover:bg-subtle flex items-center gap-2.5 rounded-md px-2 py-1.5 transition-colors focus-visible:outline-2 focus-visible:outline-offset-1"
      aria-label={t('nav.home')}
    >
      <svg
        className="size-7 shrink-0"
        viewBox="0 0 32 32"
        role="img"
        aria-hidden
      >
        <defs>
          <linearGradient id="sa-logo-grad" x1="0" y1="0" x2="32" y2="32">
            <stop offset="0%" stopColor="#6366f1" />
            <stop offset="100%" stopColor="#8b5cf6" />
          </linearGradient>
        </defs>
        <rect width="32" height="32" rx="8" fill="url(#ca-logo-grad)" />
        <path
          d="M16 8 25 12.5 16 17 7 12.5Z"
          fill="#fff"
          fillOpacity="0.95"
        />
        <path
          d="M10.5 15.4v4.3c0 .6 2.5 2.3 5.5 2.3s5.5-1.7 5.5-2.3v-4.3l-4.6 2.3a2 2 0 0 1-1.8 0Z"
          fill="#fff"
          fillOpacity="0.75"
        />
        <path d="M24 13.6v5.9" stroke="#fff" strokeOpacity="0.9" strokeWidth="1.4" strokeLinecap="round" />
        <circle cx="24" cy="20.5" r="1.2" fill="#fff" />
      </svg>
      <span className="text-base font-semibold">{t('app.name')}</span>
    </Link>
  )
}

const SessionScopeContext = createContext<{
  scope: string | null
  setScope: (scope: string | null) => void
} | null>(null)

function ProfileBoundary({ children }: { children: React.ReactNode }) {
  const [scope, setScopeState] = useState<string | null>(null)
  const scopeRef = useRef<string | null>(null)
  const setScope = useCallback((next: string | null) => {
    const previous = scopeRef.current
    if (previous === next) {
      return
    }
    scopeRef.current = next
    applySessionScopeChange(next)
    setScopeState(next)
  }, [])
  return (
    <SessionScopeContext.Provider value={{ scope, setScope }}>
      <AudioPlayerProvider scope={scope}>{children}</AudioPlayerProvider>
    </SessionScopeContext.Provider>
  )
}

function useSessionScope() {
  const value = useContext(SessionScopeContext)
  if (value === null) {
    throw new Error('useSessionScope must be used inside ProfileBoundary')
  }
  return value
}

export function AppShell() {
  return (
    <ProfileBoundary>
      <AppShellInner />
    </ProfileBoundary>
  )
}

function AppShellInner() {
  const { t, i18n } = useTranslation()
  const { setScope } = useSessionScope()
  const location = useLocation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const params = useParams({ strict: false }) as { courseId?: string; nodeId?: string }
  const workspaceSearch = useSearch({ strict: false }) as {
    material?: string
    note?: string
    study?: string
  }
  const fileOpen = fileDockOpen(workspaceSearch)
  const rail = useRailLayout(fileOpen)
  const chatFits = useChatFitsAlongsideFile(fileOpen)
  const chatOpen = useChatStore((state) => state.open)
  const chatSession = useChatStore((state) => state.session)
  const setOpen = useChatStore((state) => state.setOpen)
  const setChatSession = useChatStore((state) => state.setSession)
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: listProfiles })
  const courses = useQuery({ queryKey: ['courses'], queryFn: listCourses })
  const scratchpad = useQuery({ queryKey: ['scratchpad'], queryFn: getScratchpad })
  const courseId = useWorkspaceStore((state) => state.courseId)
  const setCourse = useWorkspaceStore((state) => state.setCourse)
  const [selected, setSelected] = useState<string | null>(null)
  const [shortcutsOpen, setShortcutsOpen] = useState(false)
  const [lectureDraft, setLectureDraft] = useState<LectureDraft | null>(null)
  const [lectureOpen, setLectureOpen] = useState(false)
  const [lectureDismissed, setLectureDismissed] = useState(false)
  const palette = useCommandPaletteOpen()
  useEffect(() => {
    setLectureDraft(loadLectureDraft())
  }, [])
  const shortViewport = useIsShortViewport()
  const dueCount = useDueCount()
  const pendingProposals = usePendingProposalCount()
  // User-menu state: the signed-in identity (module state, fixed by the
  // boot flow), the shared theme preference and the demo-instance flag
  // (identity-auth §13) for the status pill.
  const user = getCurrentUser()
  const [theme, setTheme] = useThemePreference()
  const [demoMode, setDemoMode] = useState(false)
  const quarantine = useQuarantineNotice()
  const [updateCheck, setUpdateCheck] = useState<Awaited<
    ReturnType<typeof loadUpdateCheck>
  >>(null)
  useEffect(() => {
    let alive = true
    void loadUpdateCheck().then((value) => {
      if (alive) setUpdateCheck(value)
    })
    return () => {
      alive = false
    }
  }, [])
  const canSeeUpdateRow = Boolean(getCurrentUser()?.is_admin)
  useEffect(() => {
    let alive = true
    void loadDemoMode().then((value) => {
      if (alive) setDemoMode(value)
    })
    return () => {
      alive = false
    }
  }, [])
  useReviewNudgeInterval()
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === '?' && !isTypingTarget(event.target)) {
        event.preventDefault()
        setShortcutsOpen((open) => !open)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  const courseList = courses.data ?? []
  // memoized: the §15 reconciliation effect below depends on the list and
  // must not see a fresh `[]` identity on every render
  const profileList = useMemo(() => profiles.data ?? [], [profiles.data])
  const activeCourse = courseList.find((course) => course.id === courseId) ?? null

  useEffect(() => {
    let storedProfileId: string | null = null
    try {
      const raw = window.localStorage.getItem(storageKeys.profileId)
      if (raw && raw.length > 0) {
        storedProfileId = raw
      }
    } catch {
      storedProfileId = null
    }
    setSelected(storedProfileId)
    setActiveProfile(storedProfileId)
  }, [])

  // Profile-selection reconciliation (identity-auth §15): server (web)
  // mode has no silent default — a null selection must adopt the Default
  // profile once the list loads, or every non-exempt boot query 400s
  // with "X-Profile-Id required". Desktop keeps null = the middleware's
  // last-used fallback. Both modes repair a selection that no longer
  // exists (dev DBs get recreated; profiles can be deleted elsewhere).
  const [authMode, setAuthMode] = useState<string | undefined>(undefined)
  const [identityMode, setIdentityMode] = useState<string | undefined>(undefined)
  useEffect(() => {
    let alive = true
    void loadInstanceConfig().then((config) => {
      if (alive) {
        setAuthMode(config?.auth_mode)
        setIdentityMode(config?.identity_mode)
        // config unresolvable: fail open — release the gate so requests
        // behave exactly as before this reconciliation existed
        if (config === undefined) markProfileSettled()
      }
    })
    return () => {
      alive = false
    }
  }, [])

  const defaultProfile =
    profileList.find((profile) => profile.is_default) ?? profileList[0] ?? null
  const scopeProfileId =
    selected ?? (identityMode === 'desktop' ? defaultProfile?.id ?? null : null)
  const sessionScope = resolveSessionScope(user, scopeProfileId)

  useEffect(() => {
    setScope(sessionScope)
  }, [sessionScope, setScope])

  useEffect(() => {
    if (authMode === undefined) {
      return // instance facts still loading — profile-scoped requests stay gated
    }
    if (profileList.length > 0) {
      const known = selected !== null && profileList.some((profile) => profile.id === selected)
      if (!known && !(selected === null && authMode !== 'authenticated')) {
        const fallback = profileList.find((profile) => profile.is_default) ?? profileList[0]
        if (fallback !== undefined && fallback.id !== selected) {
          setSelected(fallback.id)
          setActiveProfile(fallback.id)
          try {
            window.localStorage.setItem(storageKeys.profileId, fallback.id)
          } catch {
            // best-effort persistence; the in-memory switch still works
          }
          void queryClient.invalidateQueries()
        }
      }
    }
    // the selection is decided (or there is nothing to scope with) —
    // release the §15 boot gate; later switches are explicit user actions
    markProfileSettled()
  }, [selected, profileList, authMode, queryClient])

  useEffect(() => {
    if (courses.data === undefined || courseId === null) {
      return
    }
    if (!courses.data.some((course) => course.id === courseId)) {
      setCourse(null)
    }
  }, [courses.data, courseId, setCourse])

  const openCourse = async (targetId: string | null) => {
    if (targetId !== courseId) {
      setCourse(targetId)
      await queryClient.invalidateQueries()
    }
    if (targetId !== null) {
      void navigate({ to: '/courses/$courseId', params: { courseId: String(targetId) } })
    } else {
      void navigate({ to: '/courses' })
    }
  }

  const { chatId, sessionId } = useActiveChatSession()

  const adoptSidebarSession = (session: ChatSession) => {
    setChatSession({ id: session.id, publicId: session.public_id })
  }

  const onNewChat = () => {
    setChatSession(null)
  }

  const expandChat = () => {
    setOpen(false)
    const targetId = chatId ?? chatSession?.publicId ?? null
    if (targetId !== null) {
      void navigate({ to: '/chat/$chatId', params: { chatId: targetId } })
    } else {
      void navigate({ to: '/chat' })
    }
  }

  const closeChat = () => {
    setOpen(false)
  }

  const toggleChat = () => {
    if (chatOpen) {
      setOpen(false)
      return
    }
    if (!chatFits) {
      navigateWorkspaceSearch(navigate, params, stripFileParams)
    }
    setOpen(true)
  }

  useEffect(() => {
    if (chatOpen && location.pathname.startsWith('/chat')) {
      setOpen(false)
    }
  }, [chatOpen, location.pathname, setOpen])

  const switchProfile = async (profileId: string | null) => {
    setSelected(profileId)
    setActiveProfile(profileId)
    try {
      if (profileId === null) {
        window.localStorage.removeItem(storageKeys.profileId)
      } else {
        window.localStorage.setItem(storageKeys.profileId, profileId)
      }
    } catch {
      // profile persistence is best-effort; the in-memory switch still works
    }
    await queryClient.invalidateQueries()
  }

  return (
    <div className="bg-surface text-foreground flex h-[100dvh] overflow-hidden">
      <aside className="border-border bg-subtle hidden w-60 shrink-0 border-r md:block">
        <SidebarNav
          items={PRIMARY_NAV.map(({ to, icon, labelKey }) => ({
            id: to,
            label: t(labelKey),
            icon,
            badge:
              to === '/review' && dueCount > 0
                ? String(dueCount)
                : to === '/chat' && pendingProposals > 0
                  ? String(pendingProposals)
                  : undefined,
          }))}
          activeId={resolveActiveId(location.pathname)}
          onNavigate={(id) => void navigate({ to: id })}
          labels={{ navAria: t('nav.primary') }}
          compact={shortViewport}
          className="h-full w-full border-r-0 bg-transparent"
          header={
            <div className="border-border bg-subtle space-y-2 border-b px-3 pb-3">
              <div className="pt-3">
                <AppLogo />
              </div>
              <button
                type="button"
                className="focus-visible:outline-ring text-muted-foreground hover:text-foreground border-border hover:border-border bg-surface flex w-full items-center gap-2 rounded-md border px-2.5 py-2 text-left text-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-1"
                title={t('palette.shortcut')}
                aria-label={t('palette.shortcut')}
                onClick={palette.openPalette}
              >
                <Search className="size-3.5 shrink-0" aria-hidden />
                <span className="flex-1">{t('palette.searchLabel')}</span>
                <kbd className="text-muted-foreground rounded border border-border px-1 text-[10px]">{t('palette.ctrlK')}</kbd>
              </button>
              <button
                type="button"
                className="focus-visible:outline-ring text-muted-foreground hover:text-foreground border-border hover:border-border bg-surface flex w-full items-center gap-2 rounded-md border px-2.5 py-2 text-left text-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-1"
                title={t('shortcuts.title')}
                aria-label={t('shortcuts.title')}
                onClick={() => setShortcutsOpen(true)}
              >
                <Keyboard className="size-3.5 shrink-0" aria-hidden />
                <span className="flex-1">{t('shortcuts.searchLabel')}</span>
                <kbd className="text-muted-foreground rounded border border-border px-1 text-[10px]">?</kbd>
              </button>
              {courseList.length > 0 ? (
                <>
                  <CourseSwitcher
                    courses={courseList}
                    courseId={courseId}
                    selectLabel={t('nav.selectCourse')}
                    allLabel={t('workspace.allCourses')}
                    manageLabel={t('nav.courses')}
                    searchLabel={t('nav.searchCourses')}
                    emptyLabel={t('nav.noCoursesMatch')}
                    label={t('workspace.select')}
                    onPick={(next) => void openCourse(next)}
                  />
                  {activeCourse ? <QuickDestinations courseId={String(activeCourse.id)} /> : null}
                </>
              ) : (
                <Link
                  to="/courses"
                  className="focus-visible:outline-ring border-border bg-surface text-muted-foreground hover:text-foreground hover:bg-subtle flex items-center gap-2 rounded-md border px-2 py-2 text-xs focus-visible:outline-2 focus-visible:outline-offset-1"
                >
                  <Plus className="size-3.5" aria-hidden />
                  {t('nav.createCourse')}
                </Link>
              )}
              {scratchpad.data !== undefined && scratchpad.data.content_count > 0 ? (
                <button
                  type="button"
                  className="focus-visible:outline-ring text-muted-foreground hover:text-foreground hover:bg-subtle flex w-full items-center gap-2 rounded-md px-2 py-2 text-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-1"
                  title={t('nav.scratchpad')}
                  onClick={() => void openCourse(scratchpad.data!.course.id)}
                >
                  <FlaskConical className="size-3.5 shrink-0" aria-hidden />
                  <span className="flex-1 truncate text-left">{t('nav.scratchpad')}</span>
                </button>
              ) : null}
            </div>
          }
          footer={
            <div className="space-y-2">
              <UserMenu
                className="w-full"
                triggerClassName="w-full rounded-md"
                switcher={
                  <ProfileSwitcherMenu
                    profiles={profileList}
                    selectedId={selected}
                    loading={profiles.isLoading}
                    onSelect={(profileId) => void switchProfile(profileId)}
                  />
                }
                contentClassName="overflow-visible"
                user={
                  user
                    ? { name: user.full_name || undefined, email: user.email }
                    : undefined
                }
                labels={{ openMenu: t('auth.accountMenu') }}
                status={demoMode ? { label: t('demo.badge'), tone: 'warning' } : undefined}
                theme={theme}
                onThemeChange={setTheme}
                themeLabels={{
                  light: t('theme.light'),
                  dark: t('theme.dark'),
                  system: t('theme.system'),
                }}
                language={i18n.resolvedLanguage ?? 'en'}
                onLanguageChange={(code) => void setLocale(code)}
                languages={availableLocales().map((locale) => ({
                  id: locale.code,
                  label: locale.name,
                }))}
                items={[
                  { id: 'settings', label: t('nav.settings'), icon: Settings },
                  { id: 'about', label: t('nav.about'), icon: Info },
                  ...(canSeeUpdateRow &&
                  updateCheck?.update_available &&
                  updateCheck.latest_version
                    ? [
                        {
                          id: 'update',
                          label: t('update.releaseNotes'),
                          icon: Download,
                        },
                      ]
                    : []),
                ]}
                onItemSelect={(id) => {
                  if (id === 'settings') void navigate({ to: '/settings' })
                  if (id === 'about') void navigate({ to: '/about' })
                  if (id === 'update' && updateCheck) {
                    window.open(updateCheck.release_url, '_blank', 'noreferrer')
                  }
                }}
                onLogout={() => void logoutSession()}
                logoutLabel={t('auth.signOut')}
              />
              <div className="flex items-center justify-end gap-1 pt-1">
                <NotificationBell />
                <ActivityButton />
                <button
                  type="button"
                  className={cn(
                    'focus-visible:outline-ring rounded-md p-2 transition-colors focus-visible:outline-2 focus-visible:outline-offset-1',
                    chatOpen
                      ? 'bg-surface text-foreground'
                      : 'text-muted-foreground hover:text-foreground'
                  )}
                  title={chatOpen ? t('chat.close') : t('chat.open')}
                  aria-pressed={chatOpen}
                  onClick={toggleChat}
                >
                  <MessageSquare className="size-4" aria-hidden />
                </button>
              </div>
              {shortViewport ? (
                <div className="pt-1">
                  <SidebarFooter compact />
                </div>
              ) : (
                <div className="pt-3">
                  <div
                    aria-hidden
                    className="via-border bg-linear-to-r from-transparent h-px to-transparent"
                  />
                  <div className="pt-3">
                    <SidebarFooter />
                  </div>
                </div>
              )}
            </div>
          }
        />
      </aside>
      <main className="flex-1 overflow-y-auto pb-20 md:pb-0">
        <Suspense
          fallback={
            <div className="mx-auto max-w-4xl space-y-3 p-8" aria-busy="true">
              <div className="bg-subtle h-8 w-52 animate-pulse rounded" />
              <div className="bg-subtle h-24 w-full animate-pulse rounded-lg" />
              <div className="bg-subtle h-40 w-full animate-pulse rounded-lg" />
            </div>
          }
        >
          <RouteFade />
        </Suspense>
      </main>
      {lectureDraft && !lectureDismissed ? (
        <div
          className="bg-surface border-border fixed bottom-4 left-1/2 z-40 flex w-[min(92vw,40rem)] -translate-x-1/2 items-center gap-3 rounded-lg border px-3 py-2 shadow-[var(--as-shadow-3)]"
          role="status"
        >
          <AudioLines className="text-primary size-4 shrink-0" aria-hidden />
          <p className="min-w-0 flex-1 text-xs">
            {t('lectures.recoveryBanner', { title: lectureDraft.title })}
          </p>
          <Button size="sm" onClick={() => setLectureOpen(true)}>
            {t('lectures.resumeUpload')}
          </Button>
          <button
            type="button"
            className="text-muted-foreground hover:text-foreground text-xs underline"
            onClick={() => setLectureDismissed(true)}
          >
            {t('lectures.later')}
          </button>
        </div>
      ) : null}
      {lectureOpen && lectureDraft ? (
        <LectureRecorderDialog
          courseId={lectureDraft.courseId}
          nodeId={lectureDraft.nodeId}
          onClose={() => {
            setLectureOpen(false)
            setLectureDraft(loadLectureDraft())
          }}
          onCreated={() => {
            setLectureDraft(null)
            setLectureOpen(false)
          }}
        />
      ) : null}
      <AudioPlayerBar />
      {fileOpen ? (
        <Suspense fallback={null}>
          <FileDock />
        </Suspense>
      ) : null}
      {chatOpen && !rail.chatDeferred ? (
        <StudyChatProvider sessionId={sessionId ?? chatSession?.id ?? null}>
          <StudyChatPanel
            layoutWidth={rail.chatWidth ?? undefined}
            onSessionCreated={adoptSidebarSession}
            onSelectSession={adoptSidebarSession}
            onNewChat={onNewChat}
            onClose={closeChat}
            onExpand={expandChat}
          />
        </StudyChatProvider>
      ) : null}
      <CommandPalette open={palette.open} onClose={palette.close} />
      {shortcutsOpen ? <ShortcutsDialog onClose={() => setShortcutsOpen(false)} /> : null}
      <FocusTimer />
      <QuickCapture />
      <SnapIntoNote />
      <UrlImportDialog />
      <WindowDropOverlay />
      <ReviewSyncNotice />
      <MobileBottomBar
        activePath={location.pathname}
        dueCount={dueCount}
        onNavigate={(path) => void navigate({ to: path as never })}
        onCapture={async (files) => {
          for (const file of Array.from(files)) {
            await offlineJournal.enqueueCapture(file, 'camera')
          }
          window.dispatchEvent(new Event('sa-capture-enqueued'))
          await navigate({ to: '/library' })
        }}
        onSearch={palette.openPalette}
      />
      {quarantine.notice ? (
        <DatastoreQuarantineDialog
          notice={quarantine.notice}
          onDismiss={quarantine.dismiss}
        />
      ) : (
        <OnboardingWizard />
      )}
    </div>
  )
}
