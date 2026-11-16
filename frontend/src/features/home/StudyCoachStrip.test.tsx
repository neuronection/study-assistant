import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { StudyCoachStrip } from './StudyCoachStrip'

const navigate = vi.fn()
const getOverview = vi.fn()
const listCourses = vi.fn()
const listMaterials = vi.fn()
const getExamStatus = vi.fn()
const listQuizzes = vi.fn()
const listTasks = vi.fn()
const recordActivation = vi.fn()

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return { ...actual, useNavigate: () => navigate }
})

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getOverview: () => getOverview(),
    listCourses: () => listCourses(),
    listMaterials: () => listMaterials(),
    getExamStatus: () => getExamStatus(),
    listQuizzes: () => listQuizzes(),
    listTasks: () => listTasks(),
    recordActivation: (...args: unknown[]) => recordActivation(...args),
  }
})

function renderStrip() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <StudyCoachStrip />
    </QueryClientProvider>,
  )
}

describe('StudyCoachStrip', () => {
  beforeEach(() => {
    window.localStorage.clear()
    navigate.mockReset()
    getOverview.mockReset().mockResolvedValue({ due_cards: 0 })
    listCourses.mockReset().mockResolvedValue([{ id: 'course-1', title: 'Calculus' }])
    listMaterials.mockReset().mockResolvedValue([{ id: 'material-1' }])
    getExamStatus.mockReset().mockResolvedValue([])
    listQuizzes.mockReset().mockResolvedValue([{ id: 'quiz-1' }])
    listTasks.mockReset().mockResolvedValue([
      { task: 'chat', model_id: 'model-1', model_label: 'Model' },
    ])
    recordActivation.mockReset().mockResolvedValue(undefined)
  })

  test('asks for the first file when the library is empty', async () => {
    listMaterials.mockResolvedValue([])
    renderStrip()
    expect(await screen.findByText('Add your first study file')).toBeInTheDocument()
    expect(screen.queryByText('Connect an AI provider')).not.toBeInTheDocument()
  })

  test('shows at most two rules in priority order and dismisses one per rule', async () => {
    getOverview.mockResolvedValue({ due_cards: 6 })
    getExamStatus.mockResolvedValue([
      {
        course_id: 'course-1',
        course_title: 'Calculus',
        days_left: 9,
        exam_date: '2026-11-21',
        engaged_nodes: 2,
        total_nodes: 8,
        remaining_nodes: 6,
        nodes_per_day: 1,
        on_track: true,
        answers_in_scope: 0,
        readiness: 40,
        readiness_state: 'ok',
        most_behind_node: null,
      },
    ])
    renderStrip()
    expect(await screen.findByText('6 cards are due')).toBeInTheDocument()
    expect(screen.getByText('Calculus exam in 9 days')).toBeInTheDocument()
    expect(screen.queryByText('Connect an AI provider')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Dismiss “6 cards are due”' }))
    await waitFor(() =>
      expect(screen.queryByText('6 cards are due')).not.toBeInTheDocument(),
    )
    expect(screen.getByText('Calculus exam in 9 days')).toBeInTheDocument()
    expect(JSON.parse(window.localStorage.getItem('sa-coach-dismissed') ?? '[]')).toEqual([
      'review',
    ])
    expect(recordActivation).toHaveBeenCalledWith('tip_dismissed', {
      surface: 'home_coach',
      step: 'review',
    })
  })

  test('offers AI setup when no task has a model', async () => {
    listTasks.mockResolvedValue([
      { task: 'chat', model_id: null, model_label: null },
    ])
    renderStrip()
    expect(await screen.findByText('Connect an AI provider')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Open AI settings' }))
    expect(navigate).toHaveBeenCalledWith({
      to: '/settings',
      params: {},
      search: { tab: 'ai' },
    })
  })
})
