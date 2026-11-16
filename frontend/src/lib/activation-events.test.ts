import { beforeEach, describe, expect, test, vi } from 'vitest'

import { clearFirstEventKeys, clearPreScopeFirstEventKeys, recordFirstActivation } from './activation-events'
import { rememberSessionScope, resetSessionScopeForTests } from './session-scope'

const recordActivation = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    recordActivation: (...args: unknown[]) => recordActivation(...args),
  }
})

const SCOPE_A = 'u:user-1:p:profile-a'
const SCOPE_B = 'u:user-1:p:profile-b'

describe('recordFirstActivation', () => {
  beforeEach(() => {
    resetSessionScopeForTests()
    window.localStorage.clear()
    recordActivation.mockReset().mockResolvedValue(undefined)
  })

  test('records an event only once per scope', async () => {
    recordFirstActivation('first_review', { surface: 'review' })
    recordFirstActivation('first_review', { surface: 'review' })
    await vi.waitFor(() => expect(recordActivation).toHaveBeenCalledTimes(1))
    await vi.waitFor(() =>
      expect(window.localStorage.getItem('sa-first-event.local.first_review')).toBe('1'),
    )
    recordFirstActivation('first_review')
    expect(recordActivation).toHaveBeenCalledTimes(1)
  })

  test('two profiles record their own first event', async () => {
    rememberSessionScope(SCOPE_A)
    recordFirstActivation('first_review', { surface: 'review' })
    await vi.waitFor(() => expect(recordActivation).toHaveBeenCalledTimes(1))
    await vi.waitFor(() =>
      expect(
        window.localStorage.getItem(`sa-first-event.${SCOPE_A}.first_review`),
      ).toBe('1'),
    )

    rememberSessionScope(SCOPE_B)
    recordFirstActivation('first_review', { surface: 'review' })
    await vi.waitFor(() => expect(recordActivation).toHaveBeenCalledTimes(2))
    expect(
      window.localStorage.getItem(`sa-first-event.${SCOPE_B}.first_review`),
    ).toBe('1')
  })

  test('a failed first event can be retried', async () => {
    recordActivation.mockRejectedValueOnce(new Error('offline'))
    recordFirstActivation('first_capture')
    await vi.waitFor(() => expect(recordActivation).toHaveBeenCalledTimes(1))
    await new Promise((resolve) => setTimeout(resolve, 0))
    recordActivation.mockResolvedValue(undefined)
    recordFirstActivation('first_capture')
    await vi.waitFor(() => expect(recordActivation).toHaveBeenCalledTimes(2))
  })

  test('clearFirstEventKeys removes the captured scope and the shared local bucket', () => {
    window.localStorage.setItem(`sa-first-event.${SCOPE_A}.first_review`, '1')
    window.localStorage.setItem(`sa-first-event.${SCOPE_A}.first_quiz`, '1')
    window.localStorage.setItem(`sa-first-event.${SCOPE_B}.first_review`, '1')
    window.localStorage.setItem('sa-first-event.local.first_capture', '1')
    window.localStorage.setItem('sa-unrelated', 'keep')

    clearFirstEventKeys(SCOPE_A)

    expect(
      window.localStorage.getItem(`sa-first-event.${SCOPE_A}.first_review`),
    ).toBeNull()
    expect(
      window.localStorage.getItem(`sa-first-event.${SCOPE_A}.first_quiz`),
    ).toBeNull()
    expect(
      window.localStorage.getItem(`sa-first-event.${SCOPE_B}.first_review`),
    ).toBe('1')
    expect(
      window.localStorage.getItem('sa-first-event.local.first_capture'),
    ).toBeNull()
    expect(window.localStorage.getItem('sa-unrelated')).toBe('keep')
  })

  test('clearPreScopeFirstEventKeys clears only the shared local bucket', () => {
    window.localStorage.setItem('sa-first-event.local.first_capture', '1')
    window.localStorage.setItem(`sa-first-event.${SCOPE_A}.first_review`, '1')

    clearPreScopeFirstEventKeys()

    expect(
      window.localStorage.getItem('sa-first-event.local.first_capture'),
    ).toBeNull()
    expect(
      window.localStorage.getItem(`sa-first-event.${SCOPE_A}.first_review`),
    ).toBe('1')
  })
})
