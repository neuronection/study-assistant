export const WsTopic = {
  jobs: (jobId: number): string => `jobs:${jobId}`,
  chat: (sessionId: number): string => `chat:${sessionId}`,
  source: (sourceId: number): string => `source:${sourceId}`,
  note: (noteId: number): string => `note:${noteId}`,
  material: (materialId: number): string => `material:${materialId}`,
} as const

export const storageKeys = {
  profileId: 'ca-profile-id',
  onboardingDone: 'ca-onboarding-done',
  courseId: 'ca-course-id',
  quizShuffle: 'ca-quiz-shuffle',
  chatReasoningOpen: 'ca-chat-reasoning-open',
  chatWidth: 'ca-chat-width',
  focusFullscreen: 'ca-focus-fullscreen',
  libraryView: 'ca-library-view',
  materialsView: 'ca-materials-view',
  notesView: 'ca-notes-view',
  practiceView: 'ca-practice-view',
  treeSidebarOpen: 'ca-tree-sidebar-open',
} as const
