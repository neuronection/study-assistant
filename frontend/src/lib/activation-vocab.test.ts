import { describe, expect, test } from 'vitest'

import {
  ACTIVATION_EVENTS,
  ACTIVATION_STEPS,
  ACTIVATION_SURFACES,
} from './activation-vocab'

const SHIPPED_EVENTS = [
  'onboarding_step',
  'first_file_ingested',
  'first_review',
  'first_quiz',
  'first_ai_call',
  'first_capture',
  'update_installed',
  'highlight_to_card',
  'brief_played_50pct',
  'solve_completed',
  'paper_sat',
  'device_linked',
  'feature_opened',
  'tip_dismissed',
]

const SHIPPED_STEPS = [
  'complete',
  'materials',
  'review',
  'exam',
  'practice',
  'provider',
  'library-split-view',
  'review-buttons',
  'practice-segments',
]

const SHIPPED_SURFACES = [
  'home',
  'course',
  'review',
  'quiz',
  'quick_capture',
  'problem_desk',
  'lecture_moment',
  'lecture_moment_batch',
  'home_coach',
  'one_time_tip',
]

describe('activation vocabulary', () => {
  test('mirrors the backend event vocabulary', () => {
    expect([...ACTIVATION_EVENTS]).toEqual(SHIPPED_EVENTS)
  })

  test('mirrors every shipped step literal', () => {
    expect([...ACTIVATION_STEPS]).toEqual(SHIPPED_STEPS)
  })

  test('mirrors every shipped surface literal', () => {
    expect([...ACTIVATION_SURFACES]).toEqual(SHIPPED_SURFACES)
  })

  test('has no duplicate members', () => {
    for (const values of [ACTIVATION_EVENTS, ACTIVATION_STEPS, ACTIVATION_SURFACES]) {
      expect(new Set(values).size).toBe(values.length)
    }
  })
})
