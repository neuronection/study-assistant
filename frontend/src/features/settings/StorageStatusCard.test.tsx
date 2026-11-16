import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { StorageStatusCard } from './StorageStatusCard'

const mocks = vi.hoisted(() => ({
  getStorageStatus: vi.fn(),
  isAdmin: { value: true },
  desktop: { value: false },
}))

vi.mock('@/lib/api', () => ({
  getStorageStatus: (refresh?: boolean) => mocks.getStorageStatus(refresh),
}))

vi.mock('@/lib/auth-session', () => ({
  getCurrentUser: () => ({ is_admin: mocks.isAdmin.value }),
}))

vi.mock('@/lib/desktop-bridge', () => ({
  desktopBridge: () => (mocks.desktop.value ? {} : undefined),
}))

function status(overrides: Record<string, unknown> = {}) {
  return {
    backend: 's3',
    entrypoint: 'server',
    cloud_profile: 'aws',
    bucket: 'study-assistant-prod',
    container: null,
    region: 'eu-north-1',
    endpoint_host: 's3.eu-north-1.amazonaws.com',
    prefix: 'prod',
    sse: 'AES256',
    max_object_mb: 200,
    presign_ttl_seconds: 300,
    required: true,
    status: 'ok',
    healthy: true,
    detail: null,
    checked_at: '2026-11-15T12:00:00Z',
    ...overrides,
  }
}

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <StorageStatusCard />
    </QueryClientProvider>
  )
}

describe('StorageStatusCard', () => {
  beforeEach(() => {
    mocks.getStorageStatus.mockReset()
    mocks.isAdmin.value = true
    mocks.desktop.value = false
  })

  test('renders the resolved target as read-only facts', async () => {
    mocks.getStorageStatus.mockResolvedValue(status())
    renderCard()

    expect(await screen.findByText('study-assistant-prod')).toBeInTheDocument()
    expect(screen.getByText('Storage status')).toBeInTheDocument()
    expect(screen.getByText('prod')).toBeInTheDocument()
    expect(screen.getByText('eu-north-1 · s3.eu-north-1.amazonaws.com')).toBeInTheDocument()
    expect(screen.getByText('AES256')).toBeInTheDocument()
    expect(screen.getByText('200 MB')).toBeInTheDocument()
    expect(screen.getByText('300 s')).toBeInTheDocument()
    expect(screen.getByText('Healthy')).toBeInTheDocument()
    // No credential, endpoint path or presigned-URL fields exist in the card.
    expect(screen.queryByLabelText(/secret/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/X-Amz-/)).not.toBeInTheDocument()
    expect(screen.queryByText(/access key/i)).not.toBeInTheDocument()
  })

  test('the test button forces a fresh probe and renders the new health row', async () => {
    mocks.getStorageStatus
      .mockResolvedValueOnce(status())
      .mockResolvedValueOnce(
        status({
          status: 'unavailable',
          healthy: false,
          detail: 'StorageUnavailable',
          checked_at: '2026-11-15T12:00:30Z',
        })
      )
    renderCard()
    expect(await screen.findByText('Healthy')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Test connection' }))

    expect(await screen.findByText('Unavailable')).toBeInTheDocument()
    await waitFor(() => expect(mocks.getStorageStatus).toHaveBeenLastCalledWith(true))
  })

  test('shows an explicit loading state before the first snapshot', async () => {
    let resolve: (value: ReturnType<typeof status>) => void = () => {}
    mocks.getStorageStatus.mockReturnValue(
      new Promise<ReturnType<typeof status>>((done) => {
        resolve = done
      })
    )
    renderCard()
    expect(screen.getByRole('status')).toHaveTextContent(
      'Reading deployment storage status…'
    )
    resolve(status())
    expect(await screen.findByText('study-assistant-prod')).toBeInTheDocument()
  })

  test('a failed read shows an actionable error instead of stale facts', async () => {
    mocks.getStorageStatus.mockRejectedValue(new Error('storage status unavailable'))
    renderCard()
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'storage status unavailable'
    )
  })

  test('a failed test-connection mutation reports the probe error', async () => {
    mocks.getStorageStatus
      .mockResolvedValueOnce(status())
      .mockRejectedValueOnce(new Error('probe failed'))
    renderCard()
    expect(await screen.findByText('Healthy')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Test connection' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('probe failed')
    expect(mocks.getStorageStatus).toHaveBeenLastCalledWith(true)
  })

  test('renders nothing for non-admins or the desktop shell', async () => {
    mocks.isAdmin.value = false
    const plain = renderCard()
    expect(screen.queryByTestId('storage-status-card')).not.toBeInTheDocument()
    expect(mocks.getStorageStatus).not.toHaveBeenCalled()
    plain.unmount()

    mocks.isAdmin.value = true
    mocks.desktop.value = true
    renderCard()
    expect(screen.queryByTestId('storage-status-card')).not.toBeInTheDocument()
    expect(mocks.getStorageStatus).not.toHaveBeenCalled()
  })
})
