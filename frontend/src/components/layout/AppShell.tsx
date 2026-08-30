import { Outlet, useLocation, Link, useNavigate, useParams, useSearch } from '@tanstack/react-router'
import {
  BarChart3,
  BookOpen,
  Bot,
  Check,
  ChevronDown,
  ChevronRight,
  Dumbbell,
  FolderClosed,
  GraduationCap,
  Home,
  Info,
  Layers,
  MessageSquare,
  NotebookPen,
  Plus,
  Search,
  Settings,
  UserRound,
  X,
} from 'lucide-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { CommandPalette, useCommandPaletteOpen } from './CommandPalette'
import { WindowDropOverlay } from './WindowDropOverlay'
import { ActivityButton } from './ActivityPopover'
import { ProfileDialog } from './ProfileDialog'
import { ThemeToggle } from '@/components/theme/ThemeToggle'
import { Popover } from '@/components/ui/popover'
import { ChatPanel } from '@/features/chat/ChatPanel'
import { useActiveChatSession } from '@/features/chat/useChatSession'
import { OnboardingWizard } from '@/features/onboarding/OnboardingWizard'
import { listCourses, listProfiles, setActiveProfile, type ChatSession, type Course } from '@/lib/api'
import { useChatStore } from '@/lib/chat-store'
import { useWorkspaceStore } from '@/lib/workspace-store'
import { fuzzyFilter } from '@/lib/fuzzy'

import { cn } from '@/lib/utils'

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

const NAV_ITEMS = [
  { to: '/', icon: Home, labelKey: 'nav.home', exact: true },
  { to: '/courses', icon: GraduationCap, labelKey: 'nav.courses', exact: false },
  { to: '/chat', icon: Bot, labelKey: 'nav.chat', exact: false },
  { to: '/library', icon: BookOpen, labelKey: 'nav.library', exact: false },
  { to: '/scores', icon: BarChart3, labelKey: 'nav.scores', exact: false },
] as const

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
  courseId: number | null
  selectLabel: string
  allLabel: string
  manageLabel: string
  searchLabel: string
  emptyLabel: string
  label: string
  onPick: (courseId: number | null) => void
}) {
  const [closeSignal, setCloseSignal] = useState(0)
  const [query, setQuery] = useState('')
  const pick = (nextId: number | null) => {
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
          <linearGradient id="ca-logo-grad" x1="0" y1="0" x2="32" y2="32">
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

export function AppShell() {
  const { t } = useTranslation()
  const location = useLocation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const chatOpen = useChatStore((state) => state.open)
  const chatSession = useChatStore((state) => state.session)
  const setOpen = useChatStore((state) => state.setOpen)
  const setChatSession = useChatStore((state) => state.setSession)
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: listProfiles })
  const courses = useQuery({ queryKey: ['courses'], queryFn: listCourses })
  const courseId = useWorkspaceStore((state) => state.courseId)
  const setCourse = useWorkspaceStore((state) => state.setCourse)
  const [selected, setSelected] = useState<number | null>(null)
  const [profilesOpen, setProfilesOpen] = useState(false)
  const palette = useCommandPaletteOpen()
  const courseList = courses.data ?? []
  const profileList = profiles.data ?? []
  const activeCourse = courseList.find((course) => course.id === courseId) ?? null

  useEffect(() => {
    let storedProfileId: number | null = null
    try {
      const raw = window.localStorage.getItem('ca-profile-id')
      if (raw) {
        const value = Number(raw)
        if (Number.isFinite(value)) {
          storedProfileId = value
        }
      }
    } catch {
      storedProfileId = null
    }
    setSelected(storedProfileId)
    setActiveProfile(storedProfileId)
  }, [])

  useEffect(() => {
    if (courses.data === undefined || courseId === null) {
      return
    }
    if (!courses.data.some((course) => course.id === courseId)) {
      setCourse(null)
    }
  }, [courses.data, courseId, setCourse])

  const openCourse = async (targetId: number | null) => {
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

  useEffect(() => {
    if (location.pathname.startsWith('/chat')) {
      setOpen(false)
    }
  }, [location.pathname, setOpen])

  const switchProfile = async (profileId: number | null) => {
    setSelected(profileId)
    setActiveProfile(profileId)
    try {
      if (profileId === null) {
        window.localStorage.removeItem('ca-profile-id')
      } else {
        window.localStorage.setItem('ca-profile-id', String(profileId))
      }
    } catch {
      // profile persistence is best-effort; the in-memory switch still works
    }
    await queryClient.invalidateQueries()
  }

  return (
    <div className="bg-surface text-foreground flex h-screen overflow-hidden">
      <aside className="border-border bg-subtle flex w-60 shrink-0 flex-col border-r">
        <div className="border-border border-b px-3 py-3">
          <AppLogo />
        </div>
        <div className="border-border space-y-2 border-b px-3 py-3">
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
        </div>
        <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto p-3" aria-label={t('nav.primary')}>
          {NAV_ITEMS.map((item) => {
            const active = item.exact
              ? location.pathname === item.to
              : location.pathname.startsWith(item.to)
            return (
              <Link
                key={item.to}
                to={item.to}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  'focus-visible:outline-ring flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-1',
                  active
                    ? 'bg-surface font-medium'
                    : 'text-muted-foreground hover:text-foreground'
                )}
              >
                <item.icon className="size-4" aria-hidden />
                {t(item.labelKey)}
              </Link>
            )
          })}
        </nav>
        <div className="space-y-2 border-t border-border p-3">
          <Link
            to="/settings"
            aria-current={location.pathname.startsWith('/settings') ? 'page' : undefined}
            className={cn(
              'focus-visible:outline-ring flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-1',
              location.pathname.startsWith('/settings')
                ? 'bg-surface font-medium'
                : 'text-muted-foreground hover:text-foreground'
            )}
          >
            <Settings className="size-4" aria-hidden />
            {t('nav.settings')}
          </Link>
          <Link
            to="/about"
            aria-current={location.pathname === '/about' ? 'page' : undefined}
            className={cn(
              'focus-visible:outline-ring flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-1',
              location.pathname === '/about'
                ? 'bg-surface font-medium'
                : 'text-muted-foreground hover:text-foreground'
            )}
          >
            <Info className="size-4" aria-hidden />
            {t('nav.about')}
          </Link>
          <button
            type="button"
            className={cn(
              'focus-visible:outline-ring flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-1',
              'text-muted-foreground hover:text-foreground'
            )}
            title={t('profiles.manage')}
            onClick={() => setProfilesOpen(true)}
          >
            <UserRound className="size-4" aria-hidden />
            <span className="min-w-0 flex-1 truncate text-left">
              {selected === null
                ? t('profiles.default')
                : (profileList.find((profile) => profile.id === selected)?.name ??
                  t('profiles.default'))}
            </span>
            <ChevronDown className="size-3.5 shrink-0" aria-hidden />
          </button>
          <div className="flex items-center justify-between pt-1">
            <ThemeToggle />
            <div className="flex items-center gap-1">
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
                onClick={() => (chatOpen ? closeChat() : setOpen(true))}
              >
                <MessageSquare className="size-4" aria-hidden />
              </button>
            </div>
          </div>
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
      {chatOpen ? (
        <ChatPanel
          sessionId={sessionId ?? chatSession?.id ?? null}
          onSessionCreated={adoptSidebarSession}
          onSelectSession={adoptSidebarSession}
          onNewChat={onNewChat}
          onClose={closeChat}
          onExpand={expandChat}
        />
      ) : null}
      <CommandPalette open={palette.open} onClose={palette.close} />
      <WindowDropOverlay />
      {profilesOpen ? (
        <ProfileDialog
          profiles={profileList}
          selectedId={selected}
          onSelect={(profileId) => void switchProfile(profileId)}
          onClose={() => setProfilesOpen(false)}
        />
      ) : null}
      <OnboardingWizard />
    </div>
  )
}
