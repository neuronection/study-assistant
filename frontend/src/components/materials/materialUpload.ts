import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useState } from 'react'

import {
  createFolder,
  listFolders,
  uploadMaterial,
  type Folder,
  type UploadResult,
} from '@/lib/api'

export interface MaterialUploadError {
  name: string
  message: string
}

export interface UploadItem {
  file: File
  relativePath?: string
  label?: string
}

export interface MaterialUploadController {
  uploadFiles: (files: FileList | File[] | UploadItem[]) => Promise<UploadResult[]>
  uploading: boolean
  currentName: string | null
  errors: MaterialUploadError[]
  clearErrors: () => void
  reportError: (error: MaterialUploadError) => void
}

const JUNK_FILE_NAMES = new Set(['.DS_Store', 'Thumbs.db', 'desktop.ini'])

function isJunkFile(item: UploadItem): boolean {
  const name = item.file.name
  return JUNK_FILE_NAMES.has(name) || name.startsWith('._')
}

function toItems(files: FileList | File[] | UploadItem[]): UploadItem[] {
  return Array.from(files as ArrayLike<File | UploadItem>).map((entry) =>
    entry instanceof File
      ? {
          file: entry,
          relativePath:
            entry.webkitRelativePath && entry.webkitRelativePath !== ''
              ? entry.webkitRelativePath
              : undefined,
        }
      : entry
  )
}

function withName(item: File, name: string): File {
  if (name === item.name) {
    return item
  }
  return new File([item], name, { type: item.type, lastModified: item.lastModified })
}

type FolderCache = Map<number | null, Map<string, Folder>>

function indexFolders(folders: Folder[], cache: FolderCache): void {
  for (const folder of folders) {
    const siblings = cache.get(folder.parent_id) ?? new Map<string, Folder>()
    siblings.set(folder.name, folder)
    cache.set(folder.parent_id, siblings)
  }
}

async function ensureFolderPath(
  courseId: number,
  segments: string[],
  baseFolderId: number | null,
  cache: FolderCache,
  created: () => void,
  onTopLevelCreated: ((folder: Folder) => void | Promise<void>) | undefined
): Promise<number | null> {
  let parent = baseFolderId
  for (let i = 0; i < segments.length; i++) {
    const segment = segments[i]
    const existing = cache.get(parent)?.get(segment)
    if (existing !== undefined) {
      parent = existing.id
      continue
    }
    const folder = await createFolder(segment, parent, courseId)
    created()
    const siblings = cache.get(parent) ?? new Map<string, Folder>()
    siblings.set(segment, folder)
    cache.set(parent, siblings)
    parent = folder.id
    if (i === 0 && onTopLevelCreated !== undefined) {
      await onTopLevelCreated(folder)
    }
  }
  return parent
}

export function useMaterialUpload({
  courseId,
  getFolderId,
  nameFile,
  onUploaded,
  onFolderCreated,
}: {
  courseId: number | null
  getFolderId?: () => number | null | Promise<number | null>
  nameFile?: (item: UploadItem, folderId: number | null, courseId: number) => Promise<string> | string
  onUploaded?: (result: UploadResult, item: UploadItem) => void | Promise<void>
  onFolderCreated?: (folder: Folder) => void | Promise<void>
}): MaterialUploadController {
  const queryClient = useQueryClient()
  const [uploading, setUploading] = useState(false)
  const [currentName, setCurrentName] = useState<string | null>(null)
  const [errors, setErrors] = useState<MaterialUploadError[]>([])

  const uploadFiles = useCallback(
    async (files: FileList | File[] | UploadItem[]): Promise<UploadResult[]> => {
      if (courseId === null) {
        return []
      }
      const items = toItems(files).filter((item) => !isJunkFile(item))
      if (items.length === 0) {
        return []
      }
      setErrors([])
      setUploading(true)
      const baseFolderId = (await getFolderId?.()) ?? null
      const cache: FolderCache = new Map()
      indexFolders(await listFolders(courseId), cache)
      let foldersCreated = false
      const noteCreated = () => {
        foldersCreated = true
      }
      const createdTopLevel = new Set<number>()
      const topLevelCreated = (folder: Folder): void | Promise<void> => {
        if (createdTopLevel.has(folder.id)) {
          return undefined
        }
        createdTopLevel.add(folder.id)
        return onFolderCreated?.(folder)
      }
      const targetFolders = new Map<string, Promise<number | null>>()
      const folderTarget = (segments: string[]): Promise<number | null> => {
        const key = `${baseFolderId ?? 'root'}://${segments.join('/')}`
        let target = targetFolders.get(key)
        if (target === undefined) {
          target = ensureFolderPath(courseId, segments, baseFolderId, cache, noteCreated, topLevelCreated)
          targetFolders.set(key, target)
        }
        return target
      }
      const results: UploadResult[] = []
      for (const item of items) {
        setCurrentName(item.file.name)
        try {
          const segments = (item.relativePath ?? '')
            .split('/')
            .slice(0, -1)
            .filter((segment) => segment.length > 0)
          const folderId = segments.length > 0 ? await folderTarget(segments) : baseFolderId
          const named = (await nameFile?.(item, folderId, courseId)) ?? item.file.name
          const result = await uploadMaterial(withName(item.file, named), courseId, folderId)
          results.push(result)
          await queryClient.invalidateQueries({ queryKey: ['materials'] })
          await onUploaded?.(result, item)
        } catch (error) {
          setErrors((current) => [
            ...current,
            { name: item.file.name, message: error instanceof Error ? error.message : String(error) },
          ])
        }
      }
      if (foldersCreated) {
        await queryClient.invalidateQueries({ queryKey: ['folders'] })
      }
      setUploading(false)
      setCurrentName(null)
      return results
    },
    [courseId, getFolderId, nameFile, onUploaded, onFolderCreated, queryClient]
  )

  const clearErrors = useCallback(() => setErrors([]), [])

  const reportError = useCallback((error: MaterialUploadError) => {
    setErrors((current) => [...current, error])
  }, [])

  return { uploadFiles, uploading, currentName, errors, clearErrors, reportError }
}
