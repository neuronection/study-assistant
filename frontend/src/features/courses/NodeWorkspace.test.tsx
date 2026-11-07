import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, test } from 'vitest'
import {
  courseTree,
  listFolders,
  nodeWorkspace,
  updateCourse,
  updateNode,
  ROOT_WS,
  NODE_WS,
  primeDefaults,
  renderWorkspace,
  navigateMock,
} from './workspace/__tests__/harness'

describe('Shell', () => {
  test('workspace gate renders a layout-shaped skeleton while the tree loads', async () => {
    primeDefaults()
    courseTree.mockReturnValue(new Promise(() => {}))
    const { container } = renderWorkspace('/courses/3')
    await waitFor(() =>
      expect(container.querySelector('[aria-busy="true"]')).not.toBeNull()
    )
    expect(container.querySelectorAll('[data-as="skeleton"]').length).toBeGreaterThan(4)
    expect(document.querySelector('.animate-spin')).toBeNull()
  })

  test('node workspace renders breadcrumb and sidebar focus', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5')
    expect(await screen.findByRole('heading', { name: 'Derivatives' })).toBeInTheDocument()
    const crumb = within(screen.getByRole('navigation', { name: 'Breadcrumb' })).getByRole(
      'link',
      { name: 'Calculus I' }
    )
    expect(crumb).toHaveAttribute('href', '/courses/3')
    expect(screen.queryByRole('button', { name: /ai outline/i })).not.toBeInTheDocument()
    const sidebarRoot = screen.getAllByRole('link', { name: 'Calculus I' }).find(
      (link) => link.closest('aside') !== null
    )
    expect(sidebarRoot).toBeDefined()
    expect(screen.getByRole('treeitem', { selected: true })).toHaveTextContent('Derivatives')
  })

  test('breadcrumb last crumb is the page heading and the title row is not duplicated', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5')
    const nav = await screen.findByRole('navigation', { name: 'Breadcrumb' })
    const current = within(nav).getByText('Derivatives')
    expect(current.closest('h1')).not.toBeNull()
    expect(current.getAttribute('aria-current') ?? '').toBe('')
    expect(within(nav).getByText('Derivatives').closest('span')).toHaveAttribute(
      'aria-current',
      'page'
    )
    expect(within(nav).queryByRole('link', { name: 'Derivatives' })).not.toBeInTheDocument()
    expect(screen.getAllByRole('heading', { name: 'Derivatives' })).toHaveLength(1)
    expect(screen.getByRole('button', { name: /study here/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ask about this node/i })).toBeInTheDocument()
  })

  test('visiting a node records it in the profile recents store', async () => {
    primeDefaults()
    window.localStorage.removeItem('sa-recent-nodes.default')
    renderWorkspace('/courses/3/n/5')
    expect(await screen.findByRole('heading', { name: 'Derivatives' })).toBeInTheDocument()
    await waitFor(() => {
      const raw = window.localStorage.getItem('sa-recent-nodes.default')
      expect(raw).not.toBeNull()
      const entries = JSON.parse(raw!) as Array<{ courseId: string; nodeId: string }>
      expect(entries[0]).toMatchObject({ courseId: '3', nodeId: '5' })
    })
    window.localStorage.removeItem('sa-recent-nodes.default')
  })

  test('tree sidebar renders permanently and ignores the older closed flag', async () => {
    window.localStorage.setItem('sa-tree-sidebar-open', '0')
    primeDefaults()
    renderWorkspace('/courses/3')
    expect(await screen.findByRole('heading', { name: 'Calculus I' })).toBeInTheDocument()
    expect(screen.getByRole('tree')).toBeInTheDocument()
    expect(screen.queryByTitle(/toggle structure sidebar/i)).not.toBeInTheDocument()
    window.localStorage.removeItem('sa-tree-sidebar-open')
  })

  test('clicking a tab navigates with the tab search param', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5')
    await screen.findByRole('heading', { name: 'Derivatives' })
    fireEvent.click(screen.getByRole('tab', { name: 'Tutor' }))
    expect(navigateMock).toHaveBeenCalledWith({
      to: '/courses/$courseId/n/$nodeId',
      params: { courseId: '3', nodeId: '5' },
      search: { tab: 'tutor' },
    })
  })

  test('study here opens the study launcher', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5')
    fireEvent.click(await screen.findByRole('button', { name: /study here/i }))
    console.log('DIALOG?', document.querySelectorAll('[role="dialog"]').length, 'BODY_TAIL:', document.body.innerHTML.slice(-400))
    expect(await screen.findByText('Write a note')).toBeInTheDocument()
    expect(screen.getByText('Mindmap')).toBeInTheDocument()
    expect(screen.getByText('Quiz')).toBeInTheDocument()
  })

  test('opening the study launcher closes an open tab-action popover', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5')
    fireEvent.pointerDown(await screen.findByRole('button', { name: /cheat sheet/i }))
    expect(
      screen.getByRole('menuitem', { name: /generate cheat sheet/i })
    ).toBeInTheDocument()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /study here/i }))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('Write a note')).toBeInTheDocument()
    expect(
      screen.queryByRole('menuitem', { name: /generate cheat sheet/i })
    ).not.toBeInTheDocument()
  })

  test('missing node shows a message', async () => {
    primeDefaults()
    nodeWorkspace.mockRejectedValue(new Error('404'))
    renderWorkspace('/courses/3/n/5')
    expect(await screen.findByText('This node no longer exists.')).toBeInTheDocument()
  })

  test('old chapters route redirects to the node workspace', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/chapters/5')
    expect(await screen.findByRole('heading', { name: 'Derivatives' })).toBeInTheDocument()
  })

  test('header shows the settings popover with badge and description', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5')
    await screen.findByRole('heading', { name: 'Derivatives' })
    expect(screen.queryByText('Rates of change')).not.toBeInTheDocument()
    expect(screen.queryByRole('img', { name: /custom ai instructions/i })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /node settings/i }))
    const panel = screen.getByRole('dialog', { name: /node settings/i })
    expect(within(panel).getByRole('textbox', { name: /^title$/i })).toHaveValue('Derivatives')
    expect(within(panel).getByRole('textbox', { name: /description/i })).toHaveValue(
      'Rates of change'
    )

    fireEvent.change(within(panel).getByRole('textbox', { name: /ai instructions/i }), {
      target: { value: 'prefer numeric answers' },
    })
    fireEvent.click(within(panel).getByRole('button', { name: /save/i }))
    await waitFor(() => expect(updateNode).toHaveBeenCalledWith('5', { ai_hint: 'prefer numeric answers' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  test('root settings popover edits title and description through the course endpoint', async () => {
    primeDefaults()
    updateNode.mockClear()
    updateCourse.mockClear()
    renderWorkspace('/courses/3')
    await screen.findByRole('heading', { name: 'Calculus I' })

    fireEvent.click(screen.getByRole('button', { name: /node settings/i }))
    const panel = screen.getByRole('dialog', { name: /node settings/i })
    expect(within(panel).getByRole('textbox', { name: /^title$/i })).toHaveValue('Calculus I')

    fireEvent.change(within(panel).getByRole('textbox', { name: /^title$/i }), {
      target: { value: 'Calculus II' },
    })
    fireEvent.change(within(panel).getByRole('textbox', { name: /description/i }), {
      target: { value: 'A different description' },
    })
    fireEvent.click(within(panel).getByRole('button', { name: /save/i }))
    await waitFor(() =>
      expect(updateCourse).toHaveBeenCalledWith('3', {
        title: 'Calculus II',
        description: 'A different description',
      })
    )
    expect(updateNode).not.toHaveBeenCalled()
  })

  test('linked-source browse offers open-in-library at the crumb row (plan 76 C)', async () => {
    primeDefaults()
    nodeWorkspace.mockImplementation((id: string) =>
      Promise.resolve(
        id === '1'
          ? ROOT_WS
          : {
              ...NODE_WS,
              folders: [
                {
                  folder_id: '10',
                  name: 'Lectures',
                  source_id: '77',
                  member_count: 2,
                  rationale: null,
                  auto_assigned: false,
                },
              ],
            }
      )
    )
    listFolders.mockResolvedValue([
      {
        id: '10',
        name: 'Lectures',
        path: '/Lectures',
        course_id: '3',
        parent_id: null,
        source_id: '77',
        created_at: '2026-09-01T00:00:00Z',
      },
    ])
    renderWorkspace('/courses/3/n/5?tab=materials&folder=10')
    const button = await screen.findByRole('button', { name: /Open in library/i })
    fireEvent.click(button)
    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith(
        expect.objectContaining({
          to: '/library',
          search: expect.objectContaining({ course: '3', folder: '10', source: '77' }),
        })
      )
    )
  })

  test('settings tab appears at the course root only and deep-links to course details', async () => {
    primeDefaults()
    const root = renderWorkspace('/courses/3?tab=settings')
    expect(await screen.findByTestId('course-settings-tab')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Title' })).toHaveValue('Calculus I')
    expect(screen.getByRole('button', { name: /save/i })).toBeDisabled()
    root.unmount()

    renderWorkspace('/courses/3/n/5')
    expect(await screen.findByRole('heading', { name: 'Derivatives' })).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Settings' })).not.toBeInTheDocument()
    expect(screen.queryByTestId('course-settings-tab')).not.toBeInTheDocument()
  })

  test('settings tab saves the course title and description', async () => {
    primeDefaults()
    updateCourse.mockResolvedValue(undefined)
    renderWorkspace('/courses/3?tab=settings')
    await screen.findByTestId('course-settings-tab')
    fireEvent.change(screen.getByRole('textbox', { name: 'Title' }), {
      target: { value: 'Analysis I' },
    })
    fireEvent.change(screen.getByRole('textbox', { name: 'Description' }), {
      target: { value: 'Limits, derivatives, integrals' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))
    await waitFor(() =>
      expect(updateCourse).toHaveBeenCalledWith('3', {
        title: 'Analysis I',
        description: 'Limits, derivatives, integrals',
      })
    )
  })

})
