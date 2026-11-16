import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { DailyBriefCard } from './DailyBriefCard'

const getProfilePreferences = vi.fn()
const updateProfilePreferences = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getProfilePreferences: () => getProfilePreferences(),
    updateProfilePreferences: (prefs: unknown) => updateProfilePreferences(prefs),
  }
})

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <DailyBriefCard />
    </QueryClientProvider>,
  )
}

describe('DailyBriefCard', () => {
  beforeEach(() => {
    getProfilePreferences.mockReset().mockResolvedValue({
      use_embeddings: true,
      ocr_image_max_edge: 1600,
      discovery: { enabled: [], sites: [] },
      daily_brief: { enabled: false, time: '07:00', length_minutes: 5, voice: null },
    })
    updateProfilePreferences.mockReset().mockResolvedValue({})
  })

  test('saves the daily brief schedule', async () => {
    renderCard()
    const toggle = await screen.findByRole('checkbox', { name: 'Enable daily brief' })
    await waitFor(() => expect(toggle).toHaveAttribute('aria-checked', 'false'))
    fireEvent.click(toggle)
    fireEvent.change(screen.getByDisplayValue('07:00'), { target: { value: '08:30' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save daily brief' }))
    await waitFor(() => expect(updateProfilePreferences).toHaveBeenCalled())
    expect(updateProfilePreferences).toHaveBeenCalledWith({
      daily_brief: { enabled: true, time: '08:30', length_minutes: 5 },
    })
  })
})
