import type { UploadItem } from '@/components/materials/materialUpload'
import {
  desktopFolderMode,
  fetchDesktopDropItems,
  parseFileUris,
} from '@/components/materials/desktopFolder'

type Entry = {
  isFile: boolean
  isDirectory: boolean
  name: string
  file?: (success: (file: File) => void, error: (error: unknown) => void) => void
  createReader?: () => DirectoryReader
}

type DirectoryReader = {
  readEntries: (success: (entries: Entry[]) => void, error: (error: unknown) => void) => void
}

function readAllEntries(directory: { createReader?: () => DirectoryReader }): Promise<Entry[]> {
  if (directory.createReader === undefined) {
    return Promise.resolve([])
  }
  const reader = directory.createReader()
  const all: Entry[] = []
  const readBatch = (): Promise<Entry[]> =>
    new Promise((resolve, reject) => {
      reader.readEntries(resolve, reject)
    })
  return (async () => {
    for (;;) {
      const batch = await readBatch()
      if (batch.length === 0) {
        return all
      }
      all.push(...batch)
    }
  })().catch(() => all)
}

function entryFile(entry: Entry & { file?: Entry['file'] }): Promise<File | null> {
  return new Promise((resolve) => {
    if (entry.file === undefined) {
      resolve(null)
      return
    }
    entry.file(
      (file) => resolve(file),
      () => resolve(null)
    )
  })
}

async function collectEntry(entry: Entry, prefix: string, items: UploadItem[]): Promise<void> {
  if (entry.isFile) {
    const file = await entryFile(entry)
    if (file !== null) {
      items.push(prefix === '' ? { file } : { file, relativePath: `${prefix}${entry.name}` })
    }
    return
  }
  if (entry.isDirectory && entry.createReader !== undefined) {
    const children = await readAllEntries(entry)
    for (const child of children) {
      await collectEntry(child, `${prefix}${entry.name}/`, items)
    }
  }
}

export async function collectDropFiles(dataTransfer: DataTransfer): Promise<UploadItem[]> {
  const entries: Entry[] = []
  for (const item of Array.from(dataTransfer.items ?? [])) {
    const getter = (
      item as { webkitGetAsEntry?: () => Entry | null }
    ).webkitGetAsEntry
    if (typeof getter === 'function') {
      const entry = getter.call(item)
      if (entry !== null) {
        entries.push(entry)
      }
    }
  }
  if (entries.length === 0) {
    return Array.from(dataTransfer.files ?? []).map((file) => ({ file }))
  }
  const items: UploadItem[] = []
  for (const entry of entries) {
    await collectEntry(entry, '', items)
  }
  return items
}

export async function resolveDropItems(dataTransfer: DataTransfer): Promise<UploadItem[]> {
  const paths = parseFileUris(dataTransfer)
  const items = await collectDropFiles(dataTransfer)
  if (items.length > 0) {
    return items
  }
  if (paths.length === 0 || !desktopFolderMode()) {
    return []
  }
  return fetchDesktopDropItems(paths)
}
