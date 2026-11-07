import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { UpdateBadge, clearUpdateCheckCache } from './UpdateBadge'

const getUpdateCheck = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getUpdateCheck: () => getUpdateCheck(),
  }
})

const UPDATE = {
  current_version: '0.12.1',
  latest_version: 'v0.13.0',
  update_available: true,
  release_url: 'https://github.com/neuronection/study-assistant/releases/tag/v0.13.0',
  checked_at: '2026-10-22T00:00:00Z',
  error: null,
}

function renderBadge() {
  return render(<UpdateBadge version="0.12.1" label="v0.12.1" />)
}

describe('UpdateBadge (plan 48 W6 — family version API)', () => {
  beforeEach(() => {
    getUpdateCheck.mockReset()
    getUpdateCheck.mockResolvedValue(UPDATE)
    clearUpdateCheckCache()
  })

  test('shows the dot and opens the popover with the release links', async () => {
    renderBadge()
    const button = await screen.findByRole('button')
    expect(button.getAttribute('title')).toContain('0.13.0')
    fireEvent.click(button)
    const dialog = await screen.findByRole('dialog')
    expect(dialog.textContent).toContain('v0.13.0')
    const links = Array.from(dialog.querySelectorAll('a')).map((a) => a.getAttribute('href'))
    expect(links).toContain(UPDATE.release_url)
    expect(links.some((href) => href?.endsWith('/releases'))).toBe(true)
  })

  test('closes the popover on Escape', async () => {
    renderBadge()
    fireEvent.click(await screen.findByRole('button'))
    await screen.findByRole('dialog')
    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  test('no dot when the instance is current', async () => {
    getUpdateCheck.mockResolvedValue({
      ...UPDATE,
      latest_version: 'v0.12.1',
      update_available: false,
    })
    renderBadge()
    await waitFor(() => expect(getUpdateCheck).toHaveBeenCalled())
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(document.querySelector('.rounded-full')).toBeNull()
  })

  test('a failed check reads as no update (fail-closed)', async () => {
    getUpdateCheck.mockRejectedValue(new Error('offline'))
    renderBadge()
    await waitFor(() => expect(getUpdateCheck).toHaveBeenCalled())
    expect(screen.queryByRole('dialog')).toBeNull()
  })
})
