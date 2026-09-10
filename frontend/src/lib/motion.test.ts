import { renderHook } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

let reducedMotion = false

vi.mock('framer-motion', async (importOriginal) => {
  const actual = await importOriginal<typeof import('framer-motion')>()
  return {
    ...actual,
    useReducedMotion: () => reducedMotion,
  }
})

const { useMotionPresets } = await import('./motion')

describe('useMotionPresets', () => {
  test('full motion: panel uses the overlay spring, rows stagger', () => {
    reducedMotion = false
    const { result } = renderHook(() => useMotionPresets())
    expect(result.current.reduced).toBe(false)
    expect(result.current.panel.transition).toEqual({
      type: 'spring',
      stiffness: 380,
      damping: 32,
    })
    expect(result.current.backdrop.transition).toEqual({
      duration: 0.15,
      ease: 'easeOut',
    })
    expect(result.current.route.transition).toEqual({
      duration: 0.12,
      ease: 'easeOut',
    })
    expect(result.current.step.transition).toEqual({
      duration: 0.18,
      ease: 'easeOut',
    })
    expect(result.current.collapse.animate).toEqual({ height: 'auto', opacity: 1 })
    expect(result.current.enter.animate).toEqual({ opacity: 1, y: 0 })
    expect(result.current.staggeredRows().show).toMatchObject({
      transition: { staggerChildren: 0.015 },
    })
  })

  test('rows carry an exit for AnimatePresence removal', () => {
    reducedMotion = false
    const { result } = renderHook(() => useMotionPresets())
    expect(result.current.row.exit).toMatchObject({ opacity: 0, scale: 0.95 })
  })

  test('reduced motion: every transition is instant and stagger collapses', () => {
    reducedMotion = true
    const { result } = renderHook(() => useMotionPresets())
    expect(result.current.reduced).toBe(true)
    expect(result.current.panel.transition).toEqual({ duration: 0 })
    expect(result.current.backdrop.transition).toEqual({ duration: 0 })
    expect(result.current.route.transition).toEqual({ duration: 0 })
    expect(result.current.step.transition).toEqual({ duration: 0 })
    expect(result.current.row.show.transition).toEqual({ duration: 0 })
    expect(result.current.row.exit.transition).toEqual({ duration: 0 })
    expect(result.current.staggeredRows().show).toMatchObject({
      transition: { staggerChildren: 0 },
    })
  })
})
