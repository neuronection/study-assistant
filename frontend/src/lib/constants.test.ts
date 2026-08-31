import { describe, expect, test } from 'vitest'

import { storageKeys, WsTopic } from './constants'

describe('WsTopic', () => {
  test('topic builders mirror the backend WsTopic factories', () => {
    expect(WsTopic.jobs(3)).toBe('jobs:3')
    expect(WsTopic.chat(9)).toBe('chat:9')
    expect(WsTopic.source(1)).toBe('source:1')
    expect(WsTopic.note(2)).toBe('note:2')
    expect(WsTopic.material(4)).toBe('material:4')
  })

  test('storage keys keep the ca- prefix and stay unique', () => {
    const values = Object.values(storageKeys)
    for (const value of values) {
      expect(value.startsWith('ca-')).toBe(true)
    }
    expect(new Set(values).size).toBe(values.length)
  })
})
