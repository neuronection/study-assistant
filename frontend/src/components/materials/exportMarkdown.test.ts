import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { markProfileSettled } from '@/lib/api'
import { exportMarkdownWithDrawings } from './exportMarkdown'

// drawing refs fetch through apiFetch — settle the §15 boot gate
beforeEach(() => {
  markProfileSettled()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('exportMarkdownWithDrawings', () => {
  test('resolves sa-drawing refs to embedded data URIs', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        arrayBuffer: async () => new Uint8Array([137, 80, 78, 71]).buffer,
      }))
    )
    const out = await exportMarkdownWithDrawings(
      'a ![drawing](sa-drawing://3) b ![drawing](sa-drawing://7)',
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
      'x ![drawing](sa-drawing://1) ![drawing](sa-drawing://2)',
      [
        { id: 1, png_sha: null },
        { id: 2, png_sha: 'missing-blob' },
      ]
    )
    expect(out).toBe('x ![drawing](sa-drawing://1) ![drawing](sa-drawing://2)')
  })
})