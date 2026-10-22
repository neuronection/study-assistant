import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { UpdateBanner } from './UpdateBanner'
import { storageKeys } from '@/lib/constants'

const getUpdateCheck = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getUpdateCheck: () => getUpdateCheck(),
  }
})

function renderBanner() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <UpdateBanner />
    </QueryClientProvider>
  )
}

const UPDATE = {
  current_version: '0.12.1',
  latest_version: 'v0.13.0',
  update_available: true,
  release_url: 'https://github.com/neuronection/study-assistant/releases/tag/v0.13.0',
  checked_at: '2026-10-22T00:00:00Z',
  error: null,
}

describe('UpdateBanner (plan 87 F)', () => {
  beforeEach(() => {
    getUpdateCheck.mockReset()
    getUpdateCheck.mockResolvedValue(UPDATE)
    window.localStorage.removeItem(storageKeys.updateDismissed)
  })

  test('shows the newer release and links to the release page', async () => {
    renderBanner()
    expect(await screen.findByText(/0.13.0 is available/)).toBeInTheDocument()
    expect(screen.getByText('Download').closest('a')?.getAttribute('href')).toBe(
      UPDATE.release_url
    )
  })

  test('dismissing remembers the version', async () => {
    renderBanner()
    await screen.findByText(/0.13.0 is available/)
    fireEvent.click(screen.getByLabelText('Dismiss update notice'))
    await waitFor(() =>
      expect(window.localStorage.getItem(storageKeys.updateDismissed)).toBe('v0.13.0')
    )
    expect(screen.queryByText(/0.13.0 is available/)).not.toBeInTheDocument()
  })

  test('no banner when the instance is current', async () => {
    getUpdateCheck.mockResolvedValue({
      ...UPDATE,
      latest_version: 'v0.12.1',
      update_available: false,
    })
    renderBanner()
    await waitFor(() => expect(getUpdateCheck).toHaveBeenCalled())
    expect(screen.queryByText(/is available/)).not.toBeInTheDocument()
  })

  test('a previously dismissed version stays hidden', async () => {
    window.localStorage.setItem(storageKeys.updateDismissed, 'v0.13.0')
    renderBanner()
    await waitFor(() => expect(getUpdateCheck).toHaveBeenCalled())
    expect(screen.queryByText(/0.13.0 is available/)).not.toBeInTheDocument()
  })
})
