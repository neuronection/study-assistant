import { describe, expect, test, vi } from 'vitest'

import {
  JournalNonRetryableError,
  MemoryJournalBackend,
  OfflineJournal,
  isCaptureOp,
} from './journal'

function file(name: string): File {
  return new File(['photo-bytes'], name, { type: 'image/jpeg' })
}

describe('OfflineJournal', () => {
  test('queues captures in order and drains them once', async () => {
    const backend = new MemoryJournalBackend()
    const journal = new OfflineJournal(backend)
    const first = await journal.enqueueCapture(file('one.jpg'), 'camera')
    const second = await journal.enqueueCapture(file('two.jpg'), 'camera')
    expect(journal.getSnapshot().ops.map((op) => op.id)).toEqual([first.id, second.id])

    const seen: string[] = []
    const completed = await journal.drain('capture', async (op, blob) => {
      if (!isCaptureOp(op) || blob === null) {
        throw new Error('expected a capture blob')
      }
      seen.push(`${op.payload.filename}:${await blob.text()}`)
    })
    expect(completed).toBe(2)
    expect(seen).toEqual(['one.jpg:photo-bytes', 'two.jpg:photo-bytes'])
    expect(journal.getSnapshot().ops).toEqual([])
  })

  test('keeps a retryable failure and marks a non-retryable one failed', async () => {
    const backend = new MemoryJournalBackend()
    const journal = new OfflineJournal(backend)
    const retryable = await journal.enqueueCapture(file('retry.jpg'), 'camera')
    const permanent = await journal.enqueueCapture(file('bad.jpg'), 'camera')

    await journal.drain('capture', async (op) => {
      if (op.id === retryable.id) {
        throw new Error('network down')
      }
      throw new JournalNonRetryableError('unsupported file')
    })
    const afterFailure = journal.getSnapshot().ops
    expect(afterFailure.find((op) => op.id === retryable.id)).toMatchObject({
      attempts: 1,
      failed: false,
      lastError: 'network down',
    })
    expect(afterFailure.find((op) => op.id === permanent.id)).toMatchObject({
      attempts: 1,
      failed: true,
      lastError: 'unsupported file',
    })

    const retried = await journal.drain('capture', async () => undefined)
    expect(retried).toBe(1)
    expect(journal.getSnapshot().ops.map((op) => op.id)).toEqual([permanent.id])
  })

  test('replays the same client op id after a restart', async () => {
    const backend = new MemoryJournalBackend()
    const first = new OfflineJournal(backend)
    const queued = await first.enqueueCapture(file('restart.jpg'), 'camera')

    const second = new OfflineJournal(backend)
    const seen: string[] = []
    await second.drain('capture', async (op) => {
      seen.push(op.id)
    })
    expect(seen).toEqual([queued.id])
    expect(second.getSnapshot().ops).toEqual([])
  })

  test('a lease stops two tabs draining the same queue', async () => {
    const backend = new MemoryJournalBackend()
    const left = new OfflineJournal(backend)
    const right = new OfflineJournal(backend)
    await left.enqueueCapture(file('locked.jpg'), 'camera')

    let release: () => void = () => undefined
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    let startedResolve: () => void = () => undefined
    const entered = new Promise<void>((resolve) => {
      startedResolve = resolve
    })
    const firstDrain = left.drain('capture', async () => {
      startedResolve()
      await gate
    })
    await entered
    const secondDrain = await right.drain('capture', async () => undefined)
    expect(secondDrain).toBe(0)
    release()
    await expect(firstDrain).resolves.toBe(1)
  })

  test('marks an op failed when its saved blob is missing', async () => {
    const backend = new MemoryJournalBackend()
    const journal = new OfflineJournal(backend)
    const queued = await journal.enqueueCapture(file('missing.jpg'), 'camera')
    await backend.deleteBlob(queued.id)
    await journal.drain('capture', async () => undefined)
    expect(journal.getSnapshot().ops[0]).toMatchObject({
      failed: true,
      lastError: 'The saved file is missing.',
    })
  })

  test('surfaces a quota failure instead of dropping the capture', async () => {
    class FullBackend extends MemoryJournalBackend {
      override async putBlob(): Promise<void> {
        throw new DOMException('no space', 'QuotaExceededError')
      }
    }
    const journal = new OfflineJournal(new FullBackend())
    await expect(journal.enqueueCapture(file('big.jpg'), 'camera')).rejects.toMatchObject({
      name: 'QuotaExceededError',
    })
  })

  test('remove drops the queued capture and its bytes', async () => {
    const backend = new MemoryJournalBackend()
    const journal = new OfflineJournal(backend)
    const queued = await journal.enqueueCapture(file('remove.jpg'), 'camera')
    await journal.remove(queued.id)
    expect(journal.getSnapshot().ops).toEqual([])
    expect(await backend.getBlob(queued.id)).toBeNull()
  })

  test('does not drain while offline', async () => {
    const backend = new MemoryJournalBackend()
    const journal = new OfflineJournal(backend)
    await journal.enqueueCapture(file('offline.jpg'), 'camera')
    const spy = vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
    const transport = vi.fn()
    expect(await journal.drain('capture', transport)).toBe(0)
    expect(transport).not.toHaveBeenCalled()
    spy.mockRestore()
  })
})
