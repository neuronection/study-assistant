import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  redirect,
  RouterProvider,
} from '@tanstack/react-router'
import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

function renderRedirectApp(initialUrl: string) {
  const rootRoute = createRootRoute()
  const coursesRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/courses',
    component: () => <p>courses-index</p>,
  })
  const quizRedirectRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/quiz',
    beforeLoad: () => {
      throw redirect({ to: '/courses', replace: true })
    },
  })
  const exercisesRedirectRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/exercises',
    beforeLoad: () => {
      throw redirect({ to: '/courses', replace: true })
    },
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([
      coursesRoute,
      quizRedirectRoute,
      exercisesRedirectRoute,
    ]),
    history: createMemoryHistory({ initialEntries: [initialUrl] }),
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
  return router
}

describe('flat quiz/exercises route redirects', () => {
  test('/quiz redirects to /courses', async () => {
    const router = renderRedirectApp('/quiz')
    expect(await screen.findByText('courses-index')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/courses')
  })

  test('/exercises redirects to /courses', async () => {
    const router = renderRedirectApp('/exercises')
    expect(await screen.findByText('courses-index')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/courses')
  })
})
