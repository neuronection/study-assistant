import { vi } from 'vitest'

export interface FakeCache {
  name: string
  store: Map<string, Blob>
  match: (request: RequestInfo) => Promise<Response | undefined>
  put: (request: RequestInfo, response: Response) => Promise<void>
  add: (request: RequestInfo) => Promise<void>
  delete: (request: RequestInfo) => Promise<boolean>
}

export interface FakeCacheStorage {
  open: (name: string) => Promise<FakeCache>
  keys: () => Promise<string[]>
  delete: (name: string) => Promise<boolean>
  has: (name: string) => Promise<boolean>
  caches: Map<string, FakeCache>
  cache: (name: string) => FakeCache | undefined
  seed: (name: string, src: string, blob: Blob) => Promise<void>
}

/** Shared Cache Storage fixture for the audio-offline/player tests. `add`
 * throws so a regression to `cache.add(src)` fails loudly. */
export function installFakeCaches(): FakeCacheStorage {
  const entries = new Map<string, FakeCache>()

  const getCache = (name: string): FakeCache => {
    const existing = entries.get(name)
    if (existing !== undefined) {
      return existing
    }
    const store = new Map<string, Blob>()
    const cache: FakeCache = {
      name,
      store,
      match: vi.fn(async (request: RequestInfo) => {
        const blob = store.get(String(request))
        return blob === undefined ? undefined : new Response(blob)
      }),
      put: vi.fn(async (request: RequestInfo, response: Response) => {
        store.set(String(request), await response.blob())
      }),
      add: vi.fn(async () => {
        throw new Error('cache.add must not be used for protected audio')
      }),
      delete: vi.fn(async (request: RequestInfo) => store.delete(String(request))),
    }
    entries.set(name, cache)
    return cache
  }

  const open = vi.fn(async (name: string) => getCache(name))
  const keys = vi.fn(async () => [...entries.keys()])
  const remove = vi.fn(async (name: string) => entries.delete(name))
  const has = vi.fn(async (name: string) => entries.has(name))

  vi.stubGlobal('caches', { open, keys, delete: remove, has })

  return {
    open,
    keys,
    delete: remove,
    has,
    caches: entries,
    cache: (name: string) => entries.get(name),
    seed: async (name: string, src: string, blob: Blob) => {
      getCache(name).store.set(src, blob)
    },
  }
}
