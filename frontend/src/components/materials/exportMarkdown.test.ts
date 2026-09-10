import { afterEach, describe, expect, test, vi } from 'vitest'

import { exportMarkdownWithDrawings } from './exportMarkdown'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('exportMarkdownWithDrawings', () => {
  test('resolves ca-drawing refs to embedded data URIs', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        arrayBuffer: async () => new Uint8Array([137, 80, 78, 71]).buffer,
      }))
    )
    const out = await exportMarkdownWithDrawings(
      'a ![drawing](ca-drawing://3) b ![drawing](ca-drawing://7)',
      [
        { id: 3, png_sha: 'sha3' },
        { id: 7, png_sha: 'sha7' },
      ]
    )
    expect(out).toBe(
      'a ![drawing](data:image/png;base64,iVBORw==) b ![drawing](data:image/png;base64,iVBORw==)'
    )
  })

  test('leaves refs whose drawing has no image or whose fetch fails untouched', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: false }))
    )
    const out = await exportMarkdownWithDrawings(
      'x ![drawing](ca-drawing://1) ![drawing](ca-drawing://2)',
      [
        { id: 1, png_sha: null },
        { id: 2, png_sha: 'missing-blob' },
      ]
    )
    expect(out).toBe('x ![drawing](ca-drawing://1) ![drawing](ca-drawing://2)')
  })
})