import { describe, expect, test, vi } from 'vitest'

import { copyText } from './clipboard'

describe('copyText', () => {
  test('uses the async clipboard API when available', async () => {
    const writeText = vi.fn(async () => {})
    Object.assign(navigator, { clipboard: { writeText } })
    await expect(copyText('hello')).resolves.toBe(true)
    expect(writeText).toHaveBeenCalledWith('hello')
  })

  test('falls back to execCommand when the async API rejects', async () => {
    Object.assign(navigator, {
      clipboard: { writeText: vi.fn(async () => Promise.reject(new Error('denied'))) },
    })
    const execCommand = vi.fn(() => true)
    document.execCommand = execCommand as unknown as typeof document.execCommand
    await expect(copyText('fallback')).resolves.toBe(true)
    expect(execCommand).toHaveBeenCalledWith('copy')
  })

  test('falls back to execCommand when the async API is missing', async () => {
    Object.assign(navigator, { clipboard: undefined })
    const execCommand = vi.fn(() => true)
    document.execCommand = execCommand as unknown as typeof document.execCommand
    await expect(copyText('legacy')).resolves.toBe(true)
    expect(execCommand).toHaveBeenCalledWith('copy')
  })

  test('reports failure when every path fails', async () => {
    Object.assign(navigator, { clipboard: undefined })
    document.execCommand = () => {
      throw new Error('unsupported')
    }
    await expect(copyText('nope')).resolves.toBe(false)
  })
})
