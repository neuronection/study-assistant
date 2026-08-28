import {
  createRootRoute,
  createRoute,
  createRouter,
  redirect,
  useParams,
} from '@tanstack/react-router'

import { AppShell } from '@/components/layout/AppShell'
import { CourseDetailPage } from '@/features/courses/CourseDetailPage'
import { NodeWorkspace } from '@/features/courses/NodeWorkspace'
import { CoursesPage } from '@/features/courses/CoursesPage'
import { HomePage } from '@/features/home/HomePage'
import { LibraryPage } from '@/features/library/LibraryPage'
import { MaterialDetailPage } from '@/features/library/MaterialDetailPage'
import { ExercisePlayerRoute } from '@/features/exercises/Player'
import { NoteFocusPage } from '@/features/notes/NoteFocusPage'
import { ChatPage } from '@/features/chat/ChatPage'
import { QuizRunner } from '@/features/quiz/QuizRunner'
import { ScoresPage } from '@/features/scores/ScoresPage'
import { JobsPage } from '@/features/jobs/JobsPage'
import { SettingsPage } from '@/features/settings/SettingsPage'
import { SpikePage } from '@/features/spike/SpikePage'

const rootRoute = createRootRoute({
  component: () => <AppShell />,
})

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: () => <HomePage />,
})

const chatRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/chat',
  component: () => <ChatPage />,
})

const chatDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/chat/$chatId',
  component: () => <ChatPage />,
})

const coursesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/courses',
  component: () => <CoursesPage />,
})

function tabSearch(search: Record<string, unknown>): {
  tab?: string
  note?: number
  material?: number
  study?: number | 'new'
} {
  const rawStudy = search.study
  let study: number | 'new' | undefined
  if (rawStudy === 'new') {
    study = 'new'
  } else if (typeof rawStudy === 'number') {
    study = rawStudy
  } else if (typeof rawStudy === 'string' && /^\d+$/.test(rawStudy)) {
    study = Number(rawStudy)
  }
  return {
    tab: typeof search.tab === 'string' ? search.tab : undefined,
    note: typeof search.note === 'number' ? search.note : undefined,
    material: typeof search.material === 'number' ? search.material : undefined,
    study,
  }
}

const courseDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/courses/$courseId',
  validateSearch: tabSearch,
  component: () => <CourseDetailPage />,
})

function NodeWorkspaceRoute() {
  const { courseId, nodeId } = useParams({ from: '/courses/$courseId/n/$nodeId' })
  return <NodeWorkspace courseId={courseId} nodeId={nodeId} />
}

const nodeWorkspaceRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/courses/$courseId/n/$nodeId',
  validateSearch: tabSearch,
  component: NodeWorkspaceRoute,
})

const chapterRedirectRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/courses/$courseId/chapters/$chapterId',
  beforeLoad: ({ params }) => {
    throw redirect({
      to: '/courses/$courseId/n/$nodeId',
      params: { courseId: params.courseId, nodeId: params.chapterId },
      replace: true,
    })
  },
})

const libraryRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/library',
  validateSearch: (
    search: Record<string, unknown>
  ): { course?: number; folder?: number; source?: number } => ({
    course: typeof search.course === 'number' ? search.course : undefined,
    folder: typeof search.folder === 'number' ? search.folder : undefined,
    source: typeof search.source === 'number' ? search.source : undefined,
  }),
  component: () => <LibraryPage />,
})

const materialDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/library/$materialId',
  validateSearch: (search: Record<string, unknown>): { tab?: string; from?: string } => ({
    tab: typeof search.tab === 'string' ? search.tab : undefined,
    from: typeof search.from === 'string' ? search.from : undefined,
  }),
  component: () => <MaterialDetailPage />,
})

const quizRedirectRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/quiz',
  beforeLoad: () => {
    throw redirect({ to: '/courses', replace: true })
  },
})

function QuizRunRoute() {
  const { activityId } = useParams({ from: '/quiz/$activityId' })
  return <QuizRunner activityId={Number(activityId)} />
}

function focusSearch(search: Record<string, unknown>): {
  from?: string
  print?: boolean
} {
  return {
    from: typeof search.from === 'string' ? search.from : undefined,
    print: search.print === true,
  }
}

const quizRunRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/quiz/$activityId',
  validateSearch: focusSearch,
  component: QuizRunRoute,
})

const exercisesRedirectRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/exercises',
  beforeLoad: () => {
    throw redirect({ to: '/courses', replace: true })
  },
})

const exercisePlayerRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/exercises/$exerciseId',
  validateSearch: focusSearch,
  component: ExercisePlayerRoute,
})

function NoteEditorRoute() {
  return <NoteFocusPage />
}

const noteEditorRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/note/$noteId',
  validateSearch: focusSearch,
  component: NoteEditorRoute,
})

const notesRedirectRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/notes',
  beforeLoad: () => {
    throw redirect({ to: '/courses', replace: true })
  },
})

const noteEditorRedirectRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/notes/$noteId',
  beforeLoad: ({ params }) => {
    throw redirect({
      to: '/note/$noteId',
      params: { noteId: params.noteId },
      replace: true,
    })
  },
})

const flashcardsRedirectRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/flashcards',
  beforeLoad: () => {
    throw redirect({ to: '/courses', replace: true })
  },
})

const scoresRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/scores',
  validateSearch: (search: Record<string, unknown>): { tab?: string } => ({
    tab: typeof search.tab === 'string' ? search.tab : undefined,
  }),
  component: () => <ScoresPage />,
})

const spikeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/spike',
  component: () => <SpikePage />,
})

const jobsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/jobs',
  validateSearch: (search: Record<string, unknown>): {
    status?: string
    type?: string
    sort?: string
    dir?: string
  } => ({
    status: typeof search.status === 'string' ? search.status : undefined,
    type: typeof search.type === 'string' ? search.type : undefined,
    sort: typeof search.sort === 'string' ? search.sort : undefined,
    dir: typeof search.dir === 'string' ? search.dir : undefined,
  }),
  component: () => <JobsPage />,
})

const settingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/settings',
  validateSearch: (search: Record<string, unknown>): { tab?: string } => ({
    tab: typeof search.tab === 'string' ? search.tab : undefined,
  }),
  component: () => <SettingsPage />,
})

const routeTree = rootRoute.addChildren([
  indexRoute,
  chatRoute,
  chatDetailRoute,
  coursesRoute,
  courseDetailRoute,
  nodeWorkspaceRoute,
  chapterRedirectRoute,
  libraryRoute,
  materialDetailRoute,
  quizRedirectRoute,
  quizRunRoute,
  exercisesRedirectRoute,
  exercisePlayerRoute,
  noteEditorRoute,
  notesRedirectRoute,
  noteEditorRedirectRoute,
  flashcardsRedirectRoute,
  scoresRoute,
  spikeRoute,
  jobsRoute,
  settingsRoute,
])

export const router = createRouter({ routeTree, defaultPreload: 'intent' })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
