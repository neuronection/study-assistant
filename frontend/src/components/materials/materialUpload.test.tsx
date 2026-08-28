import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { UploadDropzone } from './UploadDropzone'
import { collectDropFiles } from './dropFiles'
import { useMaterialUpload, type MaterialUploadController } from './materialUpload'
import type { Folder, UploadResult } from '@/lib/api'

const uploadMaterial = vi.fn()
const listFolders = vi.fn()
const createFolder = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    uploadMaterial: (...args: unknown[]) => uploadMaterial(...(args as [])),
    listFolders: (...args: unknown[]) => listFolders(...(args as [number?])),
    createFolder: (...args: unknown[]) =>
      createFolder(...(args as [string, number | null, number])),
  }
})

function folder(id: number, name: string, parentId: number | null): Folder {
  return {
    id,
    name,
    path: name,
    course_id: 1,
    parent_id: parentId,
    source_id: null,
    created_at: '2026-08-21T00:00:00Z',
  }
}

function RESULT(id: number, title: string): UploadResult {
  return {
    material: {
      id,
      title,
      kind: 'pdf',
      status: 'pending',
      filename: title,
      mime: 'application/pdf',
      pages: 1,
      course_id: 1,
      group_id: null,
      folder_id: null,
      blob_sha: null,
      created_at: '2026-08-21T00:00:00Z',
    },
    job_id: null,
    deduped: false,
  }
}

function file(name: string, relativePath?: string): File {
  const blob = new File(['x'], name)
  if (relativePath !== undefined) {
    Object.defineProperty(blob, 'webkitRelativePath', { value: relativePath })
  }
  return blob
}

let held: MaterialUploadController | null = null

function Harness({
  courseId,
  getFolderId,
  onUploaded,
  onFolderCreated,
  variant = 'block',
}: {
  courseId: number | null
  getFolderId?: () => number | null
  onUploaded?: (result: UploadResult) => void
  onFolderCreated?: (folder: Folder) => void
  variant?: 'block' | 'row'
}) {
  const upload = useMaterialUpload({ courseId, getFolderId, onUploaded, onFolderCreated })
  held = upload
  return <UploadDropzone upload={upload} variant={variant} />
}

function renderHarness(props: Parameters<typeof Harness>[0]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const invalidateSpy = vi.spyOn(client, 'invalidateQueries')
  render(
    <QueryClientProvider client={client}>
      <Harness {...props} />
    </QueryClientProvider>
  )
  return invalidateSpy
}

describe('useMaterialUpload', () => {
  beforeEach(() => {
    uploadMaterial.mockReset()
    listFolders.mockReset()
    createFolder.mockReset()
  })

  test('uploads each file sequentially, invalidates, and keeps going after per-file errors', async () => {
    listFolders.mockResolvedValue([])
    uploadMaterial.mockImplementation(async (sent: File) =>
      sent.name === 'bad.pdf'
        ? Promise.reject(new Error('boom'))
        : Promise.resolve(RESULT(sent.name === 'a.pdf' ? 1 : 2, sent.name))
    )
    const onUploaded = vi.fn()
    const invalidateSpy = renderHarness({ courseId: 1, getFolderId: () => 4, onUploaded })

    await act(async () => {
      await held?.uploadFiles([file('a.pdf'), file('bad.pdf'), file('b.pdf')])
    })

    expect(uploadMaterial).toHaveBeenCalledTimes(3)
    for (const call of uploadMaterial.mock.calls) {
      expect(call[1]).toBe(1)
      expect(call[2]).toBe(4)
    }
    expect(onUploaded).toHaveBeenCalledTimes(2)
    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['materials'] })
    )
    expect(held?.errors).toEqual([{ name: 'bad.pdf', message: 'boom' }])
    expect(held?.uploading).toBe(false)
    expect(held?.currentName).toBeNull()
  })

  test('no-ops without a course', async () => {
    renderHarness({ courseId: null })
    await held?.uploadFiles([file('a.pdf')])
    expect(uploadMaterial).not.toHaveBeenCalled()
  })

  test('folder uploads recreate the directory tree, reusing existing folders', async () => {
    listFolders.mockResolvedValue([folder(20, 'Existing pack', null)])
    createFolder.mockImplementation(async (name: string, parentId: number | null) => {
      const id = 100 + createFolder.mock.calls.length
      return folder(id, name, parentId)
    })
    uploadMaterial.mockResolvedValue(RESULT(1, 'a.pdf'))
    renderHarness({ courseId: 1 })

    await act(async () => {
      await held?.uploadFiles([
        file('.DS_Store', 'pack/.DS_Store'),
        file('a.pdf', 'pack/a.pdf'),
        file('b.pdf', 'pack/inner/b.pdf'),
        file('c.pdf', 'pack/inner/deep/c.pdf'),
      ])
    })

    expect(createFolder).toHaveBeenCalledTimes(3)
    expect(createFolder).toHaveBeenNthCalledWith(1, 'pack', null, 1)
    expect(createFolder).toHaveBeenNthCalledWith(2, 'inner', 101, 1)
    expect(createFolder).toHaveBeenNthCalledWith(3, 'deep', 102, 1)

    const folderByCall = uploadMaterial.mock.calls.map((call) => call[2])
    expect(folderByCall).toEqual([101, 102, 103])
    expect(uploadMaterial).toHaveBeenCalledTimes(3)
  })

  test('existing folder chains are reused without createFolder calls', async () => {
    listFolders.mockResolvedValue([
      folder(30, 'pack', null),
      folder(31, 'inner', 30),
      folder(40, 'Other', null),
    ])
    uploadMaterial.mockResolvedValue(RESULT(2, 'n.pdf'))
    renderHarness({ courseId: 1 })

    await act(async () => {
      await held?.uploadFiles([file('n.pdf', 'pack/inner/n.pdf')])
    })

    expect(createFolder).not.toHaveBeenCalled()
    expect(uploadMaterial.mock.calls[0][2]).toBe(31)
  })

  test('a folder upload under a picker base folder nests below the base', async () => {
    listFolders.mockResolvedValue([folder(50, 'Base', null)])
    createFolder.mockImplementation(async (name: string, parentId: number | null) => {
      const id = 200 + createFolder.mock.calls.length
      return folder(id, name, parentId)
    })
    uploadMaterial.mockResolvedValue(RESULT(3, 'z.pdf'))
    renderHarness({ courseId: 1, getFolderId: () => 50 })

    await act(async () => {
      await held?.uploadFiles([file('z.pdf', 'tree/z.pdf')])
    })

    expect(createFolder).toHaveBeenCalledWith('tree', 50, 1)
    expect(uploadMaterial.mock.calls[0][2]).toBe(201)
  })

  test('onFolderCreated reports each top-level folder created', async () => {
    listFolders.mockResolvedValue([])
    createFolder.mockImplementation(async (name: string, parentId: number | null) => {
      const id = 400 + createFolder.mock.calls.length
      return folder(id, name, parentId)
    })
    uploadMaterial.mockResolvedValue(RESULT(3, 'z.pdf'))
    const onFolderCreated = vi.fn()
    renderHarness({ courseId: 1, onFolderCreated })

    await act(async () => {
      await held?.uploadFiles([
        file('a.pdf', 'pack/a.pdf'),
        file('b.pdf', 'pack/sub/b.pdf'),
        file('c.pdf', 'other/c.pdf'),
      ])
    })

    expect(onFolderCreated).toHaveBeenCalledTimes(2)
    const created = onFolderCreated.mock.calls.map((call) => call[0])
    expect(created.map((f) => f.name).sort()).toEqual(['other', 'pack'])
    expect(created[0].parent_id).toBeNull()
  })

  test('dropzone folder input accepts a directory selection', async () => {
    listFolders.mockResolvedValue([])
    createFolder.mockResolvedValue(folder(60, 'pack', null))
    uploadMaterial.mockResolvedValue(RESULT(4, 'd.pdf'))
    renderHarness({ courseId: 1 })

    expect(screen.getByRole('button', { name: 'Upload a folder' })).toBeInTheDocument()
    const input = screen.getByLabelText('Upload a folder')
    expect(input.hasAttribute('webkitdirectory')).toBe(true)

    fireEvent.change(input, {
      target: { files: [file('d.pdf', 'pack/d.pdf')] },
    })
    await waitFor(() => expect(uploadMaterial).toHaveBeenCalledTimes(1))
    expect(uploadMaterial.mock.calls[0][2]).toBe(60)
  })

  test('banner click offers both files and folder upload from the menu', async () => {
    listFolders.mockResolvedValue([])
    renderHarness({ courseId: 1 })

    fireEvent.click(screen.getByRole('button', { name: 'Choose what to upload' }))
    expect(await screen.findByRole('menu')).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Upload files…' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Upload folder…' })).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'Escape' })
  })

  test('banner menu folder option uploads through the directory picker', async () => {
    listFolders.mockResolvedValue([])
    createFolder.mockResolvedValue(folder(60, 'pack', null))
    uploadMaterial.mockResolvedValue(RESULT(4, 'd.pdf'))
    renderHarness({ courseId: 1 })

    fireEvent.click(screen.getByRole('button', { name: 'Choose what to upload' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Upload folder…' }))
    const input = screen.getByLabelText('Upload a folder')
    expect(input.hasAttribute('webkitdirectory')).toBe(true)
    fireEvent.change(input, {
      target: { files: [file('d.pdf', 'pack/d.pdf')] },
    })
    await waitFor(() => expect(uploadMaterial).toHaveBeenCalledTimes(1))
    expect(uploadMaterial.mock.calls[0][2]).toBe(60)
  })

  test('dropping a folder on the banner recreates the folder tree', async () => {
    listFolders.mockResolvedValue([])
    createFolder.mockImplementation(async (name: string, parentId: number | null) => {
      const id = 300 + createFolder.mock.calls.length
      return folder(id, name, parentId)
    })
    uploadMaterial.mockResolvedValue(RESULT(5, 'a.pdf'))
    renderHarness({ courseId: 1 })

    const makeFile = (name: string) => new File(['x'], name)
    const fileEntry = (name: string, blob: File) => ({
      isFile: true,
      isDirectory: false,
      name,
      file: (success: (f: File) => void) => success(blob),
    })
    const dirEntry = (name: string, children: unknown[]) => ({
      isFile: false,
      isDirectory: true,
      name,
      createReader: () => ({
        readEntries: (success: (entries: unknown[]) => void) => {
          success(children.slice())
          children.length = 0
        },
      }),
    })
    const root = makeFile('root.pdf')
    const inner = makeFile('inner.pdf')
    const tree = dirEntry('dropped', [
      fileEntry('root.pdf', root),
      dirEntry('sub', [fileEntry('inner.pdf', inner)]),
    ])
    const banner = screen.getByRole('button', { name: 'Choose what to upload' })
    fireEvent.drop(banner, {
      dataTransfer: {
        items: [{ webkitGetAsEntry: () => tree }],
        files: [],
      } as unknown as DataTransfer,
    })

    await waitFor(() => expect(uploadMaterial).toHaveBeenCalledTimes(2))
    expect(createFolder).toHaveBeenCalledWith('dropped', null, 1)
    expect(createFolder).toHaveBeenCalledWith('sub', 301, 1)
  })
})

describe('collectDropFiles', () => {
  test('falls back to plain files when entries are unavailable', async () => {
    const plain = file('plain.pdf')
    const transfer = {
      items: [plain],
      files: [plain],
    } as unknown as DataTransfer
    const items = await collectDropFiles(transfer)
    expect(items).toEqual([{ file: plain }])
  })

  test('traverses dropped directory entries into relative paths', async () => {
    const makeFile = (name: string) => new File(['x'], name)
    const fileEntry = (name: string, blob: File) => ({
      isFile: true,
      isDirectory: false,
      name,
      file: (success: (f: File) => void) => success(blob),
    })
    const dirEntry = (name: string, children: unknown[]) => ({
      isFile: false,
      isDirectory: true,
      name,
      createReader: () => ({
        readEntries: (success: (entries: unknown[]) => void) => {
          success(children.slice())
          children.length = 0
        },
      }),
    })
    const inner = makeFile('inner.pdf')
    const root = makeFile('root.pdf')
    const tree = dirEntry('dropped', [
      fileEntry('root.pdf', root),
      dirEntry('sub', [fileEntry('inner.pdf', inner)]),
    ])
    const transfer = {
      items: [{ webkitGetAsEntry: () => tree }],
      files: [],
    } as unknown as DataTransfer

    const items = await collectDropFiles(transfer)
    expect(items).toEqual([
      { file: root, relativePath: 'dropped/root.pdf' },
      { file: inner, relativePath: 'dropped/sub/inner.pdf' },
    ])
  })
})
