import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { SearchTab } from './SearchTab'

const getProfilePreferences = vi.fn()
const updateProfilePreferences = vi.fn()

vi.mock('@/lib/api', () => ({
  getProfilePreferences: () => getProfilePreferences(),
  updateProfilePreferences: (prefs: Record<string, unknown>) =>
    updateProfilePreferences(prefs),
}))

function renderTab() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <SearchTab />
    </QueryClientProvider>
  )
}

describe('SearchTab', () => {
  beforeEach(() => {
    getProfilePreferences.mockClear()
    updateProfilePreferences.mockClear()
  })

  test('shows the current OCR image max edge and saves changes', async () => {
    getProfilePreferences.mockResolvedValue({
      use_embeddings: true,
      ocr_image_max_edge: 1568,
    })
    updateProfilePreferences.mockImplementation(async (prefs) => ({
      use_embeddings: true,
      ocr_image_max_edge: 0,
      ...prefs,
    }))
    renderTab()

    const select = await screen.findByLabelText(/max long edge/i)
    await waitFor(() => expect(select).toHaveValue('1568'))

    fireEvent.change(select, { target: { value: '1024' } })
    await waitFor(() =>
      expect(updateProfilePreferences).toHaveBeenCalledWith({ ocr_image_max_edge: 1024 })
    )
  })

  test('offers the off preset', async () => {
    getProfilePreferences.mockResolvedValue({
      use_embeddings: true,
      ocr_image_max_edge: 0,
    })
    renderTab()

    const select = await screen.findByLabelText(/max long edge/i)
    await waitFor(() => expect(select).toHaveValue('0'))
    expect(
      screen.getByRole('option', { name: /off \(send as-is\)/i })
    ).toBeInTheDocument()
  })
})
