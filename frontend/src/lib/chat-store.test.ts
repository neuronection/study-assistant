import { beforeEach, describe, expect, test } from 'vitest'

import { useChatStore } from './chat-store'

function resetStore() {
  useChatStore.setState({
    open: false,
    session: null,
    pendingSend: null,
    viewerAsks: {},
    selectionAsks: {},
    width: 384,
  })
}

describe('chat-store', () => {
  beforeEach(() => {
    window.localStorage.clear()
    resetStore()
  })

  test('queueSend stages a pending ask exactly until cleared', () => {
    useChatStore.getState().queueSend({ content: 'why?', mode: 'send' })
    expect(useChatStore.getState().pendingSend).toEqual({ content: 'why?', mode: 'send' })
    useChatStore.getState().clearPendingSend()
    expect(useChatStore.getState().pendingSend).toBeNull()
  })

  test('viewer ask pins are stored per material and reusable', () => {
    const ref = { id: 4, publicId: 'uuid-4' }
    useChatStore.getState().setViewerAsk(12, ref)
    expect(useChatStore.getState().viewerAsks[12]).toEqual(ref)
    useChatStore.getState().setViewerAsk(30, { id: 9, publicId: 'uuid-9' })
    expect(Object.keys(useChatStore.getState().viewerAsks)).toEqual(['12', '30'])
    useChatStore.getState().clearViewerAsk(12)
    expect(useChatStore.getState().viewerAsks[12]).toBeUndefined()
    expect(useChatStore.getState().viewerAsks[30]).toBeDefined()
    useChatStore.getState().clearViewerAsk()
    expect(useChatStore.getState().viewerAsks).toEqual({})
  })

  test('selection ask pins are keyed by the material selection and clearable', () => {
    const ref = { id: 5, publicId: 'uuid-5' }
    useChatStore.getState().setSelectionAsk('7-12', ref)
    useChatStore.getState().setSelectionAsk('7-12-30', { id: 6, publicId: 'uuid-6' })
    expect(useChatStore.getState().selectionAsks['7-12']).toEqual(ref)
    useChatStore.getState().clearSelectionAsk('7-12')
    expect(useChatStore.getState().selectionAsks['7-12']).toBeUndefined()
    expect(useChatStore.getState().selectionAsks['7-12-30']).toBeDefined()
    useChatStore.getState().clearSelectionAsk()
    expect(useChatStore.getState().selectionAsks).toEqual({})
  })

  test('openSession pins and opens; setOpen(false) unpins', () => {
    useChatStore.getState().openSession({ id: 7, publicId: 'uuid-7' })
    expect(useChatStore.getState().open).toBe(true)
    expect(useChatStore.getState().session).toEqual({ id: 7, publicId: 'uuid-7' })
    useChatStore.getState().setOpen(false)
    expect(useChatStore.getState().open).toBe(false)
    expect(useChatStore.getState().session).toBeNull()
  })

  test('setChatWidth clamps into bounds and persistChatWidth writes storage', () => {
    useChatStore.getState().setChatWidth(120)
    expect(useChatStore.getState().width).toBe(320)
    useChatStore.getState().setChatWidth(5000)
    expect(useChatStore.getState().width).toBe(720)
    useChatStore.getState().setChatWidth(468.4)
    expect(useChatStore.getState().width).toBe(468)
    useChatStore.getState().persistChatWidth()
    expect(window.localStorage.getItem('ca-chat-width')).toBe('468')
  })
})
