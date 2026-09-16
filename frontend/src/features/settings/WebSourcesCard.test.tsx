import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { WebSourcesCard } from './WebSourcesCard'

const listExternalSources = vi.fn()
const createExternalSource = vi.fn()
const updateExternalSource = vi.fn()
const deleteExternalSource = vi.fn()
const scanExternalSource = vi.fn()
const listCourses = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listExternalSources: (...args: Parameters<typeof actual.listExternalSources>) =>
      listExternalSources(...args),
    createExternalSource: (body: unknown) => createExternalSource(body),
    updateExternalSource: (id: number, body: unknown) =>
      updateExternalSource(id, body),
    deleteExternalSource: (id: number) => deleteExternalSource(id),
    scanExternalSource: (id: number) => scanExternalSource(id),
    listCourses: () => listCourses(),
  }
})

const COURSES = [
  { id: 7, title: 'Calculus I' },
  { id: 8, title: 'Algebra' },
]

const SOURCE = {
  id: 3,
  course_id: 7,
  kind: 'rss',
  url: 'https://math.example/feed',
  label: 'Math Feed',
  options: {},
  enabled: true,
  scan_interval_sec: null,
  last_scan_error: null,
  last_scanned_at: null,
}

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <WebSourcesCard />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  listExternalSources.mockReset().mockResolvedValue([SOURCE])
  createExternalSource.mockReset()
  updateExternalSource.mockReset().mockResolvedValue(SOURCE)
  deleteExternalSource.mockReset().mockResolvedValue(undefined)
  scanExternalSource.mockReset().mockResolvedValue({ new: 2, updated: 1 })
  listCourses.mockReset().mockResolvedValue(COURSES)
})

describe('WebSourcesCard', () => {
  test('lists sources with kind, course and error badge', async () => {
    listExternalSources.mockResolvedValue([
      SOURCE,
      {
        ...SOURCE,
        id: 4,
        kind: 'youtube_channel',
        label: 'Math channel',
        enabled: false,
        last_scan_error: 'extractor broken',
      },
    ])
    renderCard()
    expect(await screen.findByText('Math Feed')).toBeInTheDocument()
    expect(screen.getAllByText('Calculus I').length).toBeGreaterThan(0)
    expect(screen.getByText('Math channel')).toBeInTheDocument()
    expect(screen.getByText(/extractor broken/)).toBeInTheDocument()
    expect(screen.getByText('Off')).toBeInTheDocument()
  })

  test('adding an RSS source posts it for the chosen course', async () => {
    createExternalSource.mockResolvedValue(SOURCE)
    renderCard()
    fireEvent.click(await screen.findByRole('button', { name: /add source/i }))
    fireEvent.change(
      await screen.findByPlaceholderText('https://example.com/feed.xml'),
      { target: { value: 'https://new.example/rss' } },
    )
    fireEvent.change(screen.getByLabelText('Label'), {
      target: { value: 'New feed' },
    })
    fireEvent.change(screen.getByLabelText('Course'), {
      target: { value: '8' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))
    await waitFor(() =>
      expect(createExternalSource).toHaveBeenCalledWith(
        expect.objectContaining({
          course_id: 8,
          kind: 'rss',
          url: 'https://new.example/rss',
          label: 'New feed',
        }),
      ),
    )
  })

  test('site search sources require a query before saving', async () => {
    createExternalSource.mockResolvedValue(SOURCE)
    renderCard()
    fireEvent.click(await screen.findByRole('button', { name: /add source/i }))
    fireEvent.change(screen.getByLabelText('Kind'), {
      target: { value: 'site_search' },
    })
    expect(screen.getByLabelText('Search query')).toBeInTheDocument()
    const save = screen.getByRole('button', { name: /^save$/i })
    expect(save).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Search query'), {
      target: { value: 'calculus' },
    })
    expect(save).toBeEnabled()
    fireEvent.change(screen.getByLabelText('Site filter (domain)'), {
      target: { value: 'khanacademy.org' },
    })
    fireEvent.change(screen.getByLabelText('Course'), {
      target: { value: '8' },
    })
    fireEvent.click(save)
    await waitFor(() =>
      expect(createExternalSource).toHaveBeenCalledWith(
        expect.objectContaining({
          kind: 'site_search',
          options: { query: 'calculus', site: 'khanacademy.org' },
        }),
      ),
    )
  })

  test('scan now surfaces the new count and refreshes suggestions', async () => {
    renderCard()
    fireEvent.click(await screen.findByRole('button', { name: /scan now/i }))
    await waitFor(() => expect(scanExternalSource).toHaveBeenCalledWith(3))
    expect(
      await screen.findByText(/scan finished — 2 new/i),
    ).toBeInTheDocument()
  })

  test('toggle and delete update the list', async () => {
    renderCard()
    fireEvent.click(await screen.findByRole('checkbox', { name: /enabled/i }))
    await waitFor(() =>
      expect(updateExternalSource).toHaveBeenCalledWith(3, { enabled: false }),
    )
    fireEvent.click(screen.getByRole('button', { name: /delete/i }))
    await waitFor(() => expect(deleteExternalSource).toHaveBeenCalledWith(3))
  })
})
