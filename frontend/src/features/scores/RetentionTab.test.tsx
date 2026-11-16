import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { RetentionTab } from './RetentionTab'
import type { RetentionReport, WorkloadReport } from '@/lib/api'

const getRetention = vi.hoisted(() => vi.fn())
const getWorkload = vi.hoisted(() => vi.fn())

vi.mock('@/lib/api', () => ({
  getRetention,
  getWorkload,
}))

const RETENTION: RetentionReport = {
  target: 0.9,
  reviews: 40,
  correct: 34,
  retention: 0.85,
  lapses: 4,
  buckets: [
    { key: 'young', reviews: 20, correct: 16, retention: 0.8 },
    { key: 'mature', reviews: 20, correct: 18, retention: 0.9 },
  ],
}

const WORKLOAD: WorkloadReport = {
  days: [
    { day: '2026-11-11', due: 2 },
    { day: '2026-11-12', due: 8 },
  ],
  new_available: 5,
  total: 10,
  peak_day: '2026-11-12',
  peak_count: 8,
}

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <RetentionTab />
    </QueryClientProvider>,
  )
}

describe('RetentionTab', () => {
  beforeEach(() => {
    getRetention.mockReset()
    getWorkload.mockReset()
  })

  test('shows true retention, target and buckets', async () => {
    getRetention.mockResolvedValue(RETENTION)
    getWorkload.mockResolvedValue(WORKLOAD)
    renderTab()
    expect(await screen.findByText('85%')).toBeInTheDocument()
    expect(screen.getByText('90%')).toBeInTheDocument()
    expect(screen.getAllByText(/Young cards/).length).toBeGreaterThan(0)
    expect(screen.getByText(/10 reviews due in 30 days/)).toBeInTheDocument()
  })

  test('is honest when there are no reviews', async () => {
    getRetention.mockResolvedValue({ ...RETENTION, reviews: 0, retention: null })
    getWorkload.mockResolvedValue(WORKLOAD)
    renderTab()
    expect(await screen.findByText(/No reviews/)).toBeInTheDocument()
  })
})
