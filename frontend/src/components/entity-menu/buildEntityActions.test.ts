import { describe, expect, test, vi } from 'vitest'
import type { TFunction } from 'i18next'

import { buildEntityActions } from './buildEntityActions'
import type { EntityActionHandlers, NodeSource } from './types'

const t = ((key: string) => key) as unknown as TFunction

function makeSource(overrides: Partial<NodeSource<unknown>> = {}): NodeSource<unknown> {
  return {
    kind: 'test',
    toEntity: () => ({ id: '1', label: 'Node' }),
    toContext: () => ({ courseId: 3, scopeNodeId: 5 }),
    ...overrides,
  }
}

function makeHandlers(overrides: Partial<EntityActionHandlers> = {}): EntityActionHandlers {
  return {
    ask: vi.fn(),
    generate: vi.fn(),
    writeNote: vi.fn(),
    addNote: vi.fn(),
    addAsSection: vi.fn(),
    editNode: vi.fn(),
    addChild: vi.fn(),
    removeNode: vi.fn(),
    ...overrides,
  }
}

describe('buildEntityActions', () => {
  test('always includes generate and integrate actions', () => {
    const groups = buildEntityActions(makeSource(), 'node', makeHandlers(), t)
    const keys = groups.flatMap((group) => group.actions.map((action) => action.key))
    expect(keys).toEqual([
      'ask',
      'quiz',
      'exercise',
      'flashcards',
      'studyGuide',
      'writeNote',
      'addNote',
      'addAsSection',
    ])
  })

  test('gates aiEdit and integrate extras on source/handler capabilities', () => {
    const withAi = buildEntityActions(
      makeSource({ canAiEdit: true }),
      'node',
      makeHandlers({ aiEdit: vi.fn(), addAsSection: undefined }),
      t
    )
    const keys = withAi.flatMap((group) => group.actions.map((action) => action.key))
    expect(keys).toContain('aiEdit')
    expect(keys).not.toContain('addAsSection')

    const withoutAi = buildEntityActions(
      makeSource({ canAiEdit: true }),
      'node',
      makeHandlers(),
      t
    )
    expect(
      withoutAi.flatMap((group) => group.actions.map((action) => action.key))
    ).not.toContain('aiEdit')
  })

  test('includes edit actions only when the source supports them', () => {
    const noCrud = buildEntityActions(makeSource(), 'node', makeHandlers(), t)
    expect(noCrud.flatMap((g) => g.actions.map((a) => a.key))).not.toContain('edit')

    const crud = buildEntityActions(
      makeSource({
        canEdit: true,
        edit: vi.fn(),
        canRemove: true,
        remove: vi.fn(),
        canAddChild: true,
        addChild: vi.fn(),
      }),
      'node',
      makeHandlers(),
      t
    )
    const keys = crud.flatMap((group) => group.actions.map((action) => action.key))
    expect(keys).toContain('addChild')
    expect(keys).toContain('edit')
    expect(keys).toContain('remove')
  })

  test('invokes generate with the resolved entity, context, and hint', () => {
    const handlers = makeHandlers()
    const source = makeSource({ llmHint: () => 'FULL MAP' })
    const groups = buildEntityActions(source, 'node', handlers, t)
    const quiz = groups[0].actions.find((action) => action.key === 'quiz')
    quiz?.onSelect()
    expect(handlers.generate).toHaveBeenCalledWith(
      'quiz',
      { id: '1', label: 'Node' },
      { courseId: 3, scopeNodeId: 5 },
      'FULL MAP'
    )
  })
})
