interface PywebviewBridge {
  api: {
    pick_folder: () => Promise<string | null>
    pick_data_dir?: () => Promise<string | null>
  }
}

declare global {
  interface Window {
    pywebview?: PywebviewBridge
  }
}

let pickingFolder = false
let pickingDataDir = false

export function desktopBridge(): PywebviewBridge | undefined {
  return window.pywebview
}

export function desktopFolderMode(): boolean {
  return desktopBridge() !== undefined
}

export function hasDataDirPicker(): boolean {
  return typeof desktopBridge()?.api.pick_data_dir === 'function'
}

export async function pickFolder(): Promise<string | null> {
  const bridge = desktopBridge()
  if (bridge === undefined || pickingFolder) {
    return null
  }
  pickingFolder = true
  try {
    return await bridge.api.pick_folder()
  } finally {
    pickingFolder = false
  }
}

export async function pickDataDir(): Promise<string | null> {
  const bridge = desktopBridge()
  if (bridge === undefined || typeof bridge.api.pick_data_dir !== 'function' || pickingDataDir) {
    return null
  }
  pickingDataDir = true
  try {
    return await bridge.api.pick_data_dir()
  } finally {
    pickingDataDir = false
  }
}
