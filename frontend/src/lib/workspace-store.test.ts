import { beforeEach, describe, expect, test } from 'vitest'

import { useWorkspaceStore } from './workspace-store'
import { storageKeys } from '@/lib/constants'

describe('workspace-store', () => {
  beforeEach(() => {
    window.localStorage.clear()
    useWorkspaceStore.setState({ courseId: null, hydrated: false })
  })

  test('defaults to all courses with empty storage', () => {
    useWorkspaceStore.getState().hydrate()
    expect(useWorkspaceStore.getState().courseId).toBeNull()
    expect(useWorkspaceStore.getState().hydrated).toBe(true)
  })

  test('setCourse persists and clears', () => {
    useWorkspaceStore.getState().setCourse(3)
    expect(useWorkspaceStore.getState().courseId).toBe(3)
    expect(window.localStorage.getItem(storageKeys.courseId)).toBe('3')

    useWorkspaceStore.getState().setCourse(null)
    expect(useWorkspaceStore.getState().courseId).toBeNull()
    expect(window.localStorage.getItem(storageKeys.courseId)).toBeNull()
  })

  test('hydrate reads the stored course and rejects junk', () => {
    window.localStorage.setItem(storageKeys.courseId, '7')
    useWorkspaceStore.getState().hydrate()
    expect(useWorkspaceStore.getState().courseId).toBe(7)

    window.localStorage.setItem(storageKeys.courseId, 'not-a-number')
    useWorkspaceStore.getState().hydrate()
    expect(useWorkspaceStore.getState().courseId).toBeNull()
  })
})
