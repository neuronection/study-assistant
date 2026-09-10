import { beforeEach, describe, expect, test, vi } from 'vitest'

import { askMaterial, askMaterials, quoteSelection, selectionAskKey } from './useMaterialAsk'
import { useChatStore } from '@/lib/chat-store'

const createChatSession = vi.fn()
const updateChatSessionQuizme = vi.fn()

vi.mock('@/lib/api', () => ({
  createChatSession: (...args: unknown[]) => createChatSession(...(args as [])),
  updateChatSessionQuizme: (...args: unknown[]) =>
    updateChatSessionQuizme(...(args as [number, boolean])),
}))

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

describe('askMaterial', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resetStore()
  })

  test('first ask creates a scoped session, pins it per material and queues the send', async () => {
    createChatSession.mockResolvedValue({
      id: 21,
      public_id: 'uuid-21',
      course_id: 3,
      title: 'Lecture notes',
    })
    await askMaterial({
      material: { id: 12, course_id: 3, title: 'Lecture notes' },
      scopeNodeId: 8,
      content: 'Summarize this',
      attachments: [{ kind: 'material', id: 12 }],
      mode: 'send',
    })
    expect(createChatSession).toHaveBeenCalledWith(3, 8, 'Lecture notes')
    const state = useChatStore.getState()
    expect(state.open).toBe(true)
    expect(state.session).toEqual({ id: 21, publicId: 'uuid-21' })
    expect(state.viewerAsks[12]).toEqual({ id: 21, publicId: 'uuid-21' })
    expect(state.pendingSend).toEqual({
      content: 'Summarize this',
      attachments: [{ kind: 'material', id: 12 }],
      mode: 'send',
    })
  })

  test('second ask for the same material reuses the pinned session', async () => {
    useChatStore.getState().setViewerAsk(12, { id: 21, publicId: 'uuid-21' })
    await askMaterial({
      material: { id: 12, course_id: 3, title: 'Lecture notes' },
      content: 'And the examples?',
      mode: 'send',
    })
    expect(createChatSession).not.toHaveBeenCalled()
    expect(useChatStore.getState().session).toEqual({ id: 21, publicId: 'uuid-21' })
    expect(useChatStore.getState().pendingSend?.content).toBe('And the examples?')
  })

  test('a selection is embedded as a capped markdown quote above the question', async () => {
    useChatStore.getState().setViewerAsk(12, { id: 21, publicId: 'uuid-21' })
    await askMaterial({
      material: { id: 12, course_id: 3, title: 'Lecture notes' },
      content: 'What does this mean?',
      selection: 'first line\nsecond line',
      mode: 'prefill',
    })
    expect(useChatStore.getState().pendingSend?.content).toBe(
      '> first line\n> second line\n\nWhat does this mean?',
    )
  })

  test('quizMe patches the session before the send is queued', async () => {
    createChatSession.mockResolvedValue({
      id: 21,
      public_id: 'uuid-21',
      course_id: 3,
      title: 'Lecture notes',
    })
    updateChatSessionQuizme.mockResolvedValue({ id: 21, quizme: true })
    const order: string[] = []
    createChatSession.mockImplementation(async () => {
      order.push('create')
      return { id: 21, public_id: 'uuid-21', course_id: 3, title: 'Lecture notes' }
    })
    updateChatSessionQuizme.mockImplementation(async () => {
      order.push('quizme')
      return { id: 21, quizme: true }
    })
    const ref = await askMaterial({
      material: { id: 12, course_id: 3, title: 'Lecture notes' },
      content: 'Quiz me on this material.',
      mode: 'send',
      quizMe: true,
    })
    expect(ref).toEqual({ id: 21, publicId: 'uuid-21' })
    expect(updateChatSessionQuizme).toHaveBeenCalledWith(21, true)
    expect(order).toEqual(['create', 'quizme'])
    expect(useChatStore.getState().pendingSend).not.toBeNull()
  })
})

describe('askMaterials', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resetStore()
  })

  const materials = [
    { id: 12, course_id: 3, title: 'Lecture notes' },
    { id: 7, course_id: 3, title: 'Problem set' },
  ]

  test('first ask creates one session, pins it per selection and attaches every material', async () => {
    createChatSession.mockResolvedValue({
      id: 31,
      public_id: 'uuid-31',
      course_id: 3,
      title: '2 materials',
    })
    await askMaterials({ materials, title: '2 materials', content: 'Compare them' })
    expect(createChatSession).toHaveBeenCalledTimes(1)
    expect(createChatSession).toHaveBeenCalledWith(3, null, '2 materials')
    const state = useChatStore.getState()
    expect(state.open).toBe(true)
    expect(state.session).toEqual({ id: 31, publicId: 'uuid-31' })
    expect(state.selectionAsks['7-12']).toEqual({ id: 31, publicId: 'uuid-31' })
    expect(state.pendingSend).toEqual({
      content: 'Compare them',
      attachments: [
        { kind: 'material', id: 12, title: 'Lecture notes' },
        { kind: 'material', id: 7, title: 'Problem set' },
      ],
      mode: 'send',
    })
  })

  test('re-asking the same selection in any order reuses the pinned session', async () => {
    useChatStore.getState().setSelectionAsk('7-12', { id: 31, publicId: 'uuid-31' })
    await askMaterials({
      materials: [...materials].reverse(),
      title: 'ignored',
      content: 'Again',
    })
    expect(createChatSession).not.toHaveBeenCalled()
    expect(useChatStore.getState().session).toEqual({ id: 31, publicId: 'uuid-31' })
  })

  test('quizMe patches the pinned session before queueing the send', async () => {
    updateChatSessionQuizme.mockResolvedValue({ id: 31, quizme: true })
    const order: string[] = []
    createChatSession.mockImplementation(async () => {
      order.push('create')
      return { id: 31, public_id: 'uuid-31', course_id: 3, title: '2 materials' }
    })
    updateChatSessionQuizme.mockImplementation(async () => {
      order.push('quizme')
      return { id: 31, quizme: true }
    })
    await askMaterials({ materials, title: '2 materials', content: 'Quiz us', quizMe: true })
    expect(order).toEqual(['create', 'quizme'])
    expect(updateChatSessionQuizme).toHaveBeenCalledWith(31, true)
    expect(useChatStore.getState().pendingSend).not.toBeNull()
  })

  test('selectionAskKey is order-insensitive', () => {
    expect(selectionAskKey([12, 7])).toBe(selectionAskKey([7, 12]))
    expect(selectionAskKey([12, 7])).toBe('7-12')
  })

  test('rejects an empty material list', async () => {
    await expect(
      askMaterials({ materials: [], title: 'x', content: 'y' }),
    ).rejects.toThrow('at least one material')
  })
})

describe('quoteSelection', () => {
  test('prefixes every line as a blockquote', () => {
    expect(quoteSelection('a\nb')).toBe('> a\n> b')
  })

  test('caps long selections with an honest truncation marker', () => {
    const long = 'x'.repeat(1600)
    const quoted = quoteSelection(long)
    expect(quoted.startsWith(`> ${'x'.repeat(1500)}`)).toBe(true)
    expect(quoted.endsWith('\n> […]')).toBe(true)
  })
})
