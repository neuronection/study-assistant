import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router'
import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import type { MentionRef } from '@/lib/api'

import { EntityMention } from './EntityMention'

function renderMention(mention: MentionRef) {
  const show = () => <EntityMention mention={mention} />
  const rootRoute = createRootRoute()
  const home = createRoute({
    getParentRoute: () => rootRoute,
    path: '/',
    component: show,
  })
  const routes = [
    createRoute({ getParentRoute: () => rootRoute, path: '/library/$materialId', component: show }),
    createRoute({ getParentRoute: () => rootRoute, path: '/note/$noteId', component: show }),
    createRoute({
      getParentRoute: () => rootRoute,
      path: '/courses/$courseId',
      component: show,
    }),
    createRoute({
      getParentRoute: () => rootRoute,
      path: '/courses/$courseId/n/$nodeId',
      component: show,
    }),
    createRoute({ getParentRoute: () => rootRoute, path: '/quiz/$activityId', component: show }),
    createRoute({
      getParentRoute: () => rootRoute,
      path: '/exercises/$exerciseId',
      component: show,
    }),
  ]
  const router = createRouter({
    routeTree: rootRoute.addChildren([home, ...routes]),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  })
  return { ...render(<RouterProvider router={router} />), router }
}

describe('EntityMention', () => {
  test('renders a material chip linking to the library', async () => {
    renderMention({
      ref: 'M12',
      kind: 'material',
      id: 12,
      title: 'Lecture 3',
      course_id: 1,
    })
    expect(await screen.findByRole('link', { name: /Lecture 3/ })).toHaveAttribute(
      'href',
      '/library/12',
    )
  })

  test('renders a note chip linking to the note page with origin return', async () => {
    renderMention({ ref: 'N3', kind: 'note', id: 3, title: 'My note', course_id: null })
    expect(await screen.findByRole('link', { name: /My note/ })).toHaveAttribute(
      'href',
      '/note/3?from=%2F',
    )
  })

  test('renders a concept chip linking to the workspace concepts tab', async () => {
    renderMention({
      ref: 'C7',
      kind: 'concept',
      id: 7,
      title: 'chain rule',
      course_id: 4,
    })
    expect(await screen.findByRole('link', { name: /chain rule/ })).toHaveAttribute(
      'href',
      '/courses/4?tab=concepts',
    )
  })

  test('renders a concept chip without course as a plain chip', async () => {
    renderMention({
      ref: 'C7',
      kind: 'concept',
      id: 7,
      title: 'chain rule',
      course_id: null,
    })
    expect(await screen.findByText('chain rule')).toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })

  test('renders a node chip linking into the node workspace', async () => {
    renderMention({
      ref: 'T5',
      kind: 'node',
      id: 5,
      title: 'Chapter 2',
      course_id: 4,
    })
    expect(await screen.findByRole('link', { name: /Chapter 2/ })).toHaveAttribute(
      'href',
      '/courses/4/n/5',
    )
  })

  test('renders quiz and exercise chips into their runners', async () => {
    const first = renderMention({
      ref: 'Q2',
      kind: 'quiz',
      id: 2,
      title: 'Limits quiz',
      course_id: 1,
    })
    expect(await first.findByRole('link', { name: /Limits quiz/ })).toHaveAttribute(
      'href',
      '/quiz/2?from=%2F',
    )
  })
})
