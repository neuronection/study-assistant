import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { DataTab } from './DataTab'

const getBackupStatus = vi.fn()
const updateBackupSettings = vi.fn()
const createBackupNow = vi.fn()
const deleteBackup = vi.fn()
const restoreBackupByName = vi.fn()
const getWorkingDir = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getBackupStatus: () => getBackupStatus(),
    updateBackupSettings: (body: unknown) => updateBackupSettings(body),
    createBackupNow: () => createBackupNow(),
    deleteBackup: (name: string) => deleteBackup(name),
    restoreBackupByName: (name: string) => restoreBackupByName(name),
    getWorkingDir: () => getWorkingDir(),
  }
})

const STATUS = {
  settings: {
    auto: true,
    interval_hours: 24,
    keep_daily: 14,
    keep_weekly: 8,
    sync_dir: null,
  },
  backups: [
    { name: 'auto-20260821-120000.zip', size: 2048, created_at: '2026-08-21T12:00:00' },
  ],
  last_recovery: null,
}

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <DataTab />
    </QueryClientProvider>
  )
}

describe('DataTab automatic backups', () => {
  beforeEach(() => {
    getBackupStatus.mockReset()
    updateBackupSettings.mockReset()
    createBackupNow.mockReset()
    deleteBackup.mockReset()
    restoreBackupByName.mockReset()
    getWorkingDir.mockReset()
    getBackupStatus.mockResolvedValue(STATUS)
    getWorkingDir.mockResolvedValue({
      path: '/data',
      default_path: '/data',
      custom: false,
      restart_pending: false,
    })
  })

  test('renders status, settings fields and the backup list', async () => {
    renderTab()
    expect(await screen.findByText('auto-20260821-120000.zip')).toBeInTheDocument()
    expect(screen.getByLabelText(/interval \(hours\)/i)).toHaveValue(24)
    expect(screen.getByRole('button', { name: /back up now/i })).toBeInTheDocument()
  })

  test('toggling automatic backups saves immediately', async () => {
    renderTab()
    const toggle = await screen.findByRole('checkbox', { name: /back up automatically/i })
    updateBackupSettings.mockResolvedValue({
      settings: { ...STATUS.settings, auto: false },
    })
    fireEvent.click(toggle)
    await waitFor(() => expect(updateBackupSettings).toHaveBeenCalledWith({ auto: false }))
  })

  test('editing retention fields enables Save settings', async () => {
    renderTab()
    await screen.findByText('auto-20260821-120000.zip')
    const daily = screen.getByLabelText(/keep daily/i)
    fireEvent.change(daily, { target: { value: '5' } })
    const save = screen.getByRole('button', { name: /save settings/i })
    expect(save).not.toBeDisabled()
    updateBackupSettings.mockResolvedValue({ settings: STATUS.settings })
    fireEvent.click(save)
    await waitFor(() =>
      expect(updateBackupSettings).toHaveBeenCalledWith(
        expect.objectContaining({ keep_daily: 5, sync_dir: null })
      )
    )
  })

  test('Back up now creates a backup and refreshes the list', async () => {
    createBackupNow.mockResolvedValue({ ...STATUS, backups: STATUS.backups })
    renderTab()
    fireEvent.click(await screen.findByRole('button', { name: /back up now/i }))
    await waitFor(() => expect(createBackupNow).toHaveBeenCalled())
  })

  test('restore from the list asks for confirmation and calls the endpoint', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    restoreBackupByName.mockResolvedValue({ status: 'restored', materials: 3 })
    renderTab()
    fireEvent.click(await screen.findByRole('button', { name: 'Restore' }))
    await waitFor(() =>
      expect(restoreBackupByName).toHaveBeenCalledWith('auto-20260821-120000.zip')
    )
    confirmSpy.mockRestore()
  })

  test('delete removes the backup row', async () => {
    deleteBackup.mockResolvedValue({ ...STATUS, backups: [] })
    renderTab()
    fireEvent.click(await screen.findByRole('button', { name: 'Delete backup' }))
    await waitFor(() =>
      expect(deleteBackup).toHaveBeenCalledWith('auto-20260821-120000.zip')
    )
  })
})
