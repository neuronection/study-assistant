import type { DragEvent } from 'react'

export const ITEM_MIME = 'application/x-ca-item'
export const MATERIAL_MIME = 'application/x-ca-material'

export type DragKind = 'folder' | 'material' | 'note'

export interface DragPayload {
  folderIds: number[]
  materialIds: number[]
  noteIds: number[]
}

const emptyIds: number[] = []

export function buildDragPayload(
  event: DragEvent,
  opts: {
    key: string
    id: number
    kind: DragKind
    selected: ReadonlySet<string>
    selectedPayload: DragPayload
    setSelection: (keys: Iterable<string>) => void
    countLabel?: (count: number) => string
  }
): { payload: DragPayload; count: number } {
  const selected = opts.selected.has(opts.key)
  let payload: DragPayload
  if (selected) {
    payload = opts.selectedPayload
  } else {
    payload = singlePayload(opts.kind, opts.id)
    opts.setSelection([opts.key])
  }
  event.dataTransfer.setData(ITEM_MIME, JSON.stringify(payload))
  if (payload.materialIds.length > 0) {
    event.dataTransfer.setData(MATERIAL_MIME, String(payload.materialIds[0]))
  }
  event.dataTransfer.effectAllowed = 'move'
  const count = payload.folderIds.length + payload.materialIds.length + payload.noteIds.length
  if (count > 1 && opts.countLabel !== undefined) {
    setDragCountImage(event, count, opts.countLabel(count))
  }
  return { payload, count }
}

export function parseDragPayload(event: DragEvent): DragPayload | null {
  const raw = event.dataTransfer.getData(ITEM_MIME)
  if (!raw) {
    return null
  }
  try {
    const parsed = JSON.parse(raw) as {
      folderIds?: unknown
      materialIds?: unknown
      noteIds?: unknown
    }
    if (!Array.isArray(parsed.folderIds) || !Array.isArray(parsed.materialIds)) {
      return null
    }
    return {
      folderIds: parsed.folderIds.map(Number),
      materialIds: parsed.materialIds.map(Number),
      noteIds: Array.isArray(parsed.noteIds) ? parsed.noteIds.map(Number) : emptyIds,
    }
  } catch {
    return null
  }
}

export function setDragCountImage(event: DragEvent, count: number, label: string): void {
  if (count < 2 || typeof event.dataTransfer.setDragImage !== 'function') {
    return
  }
  const canvas = document.createElement('canvas')
  canvas.width = 72
  canvas.height = 24
  const ctx = canvas.getContext('2d')
  if (ctx === null) {
    return
  }
  ctx.fillStyle = 'rgba(15, 23, 42, 0.9)'
  ctx.beginPath()
  ctx.roundRect(0, 0, canvas.width, canvas.height, 6)
  ctx.fill()
  ctx.fillStyle = '#ffffff'
  ctx.font = '600 12px system-ui, sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(label, canvas.width / 2, canvas.height / 2 + 0.5)
  event.dataTransfer.setDragImage(canvas, 8, canvas.height / 2)
}

function singlePayload(kind: DragKind, id: number): DragPayload {
  if (kind === 'folder') {
    return { folderIds: [id], materialIds: emptyIds, noteIds: emptyIds }
  }
  if (kind === 'material') {
    return { folderIds: emptyIds, materialIds: [id], noteIds: emptyIds }
  }
  return { folderIds: emptyIds, materialIds: emptyIds, noteIds: [id] }
}
