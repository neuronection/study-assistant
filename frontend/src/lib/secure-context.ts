export interface SecureContextEnv {
  isSecureContext?: boolean
  hostname?: string
  serviceWorker?: boolean
  beforeInstallPrompt?: boolean
  mediaDevices?: boolean
  mediaRecorder?: boolean
  notifications?: boolean
  standalone?: boolean
  desktop?: boolean
}

export interface SecureContextReport {
  secure: boolean
  desktop: boolean
  serviceWorker: boolean
  install: boolean
  shareTarget: boolean
  mediaCapture: boolean
  mediaRecorder: boolean
  notifications: boolean
}

const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]', '::1'])

function readEnv(): SecureContextEnv {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') {
    return {}
  }
  const standalone =
    typeof window.matchMedia === 'function'
      ? window.matchMedia('(display-mode: standalone)').matches
      : false
  return {
    isSecureContext: window.isSecureContext,
    hostname: window.location.hostname,
    serviceWorker: 'serviceWorker' in navigator,
    beforeInstallPrompt: 'onbeforeinstallprompt' in window,
    mediaDevices: typeof navigator.mediaDevices?.getUserMedia === 'function',
    mediaRecorder: typeof MediaRecorder !== 'undefined',
    notifications: 'Notification' in window,
    standalone,
    desktop: 'pywebview' in window,
  }
}

export function detectSecureContext(env: SecureContextEnv = readEnv()): SecureContextReport {
  const desktop = env.desktop === true
  const secure =
    env.isSecureContext === true ||
    (env.hostname !== undefined && LOOPBACK_HOSTS.has(env.hostname))
  const serviceWorker = secure && env.serviceWorker === true
  return {
    secure,
    desktop,
    serviceWorker,
    install: secure && env.beforeInstallPrompt === true,
    shareTarget: serviceWorker && env.standalone === true,
    mediaCapture: secure && env.mediaDevices === true,
    mediaRecorder: secure && env.mediaRecorder === true,
    notifications: secure && env.notifications === true,
  }
}
