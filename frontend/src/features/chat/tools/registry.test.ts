import { describe, expect, test } from 'vitest'

import i18next from 'i18next'

import { formatDuration, getToolMeta, getToolView, toolCardProps } from './registry'

const t = i18next.t.bind(i18next)

describe('tool registry', () => {
  test('resolves known tool metadata', () => {
    expect(getToolMeta('CALC').labelKey).toBe('chat.tool.calc')
    expect(getToolMeta('SYMPY').labelKey).toBe('chat.tool.sympy')
    expect(getToolMeta('READ').labelKey).toBe('chat.tool.read')
    expect(getToolMeta('STATE').labelKey).toBe('chat.tool.state')
    expect(getToolMeta('PLOT').labelKey).toBe('chat.tool.plot')
  })

  test('falls back to a generic meta for unknown tools', () => {
    const meta = getToolMeta('SOMETHING_ELSE')
    expect(meta.labelKey).toBeNull()
    expect(meta.phase).toBe('computing')
  })

  test('every tool has a view renderer', () => {
    for (const name of ['CALC', 'SYMPY', 'READ', 'STATE', 'PLOT', 'UNKNOWN']) {
      expect(typeof getToolView(name)).toBe('function')
    }
  })
})

describe('toolCardProps (plan 12 §6: registry feeds the library card)', () => {
  test('maps summary, duration, icon and translated labels', () => {
    const props = toolCardProps(
      {
        name: 'READ',
        argument: 'M12',
        phase: 'read',
        title: 'Lecture 3',
        result: 'read 1234 chars',
        status: 'done',
        start_ms: null,
        duration_ms: 1400,
      },
      t,
    )
    expect(props.name).toBe('READ')
    expect(props.title).toBe('Lecture 3')
    expect(props.status).toBe('done')
    expect(props.args).toBe('M12')
    expect(props.result).toBe('read 1234 chars')
    expect(props.durationMs).toBe(1400)
    expect(props.defaultOpen).toBe(false)
    expect(props.labels?.args).toBe('Argument')
    expect(props.labels?.result).toBe('Result')
    expect(props.renderResult).toBeTypeOf('function')
  })

  test('normalizes missing statuses from the result presence', () => {
    const done = toolCardProps(
      { name: 'CALC', argument: '1+1', phase: null, status: null, result: '2' },
      t,
    )
    const running = toolCardProps(
      { name: 'CALC', argument: '1+1', phase: null, status: null, result: null },
      t,
    )
    const failed = toolCardProps(
      { name: 'CALC', argument: '1+1', phase: null, status: 'failed', result: null },
      t,
    )
    expect(done.status).toBe('done')
    expect(running.status).toBe('running')
    expect(failed.status).toBe('failed')
  })

  test('falls back to the argument as header summary', () => {
    const props = toolCardProps(
      { name: 'CALC', argument: 'sin(pi/6)', phase: 'math', status: 'done', result: '0.5' },
      t,
    )
    expect(props.title).toBe('sin(pi/6)')
    expect(props.icon).toBe(getToolMeta('CALC').icon)
  })

  test('only QUIZ cards open by default', () => {
    const quiz = toolCardProps(
      { name: 'QUIZ', argument: 'q', phase: 'read', status: 'done', result: 'r' },
      t,
    )
    const read = toolCardProps(
      { name: 'READ', argument: 'M12', phase: 'read', status: 'done', result: 'r' },
      t,
    )
    expect(quiz.defaultOpen).toBe(true)
    expect(read.defaultOpen).toBe(false)
  })
})

describe('formatDuration', () => {
  test('formats sub-second durations in milliseconds', () => {
    expect(formatDuration(0)).toBe('0 ms')
    expect(formatDuration(500)).toBe('500 ms')
    expect(formatDuration(999)).toBe('999 ms')
  })

  test('formats seconds with one decimal below ten seconds', () => {
    expect(formatDuration(1000)).toBe('1.0 s')
    expect(formatDuration(2500)).toBe('2.5 s')
    expect(formatDuration(9999)).toBe('10.0 s')
  })

  test('formats whole seconds above ten seconds', () => {
    expect(formatDuration(12_000)).toBe('12 s')
  })

  test('returns null for missing values', () => {
    expect(formatDuration(null)).toBeNull()
    expect(formatDuration(undefined)).toBeNull()
  })
})
