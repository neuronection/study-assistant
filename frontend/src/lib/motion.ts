import { useReducedMotion } from 'framer-motion'
import type { Transition, Variants } from 'framer-motion'

const OVERLAY_SPRING: Transition = { type: 'spring', stiffness: 380, damping: 32 }
const FADE: Transition = { duration: 0.15, ease: 'easeOut' }
const STEP: Transition = { duration: 0.18, ease: 'easeOut' }
const ROUTE_FADE: Transition = { duration: 0.12, ease: 'easeOut' }
const INSTANT: Transition = { duration: 0 }

export function useMotionPresets() {
  const reduced = useReducedMotion() ?? false
  const overlaySpring: Transition = reduced ? INSTANT : OVERLAY_SPRING
  const fade: Transition = reduced ? INSTANT : FADE
  const step: Transition = reduced ? INSTANT : STEP
  const routeFade: Transition = reduced ? INSTANT : ROUTE_FADE
  return {
    reduced,
    backdrop: {
      initial: { opacity: 0 },
      animate: { opacity: 1 },
      exit: { opacity: 0 },
      transition: fade,
    },
    panel: {
      initial: { opacity: 0, y: -8, scale: 0.98 },
      animate: { opacity: 1, y: 0, scale: 1 },
      exit: { opacity: 0, y: -4, scale: 0.98 },
      transition: overlaySpring,
    },
    route: {
      initial: { opacity: 0, y: 6 },
      animate: { opacity: 1, y: 0 },
      exit: { opacity: 0 },
      transition: routeFade,
    },
    collapse: {
      initial: { height: 0, opacity: 0 },
      animate: { height: 'auto', opacity: 1 },
      exit: { height: 0, opacity: 0 },
      transition: fade,
    },
    step: {
      initial: { opacity: 0, x: 24 },
      animate: { opacity: 1, x: 0 },
      exit: { opacity: 0, x: -24 },
      transition: step,
    },
    enter: {
      initial: { opacity: 0, y: 8 },
      animate: { opacity: 1, y: 0 },
      transition: fade,
    },
    staggeredRows: (stagger = 0.015): Variants => ({
      hidden: {},
      show: { transition: { staggerChildren: reduced ? 0 : stagger } },
    }),
    row: {
      hidden: { opacity: 0, y: 4 },
      show: { opacity: 1, y: 0, transition: fade },
      exit: { opacity: 0, scale: 0.95, transition: fade },
    } satisfies Variants,
  }
}
