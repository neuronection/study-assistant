import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router'
import { describe, expect, test, vi } from 'vitest'

import { NoteLinks } from './NoteLinks'

const listNoteLinks = vi.fn()
const navigate = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return { ...actual, listNoteLinks: (id: string) => listNoteLinks(id) }
})

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return { ...actual, useNavigate: () => navigate }
})

function renderLinks() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const rootRoute = createRootRoute()
  const routes = [
    createRoute({ getParentRoute: () => rootRoute, path: '/', component: () => <NoteLinks noteId="n1" /> }),
    createRoute({ getParentRoute: () => rootRoute, path: '/note/$noteId', component: () => null }),
  ]
  const router = createRouter({
    routeTree: rootRoute.addChildren(routes),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  })
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}

describe('NoteLinks', () => {
  test('renders resolved and broken wikilinks and navigates on click', async () => {
    listNoteLinks.mockResolvedValue({
      outbound: [
        { id: 'l1', target: 'Eigenvalues', note_id: 'n2', title: 'Eigenvalues', broken: false },
        { id: 'l2', target: 'Missing', note_id: null, title: null, broken: true },
      ],
      backlinks: [{ id: 'l3', target: 'Linear Algebra', note_id: 'n3', title: 'Linear Algebra' }],
    })
    renderLinks()
    expect(await screen.findByText('Eigenvalues')).toBeInTheDocument()
    const broken = screen.getByText('Missing').closest('button')
    expect(broken).toBeDisabled()
    fireEvent.click(screen.getByText('Eigenvalues'))
    expect(navigate).toHaveBeenCalledWith({
      to: '/note/$noteId',
      params: { noteId: 'n2' },
    })
  })
})
