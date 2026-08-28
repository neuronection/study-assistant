import { describe, expect, test } from 'vitest'

import type { NoteDetailInfo } from '@/lib/api'

import { noteBodyMd } from './useNoteAutosave'

function note(body: NoteDetailInfo['body']): NoteDetailInfo {
  return {
    id: 1,
    title: 't',
    course_id: null,
    node_id: null,
    owner_type: 'standalone',
    owner_id: null,
    tags: [],
    pinned: false,
    updated_at: '2026-08-21T10:00:00',
    body,
    drawings: [],
  }
}

describe('noteBodyMd', () => {
  test('legacy stripped blocks rejoin with paragraph breaks', () => {
    const md = noteBodyMd(
      note([
        { type: 'text', md: 'before' },
        { type: 'drawing', drawing_id: 4 },
        { type: 'text', md: 'after' },
      ])
    )
    expect(md).toBe('before\n\n![drawing](ca-drawing://4)\n\nafter')
  })

  test('verbatim blocks rejoin byte-identically', () => {
    const md = noteBodyMd(
      note([
        { type: 'text', md: 'para one\n\npara two\n\n\n\npara three\n' },
      ])
    )
    expect(md).toBe('para one\n\npara two\n\n\n\npara three\n')
  })

  test('whitespace-only segments around drawings survive', () => {
    const md = noteBodyMd(
      note([
        { type: 'text', md: 'start\n\n' },
        { type: 'drawing', drawing_id: 1 },
        { type: 'text', md: '\n\nmid\n\n\n' },
        { type: 'drawing', drawing_id: 2 },
        { type: 'text', md: '\ntail\n' },
      ])
    )
    expect(md).toBe(
      'start\n\n![drawing](ca-drawing://1)\n\nmid\n\n\n![drawing](ca-drawing://2)\ntail\n'
    )
  })

  test('empty text blocks are skipped without breaking boundaries', () => {
    const md = noteBodyMd(
      note([
        { type: 'text', md: 'only' },
        { type: 'text', md: '' },
        { type: 'text', md: 'second' },
      ])
    )
    expect(md).toBe('only\n\nsecond')
  })

  test('empty body yields an empty string', () => {
    expect(noteBodyMd(note([]))).toBe('')
    expect(
      noteBodyMd(note([{ type: 'text', md: '' }, { type: 'text', md: '' }]))
    ).toBe('')
  })
})
