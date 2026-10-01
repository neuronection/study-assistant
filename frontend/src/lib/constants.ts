export const WsTopic = {
  jobs: (jobId: number): string => `jobs:${jobId}`,
  chat: (sessionId: number): string => `chat:${sessionId}`,
  source: (sourceId: number): string => `source:${sourceId}`,
  note: (noteId: number): string => `note:${noteId}`,
  material: (materialId: number): string => `material:${materialId}`,
} as const

export const storageKeys = {
  locale: 'sa-locale',
  profileId: 'sa-profile-id',
  onboardingDone: 'sa-onboarding-done',
  courseId: 'sa-course-id',
  quizShuffle: 'sa-quiz-shuffle',
  chatReasoningOpen: 'sa-chat-reasoning-open',
  chatWidth: 'sa-chat-width',
  fileWidth: 'sa-file-width',
  focusFullscreen: 'sa-focus-fullscreen',
  libraryView: 'sa-library-view',
  materialsView: 'sa-materials-view',
  notesView: 'sa-notes-view',
  practiceView: 'sa-practice-view',
  plannerView: 'sa-planner-view',
  reviewNudges: 'sa-review-nudges',
  notificationsSeen: 'sa-notifications-seen',
  recentNodesPrefix: 'sa-recent-nodes',
  interfacePrefs: 'sa-interface-prefs',
  treeWidth: 'sa-tree-width',
} as const
