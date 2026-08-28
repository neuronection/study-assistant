import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { CourseSettingsTab } from './CourseSettingsTab'
import type { Course } from '@/lib/api'

const listModels = vi.fn()
const listCourseTasks = vi.fn()
const assignCourseTask = vi.fn()
const listCourseTaskDefaults = vi.fn()
const assignCourseTaskDefault = vi.fn()
const updateCourse = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listModels: () => listModels(),
    listCourseTasks: (courseId: number) => listCourseTasks(courseId),
    assignCourseTask: (...args: unknown[]) =>
      assignCourseTask(...(args as [number, string, number | null, number | null])),
    listCourseTaskDefaults: (courseId: number) => listCourseTaskDefaults(courseId),
    assignCourseTaskDefault: (...args: unknown[]) =>
      assignCourseTaskDefault(
        ...(args as [number, string, number | null, number | null])
      ),
    updateCourse: (...args: unknown[]) => updateCourse(...(args as [number, object])),
  }
})

const COURSE: Course = {
  id: 3,
  title: 'Calculus I',
  subject: null,
  level: null,
  description: 'Limits and derivatives',
  color: '#3366cc',
  archived_at: null,
  material_count: 1,
}

function renderTab(course: Course = COURSE) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <CourseSettingsTab courseId="3" course={course} />
    </QueryClientProvider>
  )
}

describe('CourseSettingsTab', () => {
  test('general subtab edits title and description and saves via updateCourse', async () => {
    updateCourse.mockResolvedValue(undefined)
    renderTab()

    const save = screen.getByRole('button', { name: /^save$/i })
    expect(save).toBeDisabled()

    fireEvent.change(screen.getByRole('textbox', { name: 'Title' }), {
      target: { value: 'Analysis I' },
    })
    expect(save).toBeEnabled()
    fireEvent.change(screen.getByRole('textbox', { name: 'Description' }), {
      target: { value: '' },
    })
    fireEvent.click(save)

    await waitFor(() =>
      expect(updateCourse).toHaveBeenCalledWith(3, {
        title: 'Analysis I',
        description: '',
      })
    )
  })

  test('switching to tasks lists per-task overrides with inherited labels', async () => {
    listModels.mockResolvedValue([
      { id: 1, label: 'local-mini', caps: ['text'], enabled: true, missing: false },
      { id: 2, label: 'vision-pro', caps: ['vision'], enabled: true, missing: false },
    ])
    listCourseTaskDefaults.mockResolvedValue([])
    listCourseTasks.mockResolvedValue([
      {
        task: 'chat',
        description: 'Tutor chat turns',
        requires: 'text',
        model_id: null,
        fallback_model_id: null,
        model_label: null,
        fallback_model_label: null,
        global_model_label: 'global-chat',
        global_fallback_model_label: 'global-fallback',
      },
      {
        task: 'ocr',
        description: 'Scanned page OCR',
        requires: 'vision',
        model_id: 2,
        fallback_model_id: null,
        model_label: 'vision-pro',
        fallback_model_label: null,
        global_model_label: null,
        global_fallback_model_label: null,
      },
    ])

    renderTab()
    fireEvent.click(screen.getByRole('tab', { name: 'Tasks' }))

    expect(await screen.findByText('chat')).toBeInTheDocument()
    expect(screen.getByText('Tutor chat turns')).toBeInTheDocument()
    expect(screen.getByText(/using global-chat/i)).toBeInTheDocument()
    expect(listCourseTasks).toHaveBeenCalledWith(3)

    const chatModel = screen.getByRole('combobox', { name: 'chat course model' })
    expect(within(chatModel).getAllByRole('option')[0]).toHaveTextContent(
      '— inherit default —'
    )
    const options = within(chatModel).getAllByRole('option')
    expect(options.map((entry) => entry.textContent)).toEqual([
      '— inherit default —',
      'local-mini',
    ])
    expect(chatModel).toHaveValue('')
  })

  test('picking a course override assigns it; picking the inherit option clears it', async () => {    listModels.mockResolvedValue([
      { id: 1, label: 'local-mini', caps: ['text'], enabled: true, missing: false },
    ])
    const row = {
      task: 'quizgen',
      description: 'Quiz generation',
      requires: 'text',
      model_id: 1 as number | null,
      fallback_model_id: null as number | null,
      model_label: 'local-mini' as string | null,
      fallback_model_label: null as string | null,
      global_model_label: null,
      global_fallback_model_label: null,
    }
    listCourseTaskDefaults.mockResolvedValue([])
    listCourseTasks.mockResolvedValue([row])
    assignCourseTask.mockImplementation(
      (_courseId: number, _task: string, modelId: number | null, fallbackModelId: number | null) => {
        row.model_id = modelId
        row.fallback_model_id = fallbackModelId
        row.model_label = modelId === null ? null : 'local-mini'
        return Promise.resolve({ ...row })
      }
    )

    renderTab()
    fireEvent.click(screen.getByRole('tab', { name: 'Tasks' }))
    const select = await screen.findByRole('combobox', { name: 'quizgen course model' })
    expect(select).toHaveValue('1')

    fireEvent.change(select, { target: { value: '1' } })
    await waitFor(() =>
      expect(assignCourseTask).toHaveBeenLastCalledWith(3, 'quizgen', 1, null)
    )

    const fallback = screen.getByRole('combobox', { name: 'quizgen course fallback model' })
    fireEvent.change(fallback, { target: { value: '1' } })
    await waitFor(() =>
      expect(assignCourseTask).toHaveBeenLastCalledWith(3, 'quizgen', 1, 1)
    )

    fireEvent.change(screen.getByRole('combobox', { name: 'quizgen course model' }), {
      target: { value: '' },
    })
    await waitFor(() =>
      expect(assignCourseTask).toHaveBeenLastCalledWith(3, 'quizgen', null, 1)
    )
  })
})

describe('CourseSettingsTab defaults card', () => {
  test('lists capability defaults, shows inherited global label and assigns a course default', async () => {
    listModels.mockResolvedValue([
      { id: 1, label: 'local-mini', caps: ['text'], enabled: true, missing: false },
      { id: 2, label: 'vision-pro', caps: ['vision'], enabled: true, missing: false },
    ])
    const textRow = {
      requires: 'text',
      model_id: null as number | null,
      fallback_model_id: null as number | null,
      model_label: null as string | null,
      fallback_model_label: null as string | null,
      global_model_label: 'cloud-default',
      global_fallback_model_label: null,
    }
    const visionRow = {
      requires: 'vision',
      model_id: null,
      fallback_model_id: null,
      model_label: null,
      fallback_model_label: null,
      global_model_label: null,
      global_fallback_model_label: null,
    }
    listCourseTaskDefaults.mockResolvedValue([textRow, visionRow])
    assignCourseTaskDefault.mockImplementation(
      (_courseId: number, requires: string, modelId: number | null) => {
        if (requires === 'text') {
          textRow.model_id = modelId
          textRow.model_label = modelId === null ? null : 'local-mini'
        }
        return Promise.resolve({ ...textRow })
      }
    )
    listCourseTasks.mockResolvedValue([])

    renderTab()
    fireEvent.click(screen.getByRole('tab', { name: 'Tasks' }))

    const textSelect = await screen.findByRole('combobox', {
      name: 'Default text model',
    })
    expect(textSelect).toHaveValue('')
    expect(await screen.findByText(/using cloud-default/i)).toBeInTheDocument()

    fireEvent.change(textSelect, { target: { value: '1' } })
    await waitFor(() =>
      expect(assignCourseTaskDefault).toHaveBeenCalledWith(3, 'text', 1, null)
    )
    await waitFor(() => expect(textSelect).toHaveValue('1'))
    expect(listCourseTaskDefaults).toHaveBeenCalledWith(3)

    expect(visionRow.global_model_label).toBeNull()
  })
})
