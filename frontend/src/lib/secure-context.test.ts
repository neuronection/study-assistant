import { describe, expect, test } from 'vitest'

import { detectSecureContext } from './secure-context'

describe('detectSecureContext', () => {
  test('localhost is a secure context without HTTPS', () => {
    expect(
      detectSecureContext({
        hostname: 'localhost',
        serviceWorker: true,
        beforeInstallPrompt: true,
        mediaDevices: true,
        mediaRecorder: true,
        notifications: true,
      })
    ).toMatchObject({
      secure: true,
      install: true,
      mediaCapture: true,
      notifications: true,
    })
  })

  test('plain HTTP hides every secure capability', () => {
    expect(
      detectSecureContext({
        isSecureContext: false,
        hostname: '192.168.1.20',
        serviceWorker: true,
        beforeInstallPrompt: true,
        mediaDevices: true,
        mediaRecorder: true,
        notifications: true,
      })
    ).toMatchObject({
      secure: false,
      serviceWorker: false,
      install: false,
      shareTarget: false,
      mediaCapture: false,
      mediaRecorder: false,
      notifications: false,
    })
  })

  test('share target needs a secure, installed PWA', () => {
    const base = {
      isSecureContext: true,
      serviceWorker: true,
      beforeInstallPrompt: true,
      mediaDevices: true,
      mediaRecorder: true,
      notifications: true,
    }
    expect(detectSecureContext(base).shareTarget).toBe(false)
    expect(detectSecureContext({ ...base, standalone: true }).shareTarget).toBe(true)
  })

  test('desktop is reported separately', () => {
    expect(detectSecureContext({ desktop: true, isSecureContext: false })).toMatchObject({
      desktop: true,
      secure: false,
    })
  })
})
