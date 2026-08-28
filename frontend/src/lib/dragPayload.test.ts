import { describe, expect, test, vi } from 'vitest'

import {
  buildDragPayload,
  ITEM_MIME,
  MATERIAL_MIME,
  parseDragPayload,
  setDragCountImage,
} from './dragPayload'

function makeDataTransfer() {
  const data: Record<string, string> = {}
  const setData = vi.fn((mime: string, value: string) => {
    data[mime] = value
  })
  const getData = vi.fn((mime: string) => data[mime] ?? '')
  return {
    setData,
    getData,
    data,
    effectAllowed: '',
    setDragImage: vi.fn(),
    types: [] as string[],
  }
}

function dragEvent(dataTransfer: ReturnType<typeof makeDataTransfer>) {
  return { dataTransfer } as unknown as React.DragEvent
}

const emptyPayload = { folderIds: [], materialIds: [], noteIds: [] }

describe('buildDragPayload', () => {
  test('selected item drags the whole selection across kinds', () => {
    const dt = makeDataTransfer()
    const result = buildDragPayload(dragEvent(dt), {
      key: 'm3',
      id: 3,
      kind: 'material',
      selected: new Set(['m3', 'm5', 'f7']),
      selectedPayload: { folderIds: [7], materialIds: [3, 5], noteIds: [] },
      setSelection: vi.fn(),
    })
    expect(result.payload).toEqual({ folderIds: [7], materialIds: [3, 5], noteIds: [] })
    expect(result.count).toBe(3)
    expect(dt.setData).toHaveBeenCalledWith(
      ITEM_MIME,
      JSON.stringify({ folderIds: [7], materialIds: [3, 5], noteIds: [] })
    )
    expect(dt.setData).toHaveBeenCalledWith(MATERIAL_MIME, '3')
    expect(dt.effectAllowed).toBe('move')
  })

  test('unselected item drags just it and joins the selection', () => {
    const dt = makeDataTransfer()
    const setSelection = vi.fn()
    const result = buildDragPayload(dragEvent(dt), {
      key: 'n9',
      id: 9,
      kind: 'note',
      selected: new Set(['n1']),
      selectedPayload: { folderIds: [], materialIds: [], noteIds: [1] },
      setSelection,
    })
    expect(result.payload).toEqual({ folderIds: [], materialIds: [], noteIds: [9] })
    expect(result.count).toBe(1)
    expect(setSelection).toHaveBeenCalledWith(['n9'])
    expect(dt.setData).not.toHaveBeenCalledWith(MATERIAL_MIME, expect.any(String))
  })

  test('single item never sets a drag image', () => {
    const dt = makeDataTransfer()
    const countLabel = vi.fn()
    buildDragPayload(dragEvent(dt), {
      key: 'm1',
      id: 1,
      kind: 'material',
      selected: new Set(),
      selectedPayload: emptyPayload,
      setSelection: vi.fn(),
      countLabel,
    })
    expect(countLabel).not.toHaveBeenCalled()
  })
})

describe('parseDragPayload', () => {
  test('parses a valid multi-kind payload', () => {
    const dt = makeDataTransfer()
    dt.setData(ITEM_MIME, JSON.stringify({ folderIds: [7], materialIds: [3], noteIds: [9] }))
    expect(parseDragPayload(dragEvent(dt))).toEqual({
      folderIds: [7],
      materialIds: [3],
      noteIds: [9],
    })
  })

  test('missing noteIds parses as empty notes', () => {
    const dt = makeDataTransfer()
    dt.setData(ITEM_MIME, JSON.stringify({ folderIds: [], materialIds: [3] }))
    expect(parseDragPayload(dragEvent(dt))).toEqual({
      folderIds: [],
      materialIds: [3],
      noteIds: [],
    })
  })

  test('null on empty, malformed, or wrong mime', () => {
    expect(parseDragPayload(dragEvent(makeDataTransfer()))).toBeNull()
    const malformed = makeDataTransfer()
    malformed.setData(ITEM_MIME, '{not json')
    expect(parseDragPayload(dragEvent(malformed))).toBeNull()
    const wrong = makeDataTransfer()
    wrong.setData('application/x-other', '{}')
    expect(parseDragPayload(dragEvent(wrong))).toBeNull()
  })
})

describe('setDragCountImage', () => {
  test('sets a badge image for multi-item drags', () => {
    const ctx = {
      fillStyle: '',
      beginPath: vi.fn(),
      roundRect: vi.fn(),
      fill: vi.fn(),
      fillText: vi.fn(),
      font: '',
      textAlign: '',
      textBaseline: '',
    }
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
      ctx as unknown as CanvasRenderingContext2D
    )
    const dt = makeDataTransfer()
    setDragCountImage(dragEvent(dt), 3, '3 items')
    expect(dt.setDragImage).toHaveBeenCalledTimes(1)
    expect(dt.setDragImage.mock.calls[0][0]).toBeInstanceOf(HTMLCanvasElement)
    expect(ctx.fillText).toHaveBeenCalledWith('3 items', expect.any(Number), expect.any(Number))
  })

  test('no-op below two items', () => {
    const dt = makeDataTransfer()
    setDragCountImage(dragEvent(dt), 1, '1 item')
    expect(dt.setDragImage).not.toHaveBeenCalled()
  })
})