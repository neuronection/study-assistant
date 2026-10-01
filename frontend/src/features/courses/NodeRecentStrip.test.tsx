import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { NodeRecentStrip } from './NodeRecentStrip'
import { useInterfacePrefsStore } from '@/lib/interface-prefs'
import type { NodeInfo } from '@/lib/api'

const navigate = vi.fn()

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigate,
}))

const ALL_ON = {
  homeContinue: true,
  paletteRecent: true,
  courseJumpBackIn: true,
  courseCardMeta: true,
}

const TREE: NodeInfo[] = [
  {
    id: 1,
    title: 'Calculus I',
    summary: null,
    objectives: [],
    order_idx: 0,
    depth: 0,
    is_root: true,
    children: [
      {
        id: 2,
        title: 'Limits',
        summary: null,
        objectives: [],
        order_idx: 0,
        depth: 1,
        is_root: false,
        children: [
          {
            id: 3,
            title: 'Continuity',
            summary: null,
            objectives: [],
            order_idx: 0,
            depth: 2,
            is_root: false,
            children: [],
            materials: [],
          },
        ],
        materials: [],
      },
    ],
    materials: [],
  },
]

function renderStrip(tree: NodeInfo[] | undefined) {
  return render(<NodeRecentStrip courseId="9" tree={tree} />)
}

describe('NodeRecentStrip', () => {
  beforeEach(() => {
    navigate.mockClear()
    window.localStorage.removeItem('sa-recent-nodes.default')
    useInterfacePrefsStore.setState({ prefs: { ...ALL_ON } })
  })

  test('hides when the course-jump-back-in interface pref is off', () => {
    useInterfacePrefsStore.setState({
      prefs: { ...ALL_ON, courseJumpBackIn: false },
    })
    window.localStorage.setItem(
      'sa-recent-nodes.default',
      JSON.stringify([{ courseId: 9, nodeId: 3, at: Date.now() - 60000 }])
    )
    const { container } = renderStrip(TREE)
    expect(container).toBeEmptyDOMElement()
  })

  test('shows rows for this course’s recent nodes with breadcrumbs', () => {
    window.localStorage.setItem(
      'sa-recent-nodes.default',
      JSON.stringify([
        { courseId: 9, nodeId: 3, at: Date.now() - 60000 },
        { courseId: 9, nodeId: 2, at: Date.now() - 3600000 },
      ])
    )
    renderStrip(TREE)
    const continuity = screen.getByText('Continuity')
    expect(continuity.closest('button')).toHaveAttribute(
      'title',
      'Calculus I › Limits'
    )
    expect(screen.getByText('Limits')).toBeInTheDocument()
    expect(screen.getByText('Jump back in')).toBeInTheDocument()
  })

  test('never offers the course root itself as a jump target', () => {
    window.localStorage.setItem(
      'sa-recent-nodes.default',
      JSON.stringify([
        { courseId: 9, nodeId: 1, at: Date.now() - 30000 },
        { courseId: 9, nodeId: 2, at: Date.now() - 3600000 },
      ])
    )
    renderStrip(TREE)
    expect(screen.queryByText('Calculus I')).not.toBeInTheDocument()
    expect(screen.getByText('Limits')).toBeInTheDocument()
  })

  test('clicking a pill navigates to the node workspace', () => {
    window.localStorage.setItem(
      'sa-recent-nodes.default',
      JSON.stringify([{ courseId: 9, nodeId: 3, at: Date.now() - 60000 }])
    )
    renderStrip(TREE)
    fireEvent.click(screen.getByText('Continuity'))
    expect(navigate).toHaveBeenCalledWith({
      to: '/courses/$courseId/n/$nodeId',
      params: { courseId: '9', nodeId: '3' },
    })
  })

  test('ignores entries from other courses', () => {
    window.localStorage.setItem(
      'sa-recent-nodes.default',
      JSON.stringify([{ courseId: 4, nodeId: 3, at: Date.now() - 60000 }])
    )
    const { container } = renderStrip(TREE)
    expect(container).toBeEmptyDOMElement()
  })

  test('stays hidden while the tree is loading', () => {
    window.localStorage.setItem(
      'sa-recent-nodes.default',
      JSON.stringify([{ courseId: 9, nodeId: 3, at: Date.now() - 60000 }])
    )
    const { container } = renderStrip(undefined)
    expect(container).toBeEmptyDOMElement()
  })

  test('drops entries whose node no longer exists', () => {
    window.localStorage.setItem(
      'sa-recent-nodes.default',
      JSON.stringify([{ courseId: 9, nodeId: 999, at: Date.now() - 60000 }])
    )
    const { container } = renderStrip(TREE)
    expect(container).toBeEmptyDOMElement()
  })
})
