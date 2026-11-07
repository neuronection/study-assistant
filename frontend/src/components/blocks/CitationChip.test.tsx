import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router'
import { describe, expect, test, vi } from 'vitest'

import { BlockRenderer, citationsToMarkdownLinks } from './BlockRenderer'

const getMaterial = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getMaterial: (id: string) => getMaterial(id),
  }
})

function renderBlock(md: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const rootRoute = createRootRoute()
  const routes = [
    createRoute({ getParentRoute: () => rootRoute, path: '/', component: () => <BlockRenderer blocks={[{ type: 'text', md }]} /> }),
    createRoute({ getParentRoute: () => rootRoute, path: '/library/$materialId', component: () => null }),
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

describe('citation chips', () => {
  test('converts cite tokens to internal links', () => {
    expect(citationsToMarkdownLinks('See [[cite:abc-123]] for the proof.')).toBe(
      'See [cite](sa-cite:abc-123) for the proof.'
    )
  })

  test('renders the deterministic citation style from material metadata', async () => {
    getMaterial.mockResolvedValue({
      material: {
        id: 'abc-123',
        title: 'Gradient descent convergence',
        citation_text: 'Lovelace (2024) — Gradient descent convergence',
      },
    })
    renderBlock('See [[cite:abc-123]] for the proof.')
    const chip = await screen.findByTestId('citation-chip')
    expect(await screen.findByText('Lovelace (2024) — Gradient descent convergence')).toBeInTheDocument()
    expect(chip).toHaveTextContent('Lovelace (2024) — Gradient descent convergence')
    expect(getMaterial).toHaveBeenCalledWith('abc-123')
  })
})
