import { describe, expect, test, vi } from 'vitest'

import { registerPwa } from './pwa'

describe('registerPwa', () => {
  test('registers on a secure production web origin', () => {
    const register = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'serviceWorker', {
      configurable: true,
      value: { register },
    })
    const addEventListener = vi.spyOn(window, 'addEventListener')
    expect(
      registerPwa({ production: true, secure: true, serviceWorker: true, desktop: false })
    ).toBe(true)
    expect(addEventListener).toHaveBeenCalledWith('load', expect.any(Function))
    addEventListener.mockRestore()
  })

  test('never registers in dev, on plain HTTP, or in the desktop shell', () => {
    for (const env of [
      { production: false, secure: true, serviceWorker: true, desktop: false },
      { production: true, secure: false, serviceWorker: true, desktop: false },
      { production: true, secure: true, serviceWorker: false, desktop: false },
      { production: true, secure: true, serviceWorker: true, desktop: true },
    ]) {
      expect(registerPwa(env)).toBe(false)
    }
  })
})
