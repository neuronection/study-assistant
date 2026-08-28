import { beforeEach, describe, expect, test } from 'vitest'

import { useClipboardStore } from './clipboard-store'

describe('clipboard-store', () => {
  beforeEach(() => {
    useClipboardStore.setState({ item: null })
  })

  test('set and clear round-trip the clipboard payload', () => {
    useClipboardStore.getState().set({
      kind: 'library',
      courseId: 3,
      folderIds: [1],
      materialIds: [10, 11],
      mode: 'cut',
    })
    expect(useClipboardStore.getState().item).toEqual({
      kind: 'library',
      courseId: 3,
      folderIds: [1],
      materialIds: [10, 11],
      mode: 'cut',
    })

    useClipboardStore.getState().clear()
    expect(useClipboardStore.getState().item).toBeNull()
  })
})
