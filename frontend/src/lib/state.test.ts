import { describe, expect, test } from 'vitest'

import { diffState } from './state'

describe('diffState', () => {
  test('produces add ops for new keys', () => {
    expect(diffState({}, { value: 3 })).toEqual([
      { op: 'add', path: '/value', value: 3 },
    ])
  })

  test('produces remove ops for dropped keys', () => {
    expect(diffState({ value: 3 }, {})).toEqual([{ op: 'remove', path: '/value' }])
  })

  test('produces replace ops for changed keys', () => {
    expect(diffState({ checked: ['a'] }, { checked: ['a', 'b'] })).toEqual([
      { op: 'replace', path: '/checked', value: ['a', 'b'] },
    ])
  })

  test('produces no ops when states are equal', () => {
    expect(diffState({ value: 3 }, { value: 3 })).toEqual([])
  })

  test('escapes pointer segments containing slashes and tildes', () => {
    expect(diffState({}, { 'a/b~c': 1 })).toEqual([
      { op: 'add', path: '/a~1b~0c', value: 1 },
    ])
  })
})
