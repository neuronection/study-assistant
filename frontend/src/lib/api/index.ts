export type {
  AiContextPreview,
  AiToolArgument,
  AiToolInfo,
  EditorTransformJobOut,
  EditorTransformJobState,
  EditorTransformJobStatus,
  EditorTransformMode,
  EditorTransformRequest,
  GenerateContext,
  GenerateScope,
  McpInfo,
  McpToolInfo,
  TranscriptionResult,
} from './ai'

export {
  cancelEditorTransformJob,
  contextVars,
  getEditorTransformJob,
  listAiTools,
  listMcpInfo,
  previewAiContext,
  speakText,
  startEditorTransform,
  transcribeAudio,
} from './ai'

export type {
  CostsSummary,
  DailyEntry,
  Diagnostics,
  ErrorTagProfile,
  ExamStatusEntry,
  ItemStat,
  MatrixCell,
  Overview,
  Recommendation,
  SpeedAccuracyEntry,
  TaskCost,
} from './analytics'

export {
  getCosts,
  getDiagnostics,
  analyticsExportUrl,
  getExamStatus,
  getItems,
  getOverview,
  getRecommendations,
  setDailyGoal,
} from './analytics'

export {
  beatStudySession,
  getStudySessionSummary,
  startStudySession,
} from './study-sessions'

export type {
  StudySessionDay,
  StudySessionInfo,
  StudySessionKind,
  StudySessionSource,
  StudySessionSummary,
} from './study-sessions'

export { planIcsUrl } from './plan'

export { getReviewDue } from './review'

export type { DueCourseGroup, ReviewDue } from './review'

export { getNotifications } from './notifications'

export { getStudyNext } from './study'

export type {
  StudyNext,
  StudyPlanRow,
  StudyWeakCell,
} from './study'

export type {
  DueReviewEntry,
  ExamEntry,
  Notifications,
  PlanEntry,
} from './notifications'

export type {
  ChatAttachmentInput,
  ChatAttachmentKind,
  ChatBranchNode,
  ChatBranchTree,
  ChatCitation,
  ChatContextData,
  ChatMessage,
  ChatProposal,
  ChatRead,
  ChatSession,
  ChatToolCall,
  ChatTrace,
  ChatTraceRound,
  MentionKind,
  MentionRef,
} from './chat'

export {
  answerQuizQuestion,
    approveChatProposal,
  askAboutExerciseSession,
  askAboutQuestion,
  createChatSession,
  deleteChatSession,
  dismissChatProposal,
  editChatMessage,
  getChatBranchTree,
  getChatContext,
  listChatMessages,
  listChatSessions,
  patchChatMessageState,
  regenerateChatMessage,
  renameChatSession,
  selectChatVariant,
  sendChatMessage,
  stopChatTurn,
  updateChatSessionEmbeddings,
  updateChatSessionQuizme,
} from './chat'

export type {
  AdminUser,
  AdminUserPatch,
  InstanceAuthMode,
  PublicUser,
  UserSession,
} from './admin'

export {
  changeMyPassword,
  deleteMyAccount,
  forceLogoutUser,
  listAdminUsers,
  listMySessions,
  patchAdminUser,
  resetAdminUserPassword,
  revokeMySession,
  updateInstanceMode,
} from './admin'

export {
  ApiError,
  apiDetailMessage,
  apiFetch,
  blobUrl,
  getActiveProfile,
  markProfileSettled,
  setActiveProfile,
  unsupportedTypeDetail,
} from './client'

export type { InstanceConfig } from './instance'

export { getInstanceConfig } from './instance'

export type {
  AllocationInfo,
  ConceptDraft,
  ConceptDraftEntry,
  ConceptGraph,
  ConceptLinkDraft,
  ConceptNode,
  ConceptNodeDraft,
  Course,
  CourseBundlePreview,
  CourseDefaultTaskInfo,
  CourseDuplicate,
  CourseTaskInfo,
  CourseTypeInfo,
  GenesisCommitResult,
  GenesisDraft,
  NodeArtifacts,
  NodeCounts,
  NodeDetail,
  NodeFolderLink,
  NodeInfo,
  NodeReview,
  NodeWorkspace,
  OrganizerFinding,
  OutlineDraft,
  OutlineDraftChapter,
  OutlineDraftSection,
  ScopeCounts,
  WorkspaceChild,
  WorkspaceFolder,
  WorkspaceMaterial,
  WorkspaceNote,
} from './courses'

export {
  addNode,
  addNodeConcept,
  assignCourseTask,
  assignCourseTaskDefault,
  commitConcepts,
  conceptGraph,
  courseExportUrl,
  courseTree,
  createCourse,
  createCourseType,
  createGenesisCourse,
  deleteCourse,
  deleteNode,
  draftGenesis,
  duplicateCourse,
  draftNodeNote,
  extractConcepts,
  getCourse,
  getNode,
  getNodeArtifacts,
  getScratchpad,
  importCourseBundle,
  listCourseTaskDefaults,
  listCourseTasks,
  listCourseTypes,
  listCourses,
  listStudyStates,
  moveNode,
  nodeWorkspace,
  outlineCommit,
  outlineDraft,
  promoteNode,
  removeNodeConcept,
  renameNode,
  restoreNode,
  reviewNode,
  setStudyState,
  updateCourse,
  updateNode,
} from './courses'

export type {
  DrillPattern,
  ExerciseInfo,
  ExerciseSessionInfo,
  ExerciseStepInfo,
  ExerciseStepInput,
  HintResult,
  PatternProposal,
  StepCheck,
} from './exercises'

export {
  createExercise,
  createTeachBack,
  createPattern,
  deleteExercise,
  drillPatterns,
  exerciseSteps,
  generateExercise,
  getExercise,
  listExercises,
  moveExercise,
  proposePatterns,
  renameExercise,
  requestHint,
  similarExercise,
  startDrill,
  startExerciseSession,
  submitStepAnswer,
} from './exercises'

export type {
  FlashcardInfo,
  ReviewResult,
} from './flashcards'

export {
  ankiExportUrl,
  dueFlashcards,
  generateFlashcards,
  importAnkiDeck,
  listFlashcards,
  reviewFlashcard,
} from './flashcards'

export type {
  Folder,
  FolderDeleteInfo,
  FolderDeleteInfoNodeLink,
  FolderLinkInfo,
} from './folders'

export {
  createFolder,
  deleteFolder,
  getFolderDeleteInfo,
  getFolderLinks,
  listFolders,
  moveFolder,
  renameFolder,
  unlinkFolder,
} from './folders'

export type {
  JobInfo,
  JobTypeInfo,
  JobsSummary,
} from './jobs'

export {
  cancelJob,
  deleteFailedJobs,
  deleteJob,
  getJob,
  getJobsSummary,
  listJobTypes,
  listJobs,
  retryFailedJobs,
  retryJob,
} from './jobs'

export type {
  AcceptedTypes,
  BlockDto,
  ComposeKind,
  ComposedMaterial,
  CourseMaterialLink,
  Extraction,
  ExtractionDiffInfo,
  ExtractionVersionInfo,
  IndexCard,
  LinkMaterialBody,
  Material,
  MaterialDetail,
  MaterialLinkInfo,
  MindmapEditResult,
  PendingDrawing,
  PlacementCandidate,
  PlacementSuggestion,
  SearchHitDto,
  TextFileEditState,
  UploadResult,
  WorkspaceConcept,
} from './materials'

export {
  COMPOSE_KINDS,
  addMaterialDrawing,
  getAcceptedTypes,
  allocateMaterial,
  allocateNodeFolder,
  assignCourseMaterial,
  mirrorFolder,
  composeMaterial,
  composeMaterialAsync,
  createLinkMaterial,
  parseLinkMaterial,
  transcribeLinkAudio,
  copyMaterial,
  createTextFile,
  createTextMaterial,
  downloadBibliography,
  deallocateMaterial,
  deallocateNodeFolder,
  deleteMaterial,
  deleteMaterialDrawing,
  deriveMaterial,
  deriveMaterials,
  editExtraction,
  diffExtractionVersions,
  getExtractionVersion,
  getMaterial,
  getMaterialLinks,
  getUnassignedMaterials,
  getPlacementSuggestions,
  listCourseMaterials,
  listExtractionVersions,
  listMaterials,
  importBibliography,
  importUrlMaterial,
  mindmapEdit,
  moveMaterial,
  patchMaterial,
  reingestMaterial,
  remapDrawingRefsInMarkdown,
  renameMaterial,
  reocrMaterialDrawing,
  search,
  setMaterialDescription,
  unassignCourseMaterial,
  updateMaterialDrawing,
  updateTextMaterial,
  uploadMaterial,
} from './materials'

export type {
  NoteActionResult,
  NoteLinkInfo,
  NoteLinksInfo,
  NoteDetailInfo,
  NoteDrawingInfo,
  NoteInfo,
  NoteTagSummary,
  NoteVersionDetailInfo,
  NoteVersionDiffInfo,
  NoteVersionInfo,
  NotesPage,
} from './notes'

export {
  createPlanItem,
  deletePlanItem,
  generatePlan,
  importIcs,
  listPlanItems,
  listUpcomingItems,
  previewIcsImport,
  updatePlanItem,
} from './plan'

export type {
  IcsImportResult,
  IcsPreview,
  PlanItem,
  PlanItemKind,
  UpcomingItem,
} from './plan'

export {
  addDrawing,
  composeNote,
  createNote,
  deleteDrawing,
  deleteNote,
  diffNoteVersions,
  getNote,
  getNoteVersion,
  listNoteLinks,
  listNoteTags,
  listNoteVersions,
  listNotes,
  moveNote,
  reocrDrawing,
  restoreNoteVersion,
  vaultExportUrl,
  runNoteAction,
  saveSessionSummaryNote,
  updateDrawing,
  updateNote,
} from './notes'

export type {
  ImportResult,
  ImportValidation,
  MistakeRow,
  QuizActivity,
  QuizAnswerKeyEntry,
  QuizAttempt,
  QuizAttemptRow,
  QuizFeedback,
  QuizQuestion,
  RecognitionResult,
} from './quiz'

export {
  deleteQuiz,
  finishQuizAttempt,
  generateQuiz,
  getQuiz,
  importQpkg,
  importQuiz,
  listMistakes,
  listQuizAttempts,
  listQuizzes,
  moveQuiz,
  qpkgExportUrl,
  quizAnswerKey,
  quizExportUrl,
  quizQuestions,
  recognizeHandwriting,
  renameQuiz,
  requestQuizHint,
  setQuizTimeLimit,
  startQuizAttempt,
  submitQuizAnswer,
} from './quiz'

export type {
  AiModel,
  BackupEntryInfo,
  BackupRecoveryInfo,
  BackupSettingsInfo,
  BackupStatus,
  DefaultTaskInfo,
  LocalEngineHit,
  Provider,
  ProviderPreset,
  ProviderSetupErrorDetail,
  ProviderSetupOptions,
  ProviderSetupResult,
  RemoteModelInfo,
  SkillInfo,
  SkillVersionInfo,
  SkillPack,
  SkillPackCommit,
  SkillPackPreview,
  TaskInfo,
} from './settings'

export {
  activateSkillVersion,
  assignTask,
  assignTaskDefault,
  backupExportUrl,
  createBackupNow,
  createModel,
  createProvider,
  deleteBackup,
  deleteModel,
  deleteProvider,
  detectLocalEngines,
  discoverModels,
  getBackupStatus,
  listModels,
  listPresets,
  listProviders,
  listRemoteModels,
  listSkills,
  listTaskDefaults,
  listTasks,
  restoreBackup,
  restoreBackupByName,
  restoreSkillDefault,
  exportSkillPack,
  importSkillPackCommit,
  importSkillPackPreview,
  saveSkillVersion,
  setProviderDefault,
  setTaskBudget,
  setupErrorDetail,
  setupProviderPreset,
  skillResolution,
  skillTestRun,
  skillVersions,
  testProvider,
  updateBackupSettings,
  updateModel,
  updateProvider,
} from './settings'

export type {
  BrowseEntry,
  BrowseMaterial,
  BrowsePending,
  BrowseResult,
  InboxEntryInfo,
  LinkedSource,
  ScanResult,
} from './sources'

export {
  addSource,
  browseSource,
  deleteSource,
  importInboxFile,
  inboxPath,
  ingestSourceFile,
  listSources,
  relinkSource,
  revealSource,
  setSourceMirror,
  mirrorBackfillSource,
  scanInbox,
  scanSource,
} from './sources'

export type {
  DeletedItemInfo,
  DesktopFileEntry,
  DesktopFolderListing,
  DiscoveryPrefs,
  DiscoverySitePreset,
  FsDirEntry,
  FsDirs,
  Health,
  OnboardingState,
  ProfileInfo,
  ProfilePreferences,
  ProfilePreferencesUpdate,
  SearchProvider,
  SearchProviderCatalog,
  SearchProviderCatalogEntry,
  SearchProviderCatalogField,
  SearchProviderProbe,
  UpdateCheck,
  WorkingDirInfo,
  WorkingDirValidation,
} from './system'

export {
  createProfile,
  createSampleCourse,
  createSearchProvider,
  deleteProfile,
  deleteSearchProvider,
  desktopFileUrl,
  getHealth,
  getOnboardingState,
  getProfilePreferences,
  getSearchProviderCatalog,
  getUpdateCheck,
  getWorkingDir,
  listDeletedItems,
  listDesktopFolder,
  listFsDirs,
  listProfiles,
  listSearchProviders,
  moveSearchProvider,
  patchProfile,
  purgeDeletedItem,
  registerDesktopDrops,
  resetWorkingDir,
  restoreDeletedItem,
  setWorkingDir,
  testSearchProvider,
  updateProfilePreferences,
  updateSearchProvider,
  validateWorkingDir,
} from './system'

export type {
  CalendarCatalog,
  CalendarLink,
  CalendarLinkInput,
  CalendarOAuthStart,
  CalendarProvider,
  CalendarSetupField,
  CalendarSyncReport,
  DiscoveredCalendar,
} from './calendar'

export {
  completeCalendarOAuth,
  createCalendarLink,
  deleteCalendarLink,
  discoverCalendars,
  listCalendarLinks,
  listCalendarProviders,
  setCalendarLinkSecret,
  startCalendarOAuth,
  syncCalendarLink,
  testCalendarLink,
  updateCalendarLink,
} from './calendar'

export type {
  DiscoveryResultRow,
  DiscoverySearchResponse,
  DiscoverySuggestion,
  DiscoverySuggestionList,
} from './discovery'

export {
  deleteDiscoverySuggestion,
  listDiscoverySuggestions,
  patchDiscoverySuggestion,
  saveDiscoverySuggestion,
  searchDiscovery,
} from './discovery'

export type {
  ExternalSourceKind,
  ExternalSourceRow,
  SourceAcceptResult,
  SourceBackupUpload,
  SourceOAuthStatus,
  SourceProvider,
  SourceProviderCatalog,
  SourceRemoteBackup,
  SourceRemoteBackupList,
  SourceSecretStatus,
} from './external-sources'

export {
  acceptExternalSuggestion,
  connectExternalSource,
  createExternalSource,
  deleteExternalSource,
  deleteExternalSourceSecret,
  disconnectExternalSource,
  listExternalBackups,
  listExternalSources,
  listSourceProviders,
  restoreExternalBackup,
  scanExternalSource,
  setExternalSourceSecret,
  updateExternalSource,
  uploadExternalBackup,
} from './external-sources'

export type { ExtensionDocs } from './extensions'

export { getExtensionDocumentation } from './extensions'

export type { McpServerRow, McpServerToolInfo, McpCharter } from './mcp-servers'

export {
  createMcpServer,
  deleteMcpServer,
  getMcpCharter,
  listMcpServers,
  refreshMcpServer,
  updateMcpServer,
} from './mcp-servers'

export type { ExerciseOrderingItem } from './hand-types'
export { HAND_TYPE_REGISTER } from './hand-types'

export type {
  RetrievalAction,
  RetrievalCoverageEnvelope,
  RetrievalMaintenanceRequest,
  RetrievalOverview,
  RetrievalReindexRequest,
  RetrievalRuns,
  RetrievalSpaces,
} from './retrieval'

export {
  cancelRetrievalRun,
  getRetrievalCoverage,
  getRetrievalOverview,
  getRetrievalRuns,
  getRetrievalSpaces,
  postRetrievalMaintenance,
  postRetrievalReindex,
  retryRetrievalRun,
} from './retrieval'
