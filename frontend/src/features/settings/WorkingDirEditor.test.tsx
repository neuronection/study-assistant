import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { WorkingDirEditor } from './WorkingDirEditor'

const getWorkingDir = vi.fn()
const validateWorkingDir = vi.fn()
const setWorkingDir = vi.fn()
const resetWorkingDir = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getWorkingDir: () => getWorkingDir(),
    validateWorkingDir: (path: string) => validateWorkingDir(path),
    setWorkingDir: (path: string) => setWorkingDir(path),
    resetWorkingDir: () => resetWorkingDir(),
  }
})

const INFO = {
  path: '/home/u/.local/share/StudyAssistant',
  default_path: '/home/u/.local/share/StudyAssistant',
  custom: false,
  restart_pending: false,
}

const PENDING = { ...INFO, custom: true, restart_pending: true, path: '/home/u/.local/share/StudyAssistant' }

function renderEditor() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <WorkingDirEditor />
    </QueryClientProvider>
  )
}

describe('WorkingDirEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getWorkingDir.mockResolvedValue(INFO)
    setWorkingDir.mockResolvedValue({ path: '/tmp/elsewhere', restart_required: true })
    resetWorkingDir.mockResolvedValue({ restart_required: true })
  })

  test('shows the current path and the default hint', async () => {
    renderEditor()
    expect(await screen.findByDisplayValue(INFO.path)).toBeInTheDocument()
    expect(screen.getByText(/Default location:/)).toBeInTheDocument()
  })

  test('validates a changed path and saves it, showing the restart banner', async () => {
    getWorkingDir.mockResolvedValueOnce(INFO).mockResolvedValue(PENDING)
    validateWorkingDir.mockResolvedValue({
      valid: true,
      reason: null,
      exists: true,
      empty: true,
      has_app_db: false,
    })
    renderEditor()
    const input = await screen.findByDisplayValue(INFO.path)
    fireEvent.change(input, { target: { value: '/tmp/elsewhere' } })
    fireEvent.blur(input)
    expect(await screen.findByText('Empty folder — ready to use.')).toBeInTheDocument()

    const save = screen.getByRole('button', { name: 'Use after restart' })
    expect(save).not.toBeDisabled()
    fireEvent.click(save)
    await waitFor(() => expect(setWorkingDir).toHaveBeenCalledWith('/tmp/elsewhere'))
    expect(await screen.findByText(/read its data from/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Undo' })).toBeInTheDocument()
  })

  test('shows the reason for an invalid path and keeps save disabled', async () => {
    validateWorkingDir.mockResolvedValue({
      valid: false,
      reason: 'not_empty',
      exists: true,
      empty: false,
      has_app_db: false,
    })
    renderEditor()
    const input = await screen.findByDisplayValue(INFO.path)
    fireEvent.change(input, { target: { value: '/tmp/junk' } })
    fireEvent.blur(input)
    expect(
      await screen.findByText(/not empty and doesn't look like a Study Assistant data folder/)
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Use after restart' })).toBeDisabled()
  })

  test('offers restore-default when a custom location is set', async () => {
    getWorkingDir.mockResolvedValue(PENDING)
    renderEditor()
    const reset = await screen.findByRole('button', { name: 'Restore default' })
    fireEvent.click(reset)
    await waitFor(() => expect(resetWorkingDir).toHaveBeenCalled())
  })
})
