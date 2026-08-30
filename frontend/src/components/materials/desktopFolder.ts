import type { MaterialUploadController, UploadItem } from '@/components/materials/materialUpload'
import {
  ApiError,
  apiFetch,
  desktopFileUrl,
  listDesktopFolder,
  registerDesktopDrops,
  type DesktopFileEntry,
} from '@/lib/api'

interface PywebviewBridge {
  api: {
    pick_folder: () => Promise<string | null>
  }
}

declare global {
  interface Window {
    pywebview?: PywebviewBridge
  }
}

let picking = false

export function desktopFolderMode(): boolean {
  return window.pywebview !== undefined
}

export function parseFileUris(dataTransfer: DataTransfer): string[] {
  if (typeof dataTransfer.getData !== 'function') {
    return []
  }
  const uriList = dataTransfer.getData('text/uri-list')
  const paths = uriList
    ? uriList
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter((line) => line.startsWith('file://'))
        .map((line) => decodeFileUrl(line))
    : []
  if (paths.length > 0) {
    return paths
  }
  const html = dataTransfer.getData('text/html')
  if (!html) {
    return []
  }
  const matches = html.match(/file:\/\/[^\s<"]+/g) ?? []
  return matches.map((match) => decodeFileUrl(match))
}

function decodeFileUrl(url: string): string {
  const path = url.slice('file://'.length)
  try {
    return decodeURIComponent(path)
  } catch {
    return path
  }
}

export async function fetchDesktopDropItems(paths: string[]): Promise<UploadItem[]> {
  const listing = await registerDesktopDrops(paths)
  const items: UploadItem[] = []
  for (const entry of listing.files) {
    try {
      items.push(await fetchItem(entry))
    } catch {
      continue
    }
  }
  return items
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

async function fetchItem(entry: DesktopFileEntry): Promise<UploadItem> {
  const response = await apiFetch(desktopFileUrl(entry.path))
  if (!response.ok) {
    throw new ApiError(`request failed: ${response.status}`, response.status)
  }
  const blob = await response.blob()
  const name = entry.rel.split('/').pop() ?? entry.rel
  return {
    file: new File([blob], name, { type: blob.type, lastModified: entry.mtime * 1000 }),
    relativePath: entry.rel,
  }
}

export async function uploadDesktopFolder(upload: MaterialUploadController): Promise<void> {
  const bridge = window.pywebview
  if (bridge === undefined || picking || upload.uploading) {
    return
  }
  picking = true
  try {
    const folder = await bridge.api.pick_folder()
    if (folder === null || folder === '') {
      return
    }
    let listing
    try {
      listing = await listDesktopFolder(folder)
    } catch (error) {
      upload.reportError({ name: folder, message: errorMessage(error) })
      return
    }
    const items: UploadItem[] = []
    for (const entry of listing.files) {
      try {
        items.push(await fetchItem(entry))
      } catch (error) {
        upload.reportError({ name: entry.rel, message: errorMessage(error) })
      }
    }
    if (items.length > 0) {
      await upload.uploadFiles(items)
    }
  } finally {
    picking = false
  }
}

export function pickFolder(
  upload: MaterialUploadController,
  folderInput: { current: HTMLInputElement | null },
): () => void {
  return () => {
    if (desktopFolderMode()) {
      void uploadDesktopFolder(upload)
    } else {
      folderInput.current?.click()
    }
  }
}
