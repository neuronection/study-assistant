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
import { ReviewPage } from '@/features/review/ReviewPage'
import { StudySessionPage } from '@/features/study-session/StudySessionFlow'
import { QuizRunner } from '@/features/quiz/QuizRunner'
import { ScoresPage } from '@/features/scores/ScoresPage'
import { JobsPage } from '@/features/jobs/JobsPage'
import { SettingsPage } from '@/features/settings/SettingsPage'
import { AboutPage } from '@/features/about/AboutPage'

const rootRoute = createRootRoute({
  component: () => <AppShell />,
})

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: () => <HomePage />,
})

const reviewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/review',
  component: () => <ReviewPage />,
})

const studySessionRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/study/session',
  component: () => <StudySessionPage />,
})

const chatRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/chat',
  component: () => <ChatPage />,
})

const chatIndexRoute = createRoute({
  getParentRoute: () => chatRoute,
  path: '/',
  component: () => null,
})

const chatDetailRoute = createRoute({
  getParentRoute: () => chatRoute,
  path: '$chatId',
  component: () => null,
})

const coursesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/courses',
  component: () => <CoursesPage />,
})

function asId(value: unknown): string | undefined {
  if (typeof value === 'string') {
    return value.length > 0 ? value : undefined
  }
  return typeof value === 'number' ? String(value) : undefined
}

function tabSearch(search: Record<string, unknown>): {
  tab?: string
  note?: string
  material?: string
  study?: string
  folder?: string
} {
  return {
    tab: typeof search.tab === 'string' ? search.tab : undefined,
    note: asId(search.note),
    material: asId(search.material),
    study: asId(search.study),
    folder: asId(search.folder),
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
  ): { course?: string; folder?: string; source?: string } => ({
    course: asId(search.course),
    folder: asId(search.folder),
    source: asId(search.source),
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
  return <QuizRunner activityId={activityId} />
}

function focusSearch(search: Record<string, unknown>): {
  from?: string
  print?: 'paper' | 'key'
} {
  return {
    from: typeof search.from === 'string' ? search.from : undefined,
    print:
      search.print === 'paper' || search.print === 'key' ? search.print : undefined,
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
  validateSearch: (
    search: Record<string, unknown>
  ): { tab?: string; section?: string; obs?: string; detail?: string } => ({
    tab: typeof search.tab === 'string' ? search.tab : undefined,
    section: typeof search.section === 'string' ? search.section : undefined,
    obs: typeof search.obs === 'string' ? search.obs : undefined,
    detail: typeof search.detail === 'string' ? search.detail : undefined,
  }),
  component: () => <SettingsPage />,
})

const aboutRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/about',
  component: () => <AboutPage />,
})

const routeTree = rootRoute.addChildren([
  indexRoute,
  reviewRoute,
  studySessionRoute,
  chatRoute.addChildren([chatIndexRoute, chatDetailRoute]),
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
  jobsRoute,
  settingsRoute,
  aboutRoute,
])

export const router = createRouter({ routeTree, defaultPreload: 'intent' })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
