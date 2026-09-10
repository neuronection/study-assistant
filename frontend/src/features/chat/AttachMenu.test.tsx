import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { AttachMenu, type PendingAttachment } from './AttachMenu'

const courseTree = vi.fn()
const listCourses = vi.fn()
const listMaterials = vi.fn()
const listNotes = vi.fn()
const listQuizzes = vi.fn()
const listExercises = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    courseTree: (...args: unknown[]) => courseTree(...(args as [number])),
    listCourses: () => listCourses(),
    listMaterials: (...args: unknown[]) => listMaterials(...(args as [])),
    listNotes: (...args: unknown[]) => listNotes(...(args as [])),
    listQuizzes: (...args: unknown[]) => listQuizzes(...(args as [])),
    listExercises: (...args: unknown[]) => listExercises(...(args as [])),
  }
})

function renderMenu(onSelect: (item: PendingAttachment) => void) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <AttachMenu courseId={3} attached={[]} onSelect={onSelect} />
    </QueryClientProvider>,
  )
}

describe('AttachMenu nodes tab', () => {
  test('lists course tree nodes flattened and selects them as node attachments', async () => {
    courseTree.mockResolvedValue([
      {
        id: 10,
        title: 'Chapter 1',
        summary: 'Rates of change',
        objectives: [],
        order_idx: 0,
        depth: 1,
        is_root: false,
        children: [
          {
            id: 11,
            title: 'Section 1.1',
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
    ])
    const onSelect = vi.fn()
    renderMenu(onSelect)

    fireEvent.click(screen.getByRole('tab', { name: 'Course nodes' }))
    expect((await screen.findAllByText('Chapter 1')).length).toBeGreaterThan(0)
    expect(screen.getByText('Rates of change')).toBeInTheDocument()
    expect(screen.getByText('Section 1.1')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Section 1.1'))
    await waitFor(() =>
      expect(onSelect).toHaveBeenCalledWith({
        kind: 'node',
        id: 11,
        title: 'Section 1.1',
      }),
    )
    expect(courseTree).toHaveBeenCalledWith(3)
  })

  test('shows an empty state when the course has no nodes', async () => {
    courseTree.mockResolvedValue([])
    renderMenu(vi.fn())

    fireEvent.click(screen.getByRole('tab', { name: 'Course nodes' }))
    expect(await screen.findByText('Nothing found.')).toBeInTheDocument()
  })
})
