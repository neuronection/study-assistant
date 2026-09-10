import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from '@tanstack/react-router'
import { render, screen } from '@testing-library/react'
import { useEffect } from 'react'
import { describe, expect, test, vi } from 'vitest'

import { motionState, rendersIdenticallyUnderReducedMotion } from '@/test/motion'

vi.mock('framer-motion', async (importOriginal) => {
  const actual = await importOriginal<typeof import('framer-motion')>()
  return {
    ...actual,
    useReducedMotion: () => motionState.reduced,
  }
})

import { RouteFade } from './RouteFade'

function ChatLayout({ mountRef }: { mountRef: { current: number } }) {
  useEffect(() => {
    mountRef.current += 1
  }, [mountRef])
  return (
    <div>
      <p>chat-content</p>
      <Outlet />
    </div>
  )
}

function makeRouter(initialUrl: string) {
  const mountRef = { current: 0 }
  const rootRoute = createRootRoute({
    component: () => (
      <RouteFade>
        <Outlet />
      </RouteFade>
    ),
  })
  const homeRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/',
    component: () => <p>home-content</p>,
  })
  const libraryRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/library',
    component: () => <p>library-content</p>,
  })
  const chatRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/chat',
    component: () => <ChatLayout mountRef={mountRef} />,
  })
  const chatIndexRoute = createRoute({
    getParentRoute: () => chatRoute,
    path: '/',
    component: () => <p>chat-index</p>,
  })
  const chatDetailRoute = createRoute({
    getParentRoute: () => chatRoute,
    path: '$chatId',
    component: () => <p>chat-detail</p>,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([
      homeRoute,
      libraryRoute,
      chatRoute.addChildren([chatIndexRoute, chatDetailRoute]),
    ]),
    history: createMemoryHistory({ initialEntries: [initialUrl] }),
  })
  return { router, mountCount: () => mountRef.current }
}

function renderRouteFade(url: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const made = makeRouter(url)
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={made.router} />
    </QueryClientProvider>,
  )
  return made
}

describe('RouteFade', () => {
  test('renders the active route content', async () => {
    renderRouteFade('/')
    expect(await screen.findByText('home-content')).toBeInTheDocument()
  })

  test('keeps the area mounted across within-area navigation', async () => {
    const { router, mountCount } = renderRouteFade('/chat')
    expect(await screen.findByText('chat-index')).toBeInTheDocument()
    await router.navigate({ to: '/chat/$chatId', params: { chatId: 'abc' } })
    expect(await screen.findByText('chat-detail')).toBeInTheDocument()
    expect(mountCount()).toBe(1)
  })

  test('swaps areas on cross-area navigation', async () => {
    const { router } = renderRouteFade('/chat')
    expect(await screen.findByText('chat-index')).toBeInTheDocument()
    await router.navigate({ to: '/library' })
    expect(await screen.findByText('library-content', {}, { timeout: 3000 })).toBeInTheDocument()
    expect(screen.queryByText('chat-content')).not.toBeInTheDocument()
  })

  test('renders identically under prefers-reduced-motion', async () => {
    const settle = async (result: { findByText: (text: string) => Promise<HTMLElement> }) => {
      expect(await result.findByText('library-content')).toBeInTheDocument()
    }
    await rendersIdenticallyUnderReducedMotion(() => {
      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      return (
        <QueryClientProvider client={client}>
          <RouterProvider router={makeRouter('/library').router} />
        </QueryClientProvider>
      )
    }, settle)
    expect(motionState.reduced).toBe(false)
  })
})
