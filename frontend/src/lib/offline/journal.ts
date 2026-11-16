import type { CaptureSourceKind } from '@/lib/api'

export class JournalNonRetryableError extends Error {}

export type JournalEntity = 'capture' | 'review' | 'lecture'

interface JournalOpBase {
  id: string
  entity: JournalEntity
  createdAt: number
  attempts: number
  lastError: string | null
  failed: boolean
}

export interface CaptureJournalOp extends JournalOpBase {
  entity: 'capture'
  payload: {
    filename: string
    mime: string
    size: number
    sourceKind: CaptureSourceKind
  }
}

export interface ReviewJournalOp extends JournalOpBase {
  entity: 'review'
  payload: {
    cardId: string
    rating: number
    reviewedAt: number
  }
}

export interface LectureJournalOp extends JournalOpBase {
  entity: 'lecture'
  payload: {
    sessionId: string
    seq: number
    sha256: string
    mime: string
  }
}

export type JournalOp = CaptureJournalOp | ReviewJournalOp | LectureJournalOp

export function isCaptureOp(op: JournalOp): op is CaptureJournalOp {
  return op.entity === 'capture'
}

export function isReviewOp(op: JournalOp): op is ReviewJournalOp {
  return op.entity === 'review'
}

export function isLectureOp(op: JournalOp): op is LectureJournalOp {
  return op.entity === 'lecture'
}

export interface JournalSnapshot {
  ops: JournalOp[]
  durable: boolean
}

export type JournalTransport = (op: JournalOp, blob: Blob | null) => Promise<unknown>

interface JournalBackend {
  readonly durable: boolean
  putOp(op: JournalOp): Promise<void>
  listOps(): Promise<JournalOp[]>
  deleteOp(id: string): Promise<void>
  putBlob(id: string, blob: Blob): Promise<void>
  getBlob(id: string): Promise<Blob | null>
  deleteBlob(id: string): Promise<void>
  acquireLease(owner: string, ttlMs: number): Promise<boolean>
  releaseLease(owner: string): Promise<void>
}

const LEASE_MS = 30_000
const DB_NAME = 'sa-offline-journal'
const DB_VERSION = 2

function newId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `op-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains('ops')) {
        db.createObjectStore('ops', { keyPath: 'id' })
      }
      if (!db.objectStoreNames.contains('blobs')) {
        db.createObjectStore('blobs')
      }
      if (!db.objectStoreNames.contains('meta')) {
        db.createObjectStore('meta', { keyPath: 'key' })
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('indexedDB open failed'))
  })
}

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('indexedDB request failed'))
  })
}

class IndexedDbBackend implements JournalBackend {
  readonly durable = true
  private readonly database: Promise<IDBDatabase>

  constructor() {
    this.database = openDatabase()
  }

  private async store(name: string, mode: IDBTransactionMode): Promise<IDBObjectStore> {
    const db = await this.database
    return db.transaction(name, mode).objectStore(name)
  }

  async putOp(op: JournalOp): Promise<void> {
    const store = await this.store('ops', 'readwrite')
    await requestResult(store.put(op))
  }

  async listOps(): Promise<JournalOp[]> {
    const store = await this.store('ops', 'readonly')
    const rows = await requestResult(store.getAll() as IDBRequest<JournalOp[]>)
    return rows.sort((left, right) => left.createdAt - right.createdAt)
  }

  async deleteOp(id: string): Promise<void> {
    const store = await this.store('ops', 'readwrite')
    await requestResult(store.delete(id))
  }

  async putBlob(id: string, blob: Blob): Promise<void> {
    const store = await this.store('blobs', 'readwrite')
    await requestResult(store.put(blob, id))
  }

  async getBlob(id: string): Promise<Blob | null> {
    const store = await this.store('blobs', 'readonly')
    const blob = await requestResult(store.get(id) as IDBRequest<Blob | undefined>)
    return blob ?? null
  }

  async deleteBlob(id: string): Promise<void> {
    const store = await this.store('blobs', 'readwrite')
    await requestResult(store.delete(id))
  }

  async acquireLease(owner: string, ttlMs: number): Promise<boolean> {
    const db = await this.database
    return new Promise((resolve, reject) => {
      const transaction = db.transaction('meta', 'readwrite')
      const store = transaction.objectStore('meta')
      const current = store.get('lease') as IDBRequest<
        { owner: string; expiresAt: number } | undefined
      >
      current.onsuccess = () => {
        if (
          current.result !== undefined &&
          current.result.expiresAt > Date.now() &&
          current.result.owner !== owner
        ) {
          resolve(false)
          return
        }
        const put = store.put({ key: 'lease', owner, expiresAt: Date.now() + ttlMs })
        put.onsuccess = () => resolve(true)
        put.onerror = () => reject(put.error ?? new Error('lease write failed'))
      }
      current.onerror = () => reject(current.error ?? new Error('lease read failed'))
    })
  }

  async releaseLease(owner: string): Promise<void> {
    const db = await this.database
    return new Promise((resolve, reject) => {
      const transaction = db.transaction('meta', 'readwrite')
      const store = transaction.objectStore('meta')
      const current = store.get('lease') as IDBRequest<
        { key: string; owner: string } | undefined
      >
      current.onsuccess = () => {
        if (current.result?.owner !== owner) {
          resolve()
          return
        }
        const removed = store.delete('lease')
        removed.onsuccess = () => resolve()
        removed.onerror = () => reject(removed.error ?? new Error('lease delete failed'))
      }
      current.onerror = () => reject(current.error ?? new Error('lease read failed'))
    })
  }
}

export class MemoryJournalBackend implements JournalBackend {
  readonly durable = false
  private readonly ops = new Map<string, JournalOp>()
  private readonly blobs = new Map<string, Blob>()
  private leaseOwner: string | null = null
  private leaseUntil = 0

  async putOp(op: JournalOp): Promise<void> {
    this.ops.set(op.id, op)
  }

  async listOps(): Promise<JournalOp[]> {
    return [...this.ops.values()].sort((left, right) => left.createdAt - right.createdAt)
  }

  async deleteOp(id: string): Promise<void> {
    this.ops.delete(id)
  }

  async putBlob(id: string, blob: Blob): Promise<void> {
    this.blobs.set(id, blob)
  }

  async getBlob(id: string): Promise<Blob | null> {
    return this.blobs.get(id) ?? null
  }

  async deleteBlob(id: string): Promise<void> {
    this.blobs.delete(id)
  }

  async acquireLease(owner: string, ttlMs: number): Promise<boolean> {
    if (this.leaseOwner !== null && this.leaseUntil > Date.now() && this.leaseOwner !== owner) {
      return false
    }
    this.leaseOwner = owner
    this.leaseUntil = Date.now() + ttlMs
    return true
  }

  async releaseLease(owner: string): Promise<void> {
    if (this.leaseOwner === owner) {
      this.leaseOwner = null
      this.leaseUntil = 0
    }
  }
}

export class OfflineJournal {
  readonly durable: boolean
  private readonly backend: JournalBackend
  private readonly listeners = new Set<() => void>()
  private snapshot: JournalSnapshot
  private draining = false

  constructor(backend: JournalBackend) {
    this.backend = backend
    this.durable = backend.durable
    this.snapshot = { ops: [], durable: backend.durable }
  }

  getSnapshot = (): JournalSnapshot => this.snapshot

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener)
    void this.refresh()
    return () => {
      this.listeners.delete(listener)
    }
  }

  async enqueueCapture(file: File, sourceKind: CaptureSourceKind): Promise<CaptureJournalOp> {
    const op: CaptureJournalOp = {
      id: newId(),
      entity: 'capture',
      createdAt: Date.now(),
      attempts: 0,
      lastError: null,
      failed: false,
      payload: {
        filename: file.name || 'capture',
        mime: file.type,
        size: file.size,
        sourceKind,
      },
    }
    await this.backend.putBlob(op.id, file)
    await this.backend.putOp(op)
    await this.refresh()
    return op
  }

  async enqueueLectureChunk(
    sessionId: string,
    seq: number,
    blob: Blob,
    sha256: string,
    mime: string
  ): Promise<LectureJournalOp> {
    const op: LectureJournalOp = {
      id: newId(),
      entity: 'lecture',
      createdAt: Date.now(),
      attempts: 0,
      lastError: null,
      failed: false,
      payload: { sessionId, seq, sha256, mime },
    }
    await this.backend.putBlob(op.id, blob)
    await this.backend.putOp(op)
    await this.refresh()
    return op
  }

  async enqueueReview(
    cardId: string,
    rating: number,
    reviewedAt: number = Date.now()
  ): Promise<ReviewJournalOp> {
    const op: ReviewJournalOp = {
      id: newId(),
      entity: 'review',
      createdAt: Date.now(),
      attempts: 0,
      lastError: null,
      failed: false,
      payload: { cardId, rating, reviewedAt },
    }
    await this.backend.putOp(op)
    await this.refresh()
    return op
  }

  async remove(id: string): Promise<void> {
    await this.backend.deleteOp(id)
    await this.backend.deleteBlob(id)
    await this.refresh()
  }

  async retry(id: string): Promise<void> {
    const op = this.snapshot.ops.find((entry) => entry.id === id)
    if (op === undefined) {
      return
    }
    await this.backend.putOp({ ...op, failed: false, lastError: null })
    await this.refresh()
  }

  async drain(entity: JournalEntity, transport: JournalTransport): Promise<number> {
    if (this.draining || (typeof navigator !== 'undefined' && navigator.onLine === false)) {
      return 0
    }
    this.draining = true
    const owner = newId()
    let completed = 0
    try {
      if (!(await this.backend.acquireLease(owner, LEASE_MS))) {
        return 0
      }
      const ops = (await this.backend.listOps()).filter((op) => op.entity === entity)
      for (const op of ops) {
        if (op.failed) {
          continue
        }
        const blob =
          op.entity === 'capture' || op.entity === 'lecture'
            ? await this.backend.getBlob(op.id)
            : null
        if (op.entity !== 'review' && blob === null) {
          await this.backend.putOp({
            ...op,
            failed: true,
            lastError: 'The saved file is missing.',
          })
          await this.refresh()
          continue
        }
        try {
          await transport(op, blob)
          await this.backend.deleteOp(op.id)
          if (op.entity !== 'review') {
            await this.backend.deleteBlob(op.id)
          }
          completed += 1
        } catch (cause) {
          const message = cause instanceof Error ? cause.message : String(cause)
          const nonRetryable = cause instanceof JournalNonRetryableError
          await this.backend.putOp({
            ...op,
            attempts: op.attempts + 1,
            lastError: message,
            failed: nonRetryable,
          })
        }
        await this.refresh()
      }
      return completed
    } finally {
      await this.backend.releaseLease(owner)
      this.draining = false
      await this.refresh()
    }
  }

  private async refresh(): Promise<void> {
    const ops = await this.backend.listOps()
    this.snapshot = { ops, durable: this.backend.durable }
    for (const listener of this.listeners) {
      listener()
    }
  }
}

function createDefaultBackend(): JournalBackend {
  if (typeof indexedDB === 'undefined') {
    return new MemoryJournalBackend()
  }
  return new IndexedDbBackend()
}

export const offlineJournal = new OfflineJournal(createDefaultBackend())
