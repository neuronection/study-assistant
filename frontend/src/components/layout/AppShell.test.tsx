import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { AppShell } from './AppShell'
import { useChatStore } from '@/lib/chat-store'
import { useWorkspaceStore } from '@/lib/workspace-store'

const chatPanelState = vi.hoisted(() => ({
  props: null as Record<string, unknown> | null,
}))

const listCourses = vi.fn()
const listProfiles = vi.fn()
const createProfileFn = vi.fn()
const navigate = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listCourses: () => listCourses(),
    listProfiles: () => listProfiles(),
    createProfile: (name: string) => createProfileFn(name),
  }
})

vi.mock('@tanstack/react-router', () => ({
  Outlet: () => <div>outlet-content</div>,
  Link: ({
    children,
    to,
    params,
    search,
  }: {
    children: React.ReactNode
    to: string
    params?: Record<string, string>
    search?: { tab?: string }
  }) => {
    let href = to
    for (const [key, value] of Object.entries(params ?? {})) {
      href = href.replace(`$${key}`, value)
    }
    if (search?.tab) {
      href += `?tab=${search.tab}`
    }
    return <a href={href}>{children}</a>
  },
  useLocation: () => ({ pathname: '/' }),
  useNavigate: () => navigate,
  useParams: () => ({}),
  useSearch: () => ({}),
  useRouterState: ({ select }: { select: (state: unknown) => unknown }) =>
    select({ location: { pathname: '/' } }),
}))

vi.mock('./CommandPalette', () => ({
  CommandPalette: () => null,
  useCommandPaletteOpen: () => ({ open: false, close: vi.fn(), openPalette: vi.fn() }),
}))

vi.mock('@/features/chat/ChatPanel', () => ({
  ChatPanel: (props: Record<string, unknown>) => {
    chatPanelState.props = props
    return null
  },
}))

const COURSES = [
  {
    id: 1,
    title: 'Calculus I',
    subject: null,
    level: null,
    description: null,
    color: '#3366cc',
    archived_at: null,
    material_count: 2,
  },
  {
    id: 2,
    title: 'Linear Algebra',
    subject: null,
    level: null,
    description: null,
    color: '#cc3366',
    archived_at: null,
    material_count: 1,
  },
]

function renderShell() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <AppShell />
    </QueryClientProvider>
  )
}

describe('AppShell rail', () => {
  beforeEach(() => {
    listCourses.mockReset()
    listProfiles.mockReset()
    createProfileFn.mockReset()
    listCourses.mockResolvedValue(COURSES)
    listProfiles.mockResolvedValue([{ id: 1, name: 'Default', color: null }])
    navigate.mockReset()
    useWorkspaceStore.getState().setCourse(null)
    useChatStore.setState({ open: false, session: null })
    chatPanelState.props = null
  })

  test('renders primary navigation without removed flat pages', async () => {
    renderShell()
    expect(await screen.findByRole('navigation', { name: 'Main navigation' })).toBeInTheDocument()
    expect(screen.queryByText('Dev')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /rendering spike/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Flashcards' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Quiz' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Exercises' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Notes' })).not.toBeInTheDocument()
    // primary nav entries are controlled buttons (SidebarNav) — the router
    // stays app-side; Settings is pinned via secondaryItems, About lives in
    // the footer project block
    expect(screen.getByRole('button', { name: 'Scores' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Tutor' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Settings' })).toBeInTheDocument()
  })

  test('sidebar footer shows the family block, About pill and app version', async () => {
    renderShell()
    expect(await screen.findByText('More from the family')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'About' })).toBeInTheDocument()
    expect(screen.getByText(/^v\d+\.\d+\.\d+/)).toBeInTheDocument()
  })

  test('course switcher lists courses and picking one activates the course and navigates', async () => {
    renderShell()
    const switcher = await screen.findByRole('button', { name: 'Current course' })
    expect(within(switcher).getByText('Select a course')).toBeInTheDocument()
    fireEvent.click(switcher)
    const listbox = await screen.findByRole('listbox', { name: 'Current course' })
    expect(within(listbox).getByRole('option', { name: /calculus i/i })).toBeInTheDocument()
    expect(within(listbox).getByRole('option', { name: /linear algebra/i })).toBeInTheDocument()

    fireEvent.click(within(listbox).getByRole('option', { name: /linear algebra/i }))
    await waitFor(() => expect(useWorkspaceStore.getState().courseId).toBe(2))
    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith({
        to: '/courses/$courseId',
        params: { courseId: '2' },
      })
    )
  })

  test('switcher keeps an explicit all-courses row', async () => {
    useWorkspaceStore.getState().setCourse(1)
    renderShell()
    fireEvent.click(await screen.findByRole('button', { name: 'Current course' }))
    const listbox = await screen.findByRole('listbox', { name: 'Current course' })
    fireEvent.click(within(listbox).getByRole('option', { name: /all courses/i }))
    await waitFor(() => expect(useWorkspaceStore.getState().courseId).toBe(null))
  })

  test('profile button opens an overlay to switch and create profiles', async () => {
    createProfileFn.mockResolvedValue({ id: 9, name: 'New', color: null })
    renderShell()
    fireEvent.click(await screen.findByTitle('Profiles'))
    const dialog = await screen.findByRole('dialog', { name: 'Profiles' })
    expect(within(dialog).getByText('Default profile')).toBeInTheDocument()
    expect(within(dialog).queryByPlaceholderText('Profile name…')).not.toBeInTheDocument()

    fireEvent.click(within(dialog).getByRole('button', { name: /add a profile/i }))
    fireEvent.change(await within(dialog).findByPlaceholderText('Profile name…'), {
      target: { value: 'New' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: /^add$/i }))
    await waitFor(() => expect(createProfileFn).toHaveBeenCalledWith('New'))
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'Profiles' })).not.toBeInTheDocument()
    )
  })

  test('active course shows quick destinations for workspace, materials, notes and practice', async () => {
    useWorkspaceStore.getState().setCourse(1)
    renderShell()
    const grid = await screen.findByRole('group', { name: 'Course shortcuts' })
    expect(within(grid).getByRole('link', { name: 'Workspace' })).toHaveAttribute(
      'href',
      '/courses/1'
    )
    expect(within(grid).getByRole('link', { name: 'Materials' })).toHaveAttribute(
      'href',
      '/courses/1?tab=materials'
    )
    expect(within(grid).getByRole('link', { name: 'Notes' })).toHaveAttribute(
      'href',
      '/courses/1?tab=notes'
    )
    expect(within(grid).getByRole('link', { name: 'Practice' })).toHaveAttribute(
      'href',
      '/courses/1?tab=practice'
    )
  })

  test('primary navigation routes Courses through onNavigate', async () => {
    renderShell()
    expect(await screen.findByRole('navigation', { name: 'Main navigation' })).toBeInTheDocument()
    await fireEvent.click(screen.getByRole('button', { name: 'Courses' }))
    expect(navigate).toHaveBeenCalledWith({ to: '/courses' })
  })

  test('switcher popover always links to the Courses page', async () => {
    useWorkspaceStore.getState().setCourse(1)
    renderShell()
    fireEvent.click(await screen.findByRole('button', { name: 'Current course' }))
    const dialog = await screen.findByRole('dialog', { name: 'Current course' })
    expect(within(dialog).getByRole('link', { name: 'Courses' })).toHaveAttribute(
      'href',
      '/courses'
    )
  })

  test('shows a create-course CTA when no courses exist', async () => {
    listCourses.mockResolvedValue([])
    renderShell()
    const cta = await screen.findByRole('link', { name: /create course/i })
    expect(cta).toHaveAttribute('href', '/courses')
    expect(screen.queryByRole('button', { name: 'Current course' })).not.toBeInTheDocument()
  })

  test('sidebar chat stays open and adopts a session created on first send', async () => {
    renderShell()
    fireEvent.click(await screen.findByTitle('Open chat'))
    expect(chatPanelState.props).not.toBeNull()
    expect(chatPanelState.props?.sessionId).toBeNull()

    const onSessionCreated = chatPanelState.props?.onSessionCreated as (
      session: unknown,
    ) => void
    onSessionCreated({
      id: 7,
      public_id: 'uuid-7',
      course_id: null,
      node_id: null,
      title: 'New chat',
      created_at: new Date().toISOString(),
    })

    await waitFor(() => expect(chatPanelState.props?.sessionId).toBe(7))
    expect(navigate).not.toHaveBeenCalled()
  })

  test('sidebar history select and new-chat stay in the sidepanel', async () => {
    renderShell()
    fireEvent.click(await screen.findByTitle('Open chat'))

    const onSelectSession = chatPanelState.props?.onSelectSession as (
      session: unknown,
    ) => void
    onSelectSession({
      id: 9,
      public_id: 'uuid-9',
      course_id: null,
      node_id: null,
      title: 'New chat',
      created_at: new Date().toISOString(),
    })
    await waitFor(() => expect(chatPanelState.props?.sessionId).toBe(9))
    expect(navigate).not.toHaveBeenCalled()

    const onNewChat = chatPanelState.props?.onNewChat as () => void
    onNewChat()
    await waitFor(() => expect(chatPanelState.props?.sessionId).toBeNull())
    expect(navigate).not.toHaveBeenCalled()
  })

  test('node-ask pins the sidepanel to the store session and expand goes full page', async () => {
    act(() => useChatStore.getState().openSession({ id: 5, publicId: 'uuid-5' }))
    renderShell()
    expect(await screen.findByTitle('Close chat')).toBeInTheDocument()
    expect(chatPanelState.props?.sessionId).toBe(5)

    const onExpand = chatPanelState.props?.onExpand as () => void
    onExpand()
    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith({
        to: '/chat/$chatId',
        params: { chatId: 'uuid-5' },
      })
    )
    await waitFor(() => expect(useChatStore.getState().open).toBe(false))
  })
})
