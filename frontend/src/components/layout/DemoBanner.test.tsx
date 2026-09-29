import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getInstanceConfig } from '@/lib/api'

import { clearDemoModeCache, DemoBanner } from './DemoBanner'

vi.mock('@/lib/api', () => ({
  getInstanceConfig: vi.fn(),
}))

const mockedConfig = vi.mocked(getInstanceConfig)

describe('DemoBanner', () => {
  beforeEach(() => {
    mockedConfig.mockReset()
    clearDemoModeCache()
  })

  it('renders the badge on a demo instance', async () => {
    mockedConfig.mockResolvedValue({
      demo_mode: true,
      auth_mode: 'authenticated',
      registration_enabled: false,
    })
    render(<DemoBanner />)
    await waitFor(() =>
      expect(screen.getByText('Demo — synthetic data')).toBeInTheDocument(),
    )
  })

  it('renders nothing when demo_mode is off', async () => {
    mockedConfig.mockResolvedValue({
      demo_mode: false,
      auth_mode: 'authenticated',
      registration_enabled: true,
    })
    const { container } = render(<DemoBanner />)
    await waitFor(() => expect(mockedConfig).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when the config cannot be loaded', async () => {
    mockedConfig.mockRejectedValue(new Error('offline'))
    const { container } = render(<DemoBanner />)
    await waitFor(() => expect(mockedConfig).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })

  it('fetches the flag once per boot, even across remounts', async () => {
    mockedConfig.mockResolvedValue({
      demo_mode: true,
      auth_mode: 'authenticated',
      registration_enabled: false,
    })
    const first = render(<DemoBanner />)
    await waitFor(() =>
      expect(screen.getByText('Demo — synthetic data')).toBeInTheDocument(),
    )
    first.unmount()
    render(<DemoBanner />)
    await waitFor(() =>
      expect(screen.getByText('Demo — synthetic data')).toBeInTheDocument(),
    )
    expect(mockedConfig).toHaveBeenCalledTimes(1)
  })
})
