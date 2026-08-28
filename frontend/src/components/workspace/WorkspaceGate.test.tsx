import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { WorkspaceGate } from './WorkspaceGate'

const listCourses = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listCourses: () => listCourses(),
  }
})

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children }: { children: React.ReactNode }) => <a href="/courses">{children}</a>,
}))

function renderGate() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <WorkspaceGate>
        <p>page content</p>
      </WorkspaceGate>
    </QueryClientProvider>
  )
}

describe('WorkspaceGate', () => {
  beforeEach(() => {
    listCourses.mockReset()
  })

  test('shows the create-course gate when no courses exist', async () => {
    listCourses.mockResolvedValue([])
    renderGate()
    expect(await screen.findByText('No course yet')).toBeInTheDocument()
    expect(screen.queryByText('page content')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /go to courses/i })).toBeInTheDocument()
  })

  test('renders children once at least one course exists', async () => {
    listCourses.mockResolvedValue([
      {
        id: 1,
        title: 'Calculus',
        subject: null,
        level: null,
        description: null,
        color: null,
        archived_at: null,
        material_count: 0,
      },
    ])
    renderGate()
    await waitFor(() => expect(screen.getByText('page content')).toBeInTheDocument())
  })

  test('renders children while courses are loading or fail', () => {
    listCourses.mockReturnValue(new Promise(() => {}))
    renderGate()
    expect(screen.getByText('page content')).toBeInTheDocument()
  })

  test('renders children when the courses query fails', () => {
    listCourses.mockRejectedValue(new Error('offline'))
    renderGate()
    expect(screen.getByText('page content')).toBeInTheDocument()
  })
})
