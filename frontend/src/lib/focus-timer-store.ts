import { create } from 'zustand'

import {
  beatStudySession,
  startStudySession,
  type StudySessionKind,
} from '@/lib/api'

export interface FocusPreset {
  key: string
  focusMin: number
  breakMin: number
}

export const FOCUS_PRESETS: FocusPreset[] = [
  { key: '25/5', focusMin: 25, breakMin: 5 },
  { key: '50/10', focusMin: 50, breakMin: 10 },
]

export type FocusTimerPhase = 'idle' | 'focus' | 'break' | 'paused' | 'done'

interface FocusTimerState {
  phase: FocusTimerPhase
  presetKey: string
  focusMin: number
  breakMin: number
  /** Monotonic-ish anchor: epoch ms when the current stretch ends (running) or the frozen remainder (paused). */
  endsAt: number
  remainingSec: number
  sessionId: number | null
  startedAtSec: number
  lastContext: { courseId: number | null; nodeId: number | null }
  start: (preset: FocusPreset, context: { courseId: number | null; nodeId: number | null }) => void
  startCustom: (focusMin: number, breakMin: number, context: { courseId: number | null; nodeId: number | null }) => void
  pause: () => void
  resume: () => void
  giveUp: () => void
  tick: () => void
  beginBreak: () => void
  dismiss: () => void
}

function logSession(
  state: FocusTimerState,
  action: 'start' | 'end',
  context: { courseId: number | null; nodeId: number | null }
): void {
  const kind: StudySessionKind = 'focus'
  if (action === 'start') {
    void startStudySession({
      kind,
      source: 'timer',
      course_id: context.courseId,
      node_id: context.nodeId,
    })
      .then((row) => {
        useFocusTimerStore.setState({ sessionId: row.id, startedAtSec: Math.floor(Date.now() / 1000) })
      })
      .catch(() => {})
    return
  }
  if (state.sessionId !== null) {
    const id = state.sessionId
    useFocusTimerStore.setState({ sessionId: null })
    void beatStudySession(id, 'end').catch(() => {})
  }
}

function initialRemaining(focusMin: number): number {
  return Math.max(60, Math.round(focusMin * 60))
}

export const useFocusTimerStore = create<FocusTimerState>((set, get) => ({
  phase: 'idle',
  presetKey: FOCUS_PRESETS[0].key,
  focusMin: FOCUS_PRESETS[0].focusMin,
  breakMin: FOCUS_PRESETS[0].breakMin,
  endsAt: 0,
  remainingSec: 0,
  sessionId: null,
  startedAtSec: 0,
  lastContext: { courseId: null, nodeId: null },
  start: (preset, context) => {
    set({
      lastContext: context,
      phase: 'focus',
      presetKey: preset.key,
      focusMin: preset.focusMin,
      breakMin: preset.breakMin,
      remainingSec: initialRemaining(preset.focusMin),
      endsAt: Date.now() + initialRemaining(preset.focusMin) * 1000,
    })
    logSession(get(), 'start', context)
  },
  startCustom: (focusMin, breakMin, context) => {
    get().start({ key: 'custom', focusMin, breakMin }, context)
  },
  pause: () => {
    const { phase, endsAt } = get()
    if (phase !== 'focus') {
      return
    }
    set({ phase: 'paused', remainingSec: Math.max(0, Math.round((endsAt - Date.now()) / 1000)) })
    logSession(get(), 'end', { courseId: null, nodeId: null })
  },
  resume: () => {
    const { phase, remainingSec } = get()
    if (phase !== 'paused') {
      return
    }
    set({ phase: 'focus', endsAt: Date.now() + remainingSec * 1000 })
    logSession(get(), 'start', get().lastContext)
  },
  giveUp: () => {
    const { phase } = get()
    if (phase === 'idle') {
      return
    }
    logSession(get(), 'end', { courseId: null, nodeId: null })
    set({ phase: 'idle', remainingSec: 0, endsAt: 0 })
  },
  tick: () => {
    const { phase, endsAt } = get()
    if (phase !== 'focus' && phase !== 'break') {
      return
    }
    const remainingSec = Math.max(0, Math.round((endsAt - Date.now()) / 1000))
    if (remainingSec <= 0) {
      if (phase === 'focus') {
        logSession(get(), 'end', { courseId: null, nodeId: null })
        set({ phase: 'done', remainingSec: 0 })
      } else {
        set({ phase: 'idle', remainingSec: 0, endsAt: 0 })
      }
      return
    }
    set({ remainingSec })
  },
  beginBreak: () => {
    const { breakMin } = get()
    set({
      phase: 'break',
      remainingSec: Math.max(60, Math.round(breakMin * 60)),
      endsAt: Date.now() + Math.max(60, Math.round(breakMin * 60)) * 1000,
    })
  },
  dismiss: () => {
    set({ phase: 'idle', remainingSec: 0, endsAt: 0 })
  },
}))

export function formatFocusRemaining(totalSec: number): string {
  const minutes = Math.floor(totalSec / 60)
  const seconds = totalSec % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}
