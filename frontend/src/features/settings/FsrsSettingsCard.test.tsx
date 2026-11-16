import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { FsrsSettingsCard } from './FsrsSettingsCard'
import type { FsrsSettings } from '@/lib/api'

const getSettings = vi.hoisted(() => vi.fn())
const updateSettings = vi.hoisted(() => vi.fn())

vi.mock('@/lib/api', () => ({
  getFsrsSettings: getSettings,
  updateFsrsSettings: updateSettings,
}))

const SETTINGS: FsrsSettings = {
  desired_retention: 0.9,
  maximum_interval_days: 365,
  new_per_day: 20,
  reviews_per_day: 200,
  leech_threshold: 8,
  leech_action: 'tag',
  bury_siblings: false,
  load_balance: true,
  inherited: true,
}

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <FsrsSettingsCard />
    </QueryClientProvider>,
  )
}

describe('FsrsSettingsCard', () => {
  beforeEach(() => {
    getSettings.mockReset().mockResolvedValue(SETTINGS)
    updateSettings.mockReset().mockImplementation(async (body: Partial<FsrsSettings>) => ({
      ...SETTINGS,
      ...body,
    }))
  })

  test('loads the current pace and applies a preset', async () => {
    renderCard()
    expect(await screen.findByText('90%')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Intense' }))
    expect(screen.getByText('95%')).toBeInTheDocument()
  })

  test('saves the preset through the API', async () => {
    renderCard()
    await screen.findByText('90%')
    fireEvent.click(screen.getByRole('button', { name: 'Light' }))
    fireEvent.click(screen.getByRole('button', { name: /Save pace/ }))
    await waitFor(() =>
      expect(updateSettings).toHaveBeenCalledWith(
        expect.objectContaining({
          desired_retention: 0.85,
          new_per_day: 10,
          reviews_per_day: 100,
        })
      )
    )
    expect(await screen.findByRole('status')).toHaveTextContent('Saved')
  })
})
