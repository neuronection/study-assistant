import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

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

const PENDING = {
  ...INFO,
  custom: true,
  restart_pending: true,
  path: '/home/u/.local/share/StudyAssistant',
}

function renderEditor() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <WorkingDirEditor />
    </QueryClientProvider>
  )
}

async function enterEdit() {
  fireEvent.click(await screen.findByRole('button', { name: 'Change folder…' }))
  return screen.findByDisplayValue(INFO.path)
}

describe('WorkingDirEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    delete window.pywebview
    getWorkingDir.mockResolvedValue(INFO)
    setWorkingDir.mockResolvedValue({ path: '/tmp/elsewhere', restart_required: true })
    resetWorkingDir.mockResolvedValue({ restart_required: true })
  })

  afterEach(() => {
    delete window.pywebview
  })

  test('shows the current path read-only with the default hint', async () => {
    renderEditor()
    const input = await screen.findByDisplayValue(INFO.path)
    expect(input).toHaveAttribute('readonly')
    expect(screen.getByText(/Default location:/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Change folder…' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Check' })).not.toBeInTheDocument()
  })

  test('enters edit explicitly and saves a validated path', async () => {
    getWorkingDir.mockResolvedValueOnce(INFO).mockResolvedValue(PENDING)
    validateWorkingDir.mockResolvedValue({
      valid: true,
      reason: null,
      exists: true,
      empty: true,
      has_app_db: false,
    })
    renderEditor()
    const input = await enterEdit()
    expect(input).not.toHaveAttribute('readonly')
    fireEvent.change(input, { target: { value: '/tmp/elsewhere' } })
    fireEvent.blur(input)
    expect(await screen.findByText('Empty folder — ready to use.')).toBeInTheDocument()

    const save = screen.getByRole('button', { name: 'Use after restart' })
    expect(save).not.toBeDisabled()
    fireEvent.click(save)
    await waitFor(() => expect(setWorkingDir).toHaveBeenCalledWith('/tmp/elsewhere'))
    expect(await screen.findByText(/data-location change is pending/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Undo' })).toBeInTheDocument()
  })

  test('uses the desktop data-directory picker when the bridge exposes it', async () => {
    const pickDataDir = vi.fn().mockResolvedValue('/tmp/elsewhere')
    window.pywebview = {
      api: { pick_folder: vi.fn(), pick_data_dir: pickDataDir },
    }
    validateWorkingDir.mockResolvedValue({
      valid: true,
      reason: null,
      exists: true,
      empty: true,
      has_app_db: false,
    })
    renderEditor()
    await enterEdit()
    fireEvent.click(screen.getByRole('button', { name: 'Browse…' }))
    await waitFor(() => expect(pickDataDir).toHaveBeenCalled())
    await waitFor(() => expect(validateWorkingDir).toHaveBeenCalledWith('/tmp/elsewhere'))
    expect(await screen.findByText('Empty folder — ready to use.')).toBeInTheDocument()
  })

  test('falls back to manual editing when no desktop bridge exists', async () => {
    renderEditor()
    const input = await enterEdit()
    expect(input).not.toHaveAttribute('readonly')
    expect(screen.queryByRole('button', { name: 'Browse…' })).not.toBeInTheDocument()
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
    const input = await enterEdit()
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
