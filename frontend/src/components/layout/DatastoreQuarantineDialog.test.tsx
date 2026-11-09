import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { clearDemoModeCache } from './DemoBanner'
import { DatastoreQuarantineDialog } from './DatastoreQuarantineDialog'

const getInstanceConfig = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return { ...actual, getInstanceConfig: () => getInstanceConfig() }
})

const NOTICE = {
  path: '/home/ada/.local/share/study/previous-datastore-20261109-120000',
  reason: 'incompatible-schema',
  quarantined_at: '2026-11-09T12:00:00+00:00',
  schema_revision: '0067_auth_session_created_at',
  from_version: null,
}

const CONFIG = {
  demo_mode: false,
  auth_mode: 'open',
  registration_enabled: false,
  identity_mode: 'desktop',
  datastore_quarantine: NOTICE,
}

describe('DatastoreQuarantineDialog', () => {
  beforeEach(() => {
    localStorage.clear()
    clearDemoModeCache()
    getInstanceConfig.mockResolvedValue(CONFIG)
  })

  test('shows the kept-data notice and dismisses locally', async () => {
    render(<DatastoreQuarantineDialog />)
    expect(await screen.findByText('Your previous data was kept')).toBeInTheDocument()
    expect(screen.getByText(NOTICE.path)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Got it' }))
    expect(screen.queryByText('Your previous data was kept')).not.toBeInTheDocument()
    expect(localStorage.getItem('sa.datastore-quarantine-seen')).toBe(NOTICE.quarantined_at)
  })

  test('stays hidden when this notice was dismissed before', async () => {
    localStorage.setItem('sa.datastore-quarantine-seen', NOTICE.quarantined_at)
    render(<DatastoreQuarantineDialog />)
    await waitFor(() => expect(getInstanceConfig).toHaveBeenCalled())
    expect(screen.queryByText('Your previous data was kept')).not.toBeInTheDocument()
  })

  test('renders nothing without a quarantine marker', async () => {
    getInstanceConfig.mockResolvedValue({ ...CONFIG, datastore_quarantine: null })
    render(<DatastoreQuarantineDialog />)
    await waitFor(() => expect(getInstanceConfig).toHaveBeenCalled())
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
