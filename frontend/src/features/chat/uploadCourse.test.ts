import { describe, expect, test } from 'vitest'

import type { Course } from '@/lib/api'
import {
  chatUploadFolderName,
  chatUploadFolderPattern,
  resolveUploadCourse,
  sanitizeFolderTitle,
} from './uploadCourse'

function course(id: number, title: string, archived = false): Course {
  return {
    id,
    title,
    subject: null,
    level: null,
    description: null,
    color: null,
    archived_at: archived ? new Date().toISOString() : null,
    material_count: 0,
  }
}

describe('resolveUploadCourse', () => {
  test('prefers the Unsorted course over other courses', () => {
    expect(resolveUploadCourse([course(1, 'Calculus'), course(2, 'Unsorted')])?.id).toBe(2)
  })

  test('falls back to the single active course', () => {
    expect(resolveUploadCourse([course(1, 'Calculus')])?.id).toBe(1)
  })

  test('ignores archived courses', () => {
    expect(resolveUploadCourse([course(1, 'Calculus', true)])).toBeNull()
    expect(resolveUploadCourse([course(1, 'Calculus', true), course(2, 'Unsorted')])?.id).toBe(2)
  })

  test('returns null with several courses and no Unsorted', () => {
    expect(resolveUploadCourse([course(1, 'Calculus'), course(2, 'Algebra')])).toBeNull()
    expect(resolveUploadCourse([])).toBeNull()
  })
})

describe('chat upload folder naming', () => {
  test('builds a stable per-session folder name', () => {
    expect(chatUploadFolderName('New chat', 4)).toBe('New chat (#4)')
  })

  test('sanitizes filesystem-hostile characters and truncates long titles', () => {
    expect(sanitizeFolderTitle('a/b:c*d?"<>|')).toBe('a b c d')
    expect(sanitizeFolderTitle('   spaced   out   ')).toBe('spaced out')
    expect(sanitizeFolderTitle('x'.repeat(100))).toBe('x'.repeat(60))
    expect(sanitizeFolderTitle('///')).toBe('Chat')
  })

  test('titles cannot spoof the session suffix', () => {
    const name = chatUploadFolderName('weird (#9) title', 4)
    expect(name).toBe('weird ( 9) title (#4)')
    expect(chatUploadFolderPattern(4).test(name)).toBe(true)
    expect(chatUploadFolderPattern(9).test(name)).toBe(false)
  })

  test('the pattern matches legacy folders regardless of older titles', () => {
    expect(chatUploadFolderPattern(7).test('Older title (#7)')).toBe(true)
    expect(chatUploadFolderPattern(7).test('Older title (#17)')).toBe(false)
  })
})
