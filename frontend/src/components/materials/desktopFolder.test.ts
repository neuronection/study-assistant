import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import type { MaterialUploadController } from '@/components/materials/materialUpload'
import {
  desktopFolderMode,
  fetchDesktopDropItems,
  parseFileUris,
  pickFolder,
  uploadDesktopFolder,
} from './desktopFolder'

function controller(): MaterialUploadController {
  return {
    uploadFiles: vi.fn().mockResolvedValue([]),
    uploading: false,
    currentName: null,
    errors: [],
    warnings: [],
    clearErrors: vi.fn(),
    reportError: vi.fn(),
  }
}

function okResponse(body: unknown): Response {
  return {
    ok: true,
    json: () => Promise.resolve(body),
  } as unknown as Response
}

function fileResponse(bytes: string): Response {
  return {
    ok: true,
    blob: () => Promise.resolve(new Blob([bytes])),
  } as unknown as Response
}

const entries = [
  { path: '/tmp/docs/a.pdf', rel: 'docs/a.pdf', size: 3, mtime: 100 },
  { path: '/tmp/docs/sub/b.txt', rel: 'docs/sub/b.txt', size: 2, mtime: 200 },
]

function installBridge(pickFolderResult: string | null): void {
  window.pywebview = { api: { pick_folder: vi.fn().mockResolvedValue(pickFolderResult) } }
}

beforeEach(() => {
  delete window.pywebview
})

afterEach(() => {
  delete window.pywebview
  vi.unstubAllGlobals()
})

describe('desktopFolderMode', () => {
  test('detects the pywebview bridge', () => {
    expect(desktopFolderMode()).toBe(false)
    installBridge(null)
    expect(desktopFolderMode()).toBe(true)
  })
})

describe('uploadDesktopFolder', () => {
  test('no-op when cancelled', async () => {
    installBridge(null)
    const upload = controller()
    await uploadDesktopFolder(upload)
    expect(upload.uploadFiles).not.toHaveBeenCalled()
    expect(upload.reportError).not.toHaveBeenCalled()
  })

  test('uploads picked files with rooted relative paths', async () => {
    installBridge('/tmp/docs')
    const fetch = vi.fn(async (url: string) => {
      if (url.includes('/desktop/folder')) {
        return okResponse({ path: '/tmp/docs', files: entries })
      }
      return fileResponse('AAA')
    })
    vi.stubGlobal('fetch', fetch)
    const upload = controller()
    await uploadDesktopFolder(upload)
    expect(upload.uploadFiles).toHaveBeenCalledTimes(1)
    const items = vi.mocked(upload.uploadFiles).mock.calls[0][0] as {
      file: File
      relativePath?: string
    }[]
    expect(items.map((item) => item.relativePath)).toEqual(['docs/a.pdf', 'docs/sub/b.txt'])
    expect(items[0].file.name).toBe('a.pdf')
    expect(items[0].file.lastModified).toBe(100_000)
  })

  test('reports a listing failure without uploading', async () => {
    installBridge('/tmp/docs')
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        ({ ok: false, status: 404, json: () => Promise.resolve({ detail: 'nope' }) }) as unknown as Response,
      ),
    )
    const upload = controller()
    await uploadDesktopFolder(upload)
    expect(upload.reportError).toHaveBeenCalledWith({ name: '/tmp/docs', message: 'nope' })
    expect(upload.uploadFiles).not.toHaveBeenCalled()
  })

  test('skips a failed file and uploads the rest', async () => {
    installBridge('/tmp/docs')
    const fetch = vi.fn(async (url: string) => {
      if (url.includes('/desktop/folder')) {
        return okResponse({ path: '/tmp/docs', files: entries })
      }
      if (url.includes('a.pdf')) {
        return { ok: false, status: 500 } as unknown as Response
      }
      return fileResponse('BB')
    })
    vi.stubGlobal('fetch', fetch)
    const upload = controller()
    await uploadDesktopFolder(upload)
    expect(upload.reportError).toHaveBeenCalledWith({
      name: 'docs/a.pdf',
      message: 'request failed: 500',
    })
    const items = vi.mocked(upload.uploadFiles).mock.calls[0][0] as { relativePath?: string }[]
    expect(items.map((item) => item.relativePath)).toEqual(['docs/sub/b.txt'])
  })
})

describe('parseFileUris', () => {
  test('extracts and decodes file:// uris, skipping non-file lines', () => {
    const transfer = {
      getData: (type: string) =>
        type === 'text/uri-list'
          ? 'file:///tmp/a.pdf\r\nfile:///tmp/b%20c.txt\nhttps://example.com'
          : '',
    } as unknown as DataTransfer
    expect(parseFileUris(transfer)).toEqual(['/tmp/a.pdf', '/tmp/b c.txt'])
  })

  test('returns empty without getData or empty payload', () => {
    expect(parseFileUris({} as unknown as DataTransfer)).toEqual([])
    const transfer = { getData: () => '' } as unknown as DataTransfer
    expect(parseFileUris(transfer)).toEqual([])
  })

  test('falls back to file urls embedded in the text/html anchor (WebKitGTK)', () => {
    const transfer = {
      getData: (type: string) =>
        type === 'text/html'
          ? '<a style="color: black">file:///home/u/%CE%A3%CF%87%CE%BF%CE%BB%CE%AE/note.docx</a>'
          : '',
    } as unknown as DataTransfer
    expect(parseFileUris(transfer)).toEqual(['/home/u/Σχολή/note.docx'])
  })

  test('prefers text/uri-list when both channels are present', () => {
    const transfer = {
      getData: (type: string) =>
        type === 'text/uri-list'
          ? 'file:///tmp/from-uri.pdf'
          : '<a>file:///tmp/from-html.pdf</a>',
    } as unknown as DataTransfer
    expect(parseFileUris(transfer)).toEqual(['/tmp/from-uri.pdf'])
  })
})

describe('fetchDesktopDropItems', () => {
  test('registers paths and builds upload items', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.includes('/desktop/drops')) {
          return okResponse({
            files: [
              { path: '/tmp/docs/a.pdf', rel: 'a.pdf', size: 3, mtime: 7 },
              { path: '/tmp/docs/pack/b.pdf', rel: 'pack/b.pdf', size: 2, mtime: 8 },
            ],
          })
        }
        return fileResponse('AAA')
      }),
    )
    const items = await fetchDesktopDropItems(['/tmp/docs/a.pdf', '/tmp/docs/pack'])
    expect(items.map((item) => item.relativePath)).toEqual(['a.pdf', 'pack/b.pdf'])
    expect(items[0].file.lastModified).toBe(7000)
  })
})

describe('pickFolder', () => {
  test('clicks the hidden input outside desktop mode', () => {
    const input = { click: vi.fn() }
    const handler = pickFolder(controller(), { current: input as unknown as HTMLInputElement })
    handler()
    expect(input.click).toHaveBeenCalledTimes(1)
  })

  test('uses the desktop bridge inside desktop mode', async () => {
    installBridge(null)
    const input = { click: vi.fn() }
    const handler = pickFolder(controller(), { current: input as unknown as HTMLInputElement })
    handler()
    expect(input.click).not.toHaveBeenCalled()
    await vi.waitFor(() => expect(window.pywebview?.api.pick_folder).toHaveBeenCalled())
  })
})
