export const ACTIVATION_EVENTS = [
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
] as const

export type ActivationEvent = (typeof ACTIVATION_EVENTS)[number]

export const ACTIVATION_STEPS = [
  'complete',
  'materials',
  'review',
  'exam',
  'practice',
  'provider',
  'library-split-view',
  'review-buttons',
  'practice-segments',
] as const

export type ActivationStep = (typeof ACTIVATION_STEPS)[number]

export const ACTIVATION_SURFACES = [
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
] as const

export type ActivationSurface = (typeof ACTIVATION_SURFACES)[number]

export interface ActivationProps {
  schema_version?: 1
  step?: ActivationStep
  surface?: ActivationSurface
  value?: number
}
