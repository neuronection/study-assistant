import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { ActivityButton } from './ActivityPopover'

const mockGetSummary = vi.fn()
const mockListJobs = vi.fn()
const mockRetryOne = vi.fn()
const mockRetryAll = vi.fn()
const mockDeleteOne = vi.fn()
const mockDeleteAllFailed = vi.fn()

vi.mock('@/lib/api', () => ({
  getJobsSummary: () => mockGetSummary(),
  listJobs: (params?: unknown) => mockListJobs(params),
  retryJob: (jobId: number) => mockRetryOne(jobId),
  retryFailedJobs: (types?: string[]) => mockRetryAll(types),
  deleteJob: (jobId: number) => mockDeleteOne(jobId),
  deleteFailedJobs: (options?: unknown) => mockDeleteAllFailed(options),
}))

vi.mock('@tanstack/react-router', () => ({
  Link: ({
    children,
    to,
    params,
  }: {
    children: React.ReactNode
    to: string
    params?: Record<string, string>
  }) => {
    let href = to
    for (const [key, value] of Object.entries(params ?? {})) {
      href = href.replace(`$${key}`, value)
    }
    return (
      <a href={href} onClick={(event) => event.preventDefault()}>
        {children}
      </a>
    )
  },
  useSearch: () => ({}),
}))

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({ t: (key: string) => key }),
  }
})

const FAILED_JOB = {
  id: 11,
  type: 'ingest',
  status: 'failed' as const,
  progress: 30,
  stage: 'ocr',
  error: 'OCR provider unavailable',
  label: 'Lecture 3.pdf',
  material_id: 77,
  retriable: true,
  stale: false,
  created_at: new Date().toISOString(),
  started_at: null,
  finished_at: new Date().toISOString(),
}

function renderButton() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ActivityButton />
    </QueryClientProvider>
  )
}

describe('ActivityButton', () => {
  beforeEach(() => {
    mockGetSummary.mockReset()
    mockListJobs.mockReset()
    mockRetryOne.mockReset()
    mockRetryAll.mockReset()
    mockDeleteOne.mockReset()
    mockDeleteAllFailed.mockReset()
    mockGetSummary.mockResolvedValue({
      queued: 0,
      running: 0,
      failed: 1,
      done: 2,
      failed_retryable: 1,
      failed_stale: 0,
    })
    mockListJobs.mockResolvedValue([
      FAILED_JOB,
      {
        id: 12,
        type: 'ingest',
        status: 'running' as const,
        progress: 55,
        stage: 'parse',
        error: null,
        label: 'Notes.pdf',
        retriable: false,
        created_at: new Date().toISOString(),
        started_at: null,
        finished_at: null,
      },
      {
        id: 13,
        type: 'postprocess',
        status: 'done' as const,
        progress: 100,
        stage: 'indexing',
        error: null,
        label: 'Slides.pdf',
        retriable: false,
        created_at: new Date().toISOString(),
        started_at: null,
        finished_at: new Date().toISOString(),
      },
    ])
  })

  test('shows a failed-count badge on the trigger and opens the activity panel', async () => {
    renderButton()
    const badge = await screen.findByText('1')
    expect(badge).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'jobs.title' }))
    const dialog = await screen.findByRole('dialog')
    expect(await within(dialog).findByText('Lecture 3.pdf')).toBeInTheDocument()
    expect(within(dialog).getByText('OCR provider unavailable')).toBeInTheDocument()
    expect(await within(dialog).findByText('Notes.pdf')).toBeInTheDocument()
    expect(within(dialog).getAllByLabelText(/retry: /i)).toHaveLength(1)
  })

  test('retry button requeues the single failed job', async () => {
    mockRetryOne.mockResolvedValue({ ...FAILED_JOB, status: 'queued', error: null })
    renderButton()
    fireEvent.click(await screen.findByRole('button', { name: 'jobs.title' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(await within(dialog).findByLabelText(/retry: lecture 3\.pdf/i))
    await waitFor(() => expect(mockRetryOne).toHaveBeenCalledWith(11))
  })

  test('retry-all is offered when retryable failures exist', async () => {
    mockRetryAll.mockResolvedValue({ retried: 1 })
    renderButton()
    fireEvent.click(await screen.getByRole('button', { name: 'jobs.title' }))
    const dialog = await screen.findByRole('dialog')
    const retryAllButton = await within(dialog).findByText(/jobs\.retryAll/)
    fireEvent.click(retryAllButton)
    await waitFor(() => expect(mockRetryAll).toHaveBeenCalledWith(undefined))
  })

  test('failed jobs without a registered handler have no retry affordance', async () => {
    mockListJobs.mockResolvedValue([{ ...FAILED_JOB, retriable: false }])
    renderButton()
    fireEvent.click(await screen.findByRole('button', { name: 'jobs.title' }))
    const dialog = await screen.findByRole('dialog')
    await within(dialog).findByText('Lecture 3.pdf')
    expect(within(dialog).queryAllByLabelText(/retry: /i)).toHaveLength(0)
  })

  test('delete on a failed row removes the record after confirmation', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mockDeleteOne.mockResolvedValue(undefined)
    renderButton()
    fireEvent.click(await screen.findByRole('button', { name: 'jobs.title' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(await within(dialog).findByLabelText(/jobs\.deleteOne: lecture 3/i))
    await waitFor(() => expect(mockDeleteOne).toHaveBeenCalledWith(11))
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })
})
