import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { DiscoveryCard } from './DiscoveryCard'

const getProfilePreferences = vi.fn()
const getSearchProvider = vi.fn()
const updateProfilePreferences = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getProfilePreferences: () => getProfilePreferences(),
    getSearchProvider: () => getSearchProvider(),
    updateProfilePreferences: (body: unknown) => updateProfilePreferences(body),
  }
})

const PREFS = {
  use_embeddings: true,
  ocr_image_max_edge: 1568,
  discovery: {
    enabled: ['web', 'youtube', 'site:khanacademy.org'],
    sites: [{ site: 'khanacademy.org', label: 'Khan Academy', kind: 'course' }],
  },
}

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <DiscoveryCard />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  getProfilePreferences.mockReset()
  getSearchProvider.mockReset()
  updateProfilePreferences.mockReset()
  getProfilePreferences.mockResolvedValue(PREFS)
  getSearchProvider.mockResolvedValue({ assigned: true, base_url: 'https://x', flavor: 'tavily', key_set: true })
})

describe('DiscoveryCard', () => {
  test('reflects stored provider toggles and the site preset', async () => {
    renderCard()
    const web = await screen.findByRole('checkbox', { name: /web search/i })
    await screen.findByDisplayValue('khanacademy.org')
    await waitFor(() => expect(web).toBeChecked())
    const youtube = screen.getByRole('checkbox', { name: /youtube search/i })
    expect(youtube).toBeChecked()
    expect(screen.getByDisplayValue('khanacademy.org')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Khan Academy')).toBeInTheDocument()
  })

  test('web toggle is honestly disabled without a search provider', async () => {
    getSearchProvider.mockResolvedValue({ assigned: false, base_url: null, flavor: null, key_set: false })
    renderCard()
    const web = await screen.findByRole('checkbox', { name: /web search/i })
    expect(web).toBeDisabled()
    expect(screen.getByText(/needs a search provider/i)).toBeInTheDocument()
    expect(screen.getByText(/site presets need a search provider/i)).toBeInTheDocument()
  })

  test('adding a site preset saves enabled ids and the sites list', async () => {
    updateProfilePreferences.mockResolvedValue({ ...PREFS })
    renderCard()
    await screen.findByDisplayValue('khanacademy.org')
    fireEvent.click(screen.getByRole('button', { name: /add site/i }))
    const domainInputs = screen.getAllByPlaceholderText('Domain')
    const domainInput = domainInputs[domainInputs.length - 1]
    fireEvent.change(domainInput, { target: { value: '3blue1brown.com' } })
    fireEvent.click(screen.getByRole('button', { name: /save discovery settings/i }))
    await waitFor(() => expect(updateProfilePreferences).toHaveBeenCalledTimes(1))
    const body = updateProfilePreferences.mock.calls[0][0] as {
      discovery: { enabled: string[]; sites: { site: string }[] }
    }
    expect(body.discovery.enabled).toEqual([
      'web',
      'youtube',
      'site:khanacademy.org',
      'site:3blue1brown.com',
    ])
    expect(body.discovery.sites).toEqual([
      { site: 'khanacademy.org', label: 'Khan Academy', kind: 'course' },
      { site: '3blue1brown.com', label: null, kind: 'course' },
    ])
  })

  test('disabling a provider drops it from the enabled list', async () => {
    updateProfilePreferences.mockResolvedValue({ ...PREFS })
    renderCard()
    await screen.findByDisplayValue('khanacademy.org')
    const youtube = screen.getByRole('checkbox', { name: /youtube search/i })
    fireEvent.click(youtube)
    fireEvent.click(screen.getByRole('button', { name: /save discovery settings/i }))
    await waitFor(() => expect(updateProfilePreferences).toHaveBeenCalledTimes(1))
    const body = updateProfilePreferences.mock.calls[0][0] as {
      discovery: { enabled: string[] }
    }
    expect(body.discovery.enabled).toEqual(['web', 'site:khanacademy.org'])
  })
})
