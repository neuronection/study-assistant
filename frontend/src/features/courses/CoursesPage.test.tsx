import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from '@tanstack/react-router'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { CoursesPage } from './CoursesPage'

const listCourses = vi.fn()
const createCourse = vi.fn()
const deleteCourse = vi.fn()
const importCourseBundle = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listCourses: () => listCourses(),
    createCourse: (...args: unknown[]) => createCourse(...(args as [object])),
    deleteCourse: (...args: unknown[]) => deleteCourse(...(args as [number])),
    importCourseBundle: (...args: unknown[]) =>
      importCourseBundle(...(args as [File, boolean])),
  }
})

const rootRoute = createRootRoute()
const coursesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/courses',
  component: CoursesPage,
})
const detailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/courses/$courseId',
  component: () => null,
})
const router = createRouter({
  routeTree: rootRoute.addChildren([coursesRoute, detailRoute]),
  history: createMemoryHistory({ initialEntries: ['/courses'] }),
})

function renderCourses() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}

const COURSE = {
  id: 3,
  title: 'Calculus I',
  subject: 'mathematics',
  level: null,
  description: null,
  color: null,
  archived_at: null,
  material_count: 5,
}

describe('CoursesPage', () => {
  beforeEach(() => {
    listCourses.mockReset()
    createCourse.mockReset()
    deleteCourse.mockReset()
    importCourseBundle.mockReset()
  })

  test('lists courses with subject and material count', async () => {
    listCourses.mockResolvedValue([COURSE])
    renderCourses()
    expect(await screen.findByText('Calculus I')).toBeInTheDocument()
    expect(screen.getByText('mathematics · 5 materials')).toBeInTheDocument()
  })

  test('course cards show the course description when set', async () => {
    listCourses.mockResolvedValue([
      { ...COURSE, description: 'Limits, derivatives and integrals.' },
      { ...COURSE, id: 4, title: 'Linear Algebra', description: null },
    ])
    renderCourses()
    expect(await screen.findByText('Limits, derivatives and integrals.')).toBeInTheDocument()
    expect(screen.getByText('Linear Algebra')).toBeInTheDocument()
  })

  test('shows empty state', async () => {
    listCourses.mockResolvedValue([])
    renderCourses()
    expect(
      await screen.findByText('No courses yet — create one and add materials from the Library.')
    ).toBeInTheDocument()
  })

  test('search filters courses and shows a no-match note', async () => {
    listCourses.mockResolvedValue([
      COURSE,
      { ...COURSE, id: 4, title: 'Linear Algebra', subject: 'mathematics' },
    ])
    renderCourses()
    expect(await screen.findByText('Calculus I')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))
    const input = await screen.findByPlaceholderText('Search courses…')
    fireEvent.change(input, { target: { value: 'linear' } })
    expect(screen.getByText('Linear Algebra')).toBeInTheDocument()
    expect(screen.queryByText('Calculus I')).not.toBeInTheDocument()
    fireEvent.change(input, { target: { value: 'biology' } })
    expect(screen.queryByText('Linear Algebra')).not.toBeInTheDocument()
    expect(screen.getByText('No courses match')).toBeInTheDocument()
  })

  test('create form posts a new course', async () => {
    listCourses.mockResolvedValue([])
    createCourse.mockResolvedValue({ ...COURSE, id: 9, title: 'Linear Algebra' })
    renderCourses()
    screen.getByRole('button', { name: /new course/i }).click()
    const titleInput = await screen.findByPlaceholderText('Course title')
    expect(titleInput).toBeInTheDocument()
    expect(createCourse).not.toHaveBeenCalled()
  })

  test('course cards expose a bundle export link', async () => {
    listCourses.mockResolvedValue([COURSE])
    renderCourses()
    const link = await screen.findByTitle('Export course bundle')
    expect(link).toHaveAttribute('href', '/api/v1/courses/3/export')
  })

  test('import shows a dry-run preview before committing', async () => {
    listCourses.mockResolvedValue([COURSE])
    importCourseBundle.mockResolvedValue({
      dry_run: true,
      preview: {
        title: 'Calculus I',
        counts: { materials: 2, notes: 1, quizzes: 3, exercises: 4 },
        warnings: ['material ’X’ has no extraction'],
      },
    })
    renderCourses()
    expect(await screen.findByText('Calculus I')).toBeInTheDocument()

    const file = new File(['zip'], 'course.zip', { type: 'application/zip' })
    fireEvent.change(screen.getByLabelText('Import course'), { target: { files: [file] } })
    await waitFor(() => expect(importCourseBundle).toHaveBeenCalledWith(file, true))

    expect(await screen.findByText(/Import "Calculus I" as a new course\?/i)).toBeInTheDocument()
    expect(screen.getByText(/2 materials · 1 notes · 3 quizzes · 4 exercises/)).toBeInTheDocument()
    expect(screen.getByText(/has no extraction/i)).toBeInTheDocument()

    importCourseBundle.mockResolvedValue({
      dry_run: false,
      imported: { course_id: 7, title: 'Calculus I (imported)' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Import' }))
    await waitFor(() => expect(importCourseBundle).toHaveBeenCalledWith(file, false))
  })
})
