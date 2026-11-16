export interface PwaEnv {
  production: boolean
  secure: boolean
  serviceWorker: boolean
  desktop: boolean
}

function readEnv(): PwaEnv {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') {
    return { production: false, secure: false, serviceWorker: false, desktop: false }
  }
  return {
    production: Boolean(import.meta.env.PROD),
    secure: window.isSecureContext,
    serviceWorker: 'serviceWorker' in navigator,
    desktop: 'pywebview' in window,
  }
}

export function registerPwa(env: PwaEnv = readEnv()): boolean {
  if (!env.production || !env.secure || !env.serviceWorker || env.desktop) {
    return false
  }
  window.addEventListener('load', () => {
    void navigator.serviceWorker.register('/sw.js').catch(() => undefined)
  })
  return true
}
