import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { JobsPage } from './JobsPage'

const mockListJobs = vi.fn()
const mockListTypes = vi.fn()
const mockRetryOne = vi.fn()
const mockRetryAll = vi.fn()
const mockDeleteOne = vi.fn()
const mockDeleteAllFailed = vi.fn()

vi.mock('@/lib/api', () => ({
  listJobs: (params?: unknown) => mockListJobs(params),
  listJobTypes: () => mockListTypes(),
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
    search,
  }: {
    children: React.ReactNode
    to: string
    params?: Record<string, string>
    search?: Record<string, unknown> | ((prev: Record<string, unknown>) => Record<string, unknown>)
  }) => {
    let href = to
    for (const [key, value] of Object.entries(params ?? {})) {
      href = href.replace(`$${key}`, value)
    }
    const resolved =
      typeof search === 'function'
        ? search({})
        : (search ?? {})
    const query = Object.entries(resolved)
      .filter(([, value]) => value !== undefined)
      .map(([key, value]) => `${key}=${String(value)}`)
      .join('&')
    if (query) {
      href += `?${query}`
    }
    return (
      <a href={href} onClick={(event) => event.preventDefault()}>
        {children}
      </a>
    )
  },
  useSearch: () => {
    const params = new URLSearchParams(window.location.search)
    const out: Record<string, string> = {}
    for (const [key, value] of params.entries()) {
      out[key] = value
    }
    return out
  },
  useNavigate: () => () => Promise.resolve({}),
}))

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return { ...actual, useTranslation: () => ({ t: (key: string) => key }) }
})

const FAILED = {
  id: 31,
  type: 'ingest',
  status: 'failed' as const,
  progress: 40,
  stage: 'ocr',
  error: 'OCR provider unavailable',
  label: 'Lecture 3.pdf',
  material_id: 77,
  retriable: true,
  stale: false,
  created_at: new Date().toISOString(),
  started_at: new Date().toISOString(),
  finished_at: new Date().toISOString(),
}

function renderPage(url = '/jobs') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  window.history.replaceState({}, '', url)
  return render(
    <QueryClientProvider client={client}>
      <JobsPage />
    </QueryClientProvider>
  )
}

describe('JobsPage', () => {
  beforeEach(() => {
    mockListJobs.mockReset()
    mockListTypes.mockReset()
    mockRetryOne.mockReset()
    mockRetryAll.mockReset()
    mockDeleteOne.mockReset()
    mockDeleteAllFailed.mockReset()
    mockListJobs.mockResolvedValue([FAILED])
    mockListTypes.mockResolvedValue([
      { type: 'ingest', label: 'ingest' },
      { type: 'postprocess', label: 'postprocess' },
    ])
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('lists failed jobs with type, status, times and a material link', async () => {
    renderPage()
    const dialog = await screen.findByRole('list')
    expect(await within(dialog).findByText('Lecture 3.pdf')).toBeInTheDocument()
    expect(within(dialog).getByText('ingest')).toBeInTheDocument()
    expect(within(dialog).getAllByText(/failed/).length).toBeGreaterThan(0)
    expect(within(dialog).getAllByText(/ocr/).length).toBeGreaterThan(0)
    const link = within(dialog).getByRole('link', { name: 'Lecture 3.pdf' })
    expect(link.getAttribute('href')).toContain('/library/77')
    expect(within(dialog).getAllByLabelText(/retry: /i)).toHaveLength(1)
  })

  test('retry on a row requeues that job', async () => {
    mockRetryOne.mockResolvedValue({ ...FAILED, status: 'queued', error: null })
    renderPage()
    fireEvent.click(await screen.findByLabelText(/retry: lecture 3\.pdf/i))
    await waitFor(() => expect(mockRetryOne).toHaveBeenCalledWith(31))
  })

  test('status tabs are routable links updating the status param', async () => {
    renderPage('/jobs?status=failed')
    await screen.findByRole('list')
    expect(mockListJobs).toHaveBeenCalledWith(expect.objectContaining({ status: 'failed' }))
    const doneTab = screen.getByRole('link', { name: /^jobs\.tab_done/ })
    expect(doneTab.getAttribute('href')).toContain('status=done')
  })

  test('type filter and sort render from the query params', async () => {
    renderPage('/jobs?type=ingest&sort=created&dir=asc')
    await screen.findByRole('list')
    const typeSelect = screen.getByLabelText('jobs.typeFilter') as HTMLSelectElement
    expect(typeSelect.value).toBe('ingest')
    const createdTab = screen.getByRole('tab', { name: 'jobs.sortCreated' })
    expect(createdTab.getAttribute('aria-selected')).toBe('true')
  })

  test('delete on a row removes the record after confirmation', async () => {
    mockDeleteOne.mockResolvedValue(undefined)
    renderPage()
    fireEvent.click(await screen.findByLabelText(/jobs\.deleteOne: lecture 3\.pdf/i))
    fireEvent.click(await screen.findByRole('button', { name: 'jobs.deleteOne' }))
    await waitFor(() => expect(mockDeleteOne).toHaveBeenCalledWith(31))
  })

  test('row delete does nothing when the confirmation is dismissed', async () => {
    renderPage()
    fireEvent.click(await screen.findByLabelText(/jobs\.deleteOne: lecture 3\.pdf/i))
    fireEvent.click(await screen.findByRole('button', { name: 'common.cancel' }))
    expect(mockDeleteOne).not.toHaveBeenCalled()
  })

  test('stale failed rows show source-removed and hide retry', async () => {
    mockListJobs.mockResolvedValue([{ ...FAILED, stale: true }])
    renderPage()
    await screen.findByRole('list')
    expect(screen.getByText('jobs.sourceRemoved')).toBeInTheDocument()
    expect(screen.queryByLabelText(/retry: /i)).toBeNull()
  })

  test('bulk delete passes the active type filter through the menu', async () => {
    mockDeleteAllFailed.mockResolvedValue({ deleted: 1 })
    renderPage('/jobs?type=ingest')
    await screen.findByText('Lecture 3.pdf')
    fireEvent.pointerDown(screen.getByRole('button', { name: 'jobs.deleteMenu' }))
    fireEvent.click(screen.getByRole('menuitem', { name: /jobs\.deleteAllFiltered/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'jobs.deleteAllFiltered' }))
    await waitFor(() =>
      expect(mockDeleteAllFailed).toHaveBeenCalledWith({ types: ['ingest'] })
    )
  })

  test('stale menu entry deletes only stale rows', async () => {
    mockDeleteAllFailed.mockResolvedValue({ deleted: 1 })
    mockListJobs.mockResolvedValue([
      FAILED,
      { ...FAILED, id: 32, stale: true, retriable: false },
    ])
    renderPage('/jobs?status=failed')
    await screen.findAllByText('Lecture 3.pdf')
    fireEvent.pointerDown(screen.getByRole('button', { name: 'jobs.deleteMenu' }))
    fireEvent.click(screen.getByRole('menuitem', { name: /jobs\.deleteStale/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'jobs.deleteStale' }))
    await waitFor(() =>
      expect(mockDeleteAllFailed).toHaveBeenCalledWith({ staleOnly: true })
    )
  })

  test('stale menu entry is disabled when nothing is stale', async () => {
    mockListJobs.mockResolvedValue([{ ...FAILED }])
    renderPage('/jobs?status=failed')
    await screen.findByText('Lecture 3.pdf')
    fireEvent.pointerDown(screen.getByRole('button', { name: 'jobs.deleteMenu' }))
    expect(screen.getByRole('menuitem', { name: /jobs\.deleteStale/ })).toHaveAttribute(
      'aria-disabled',
      'true'
    )
  })

  test('cancelled jobs render a muted chip, no retry, and a delete button', async () => {
    mockListJobs.mockResolvedValue([
      {
        ...FAILED,
        id: 44,
        status: 'cancelled',
        retriable: false,
        error: null,
        stage: null,
      },
    ])
    renderPage('/jobs?status=cancelled')
    const dialog = await screen.findByRole('list')
    await within(dialog).findByText('Lecture 3.pdf')
    expect(mockListJobs).toHaveBeenCalledWith(expect.objectContaining({ status: 'cancelled' }))
    expect(within(dialog).getAllByText('cancelled').length).toBeGreaterThan(0)
    expect(within(dialog).queryByLabelText(/retry: /i)).not.toBeInTheDocument()
    expect(within(dialog).getByLabelText(/jobs\.deleteOne: /i)).toBeInTheDocument()
  })
})
