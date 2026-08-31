import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router'

vi.mock('mermaid', () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn(async (_id: string, code: string) => ({
      svg: `<svg data-testid="mermaid-svg" data-code="${code}"></svg>`,
    })),
  },
}))

import { BlockRenderer } from './BlockRenderer'
import type { Block } from './types'

function renderWithRouter(ui: React.ReactNode) {
  const rootRoute = createRootRoute()
  const routes = [
    createRoute({ getParentRoute: () => rootRoute, path: '/', component: () => <>{ui}</> }),
    createRoute({ getParentRoute: () => rootRoute, path: '/library/$materialId', component: () => null }),
    createRoute({ getParentRoute: () => rootRoute, path: '/note/$noteId', component: () => null }),
    createRoute({ getParentRoute: () => rootRoute, path: '/courses/$courseId', component: () => null }),
    createRoute({
      getParentRoute: () => rootRoute,
      path: '/courses/$courseId/n/$nodeId',
      component: () => null,
    }),
    createRoute({ getParentRoute: () => rootRoute, path: '/quiz/$activityId', component: () => null }),
    createRoute({
      getParentRoute: () => rootRoute,
      path: '/exercises/$exerciseId',
      component: () => null,
    }),
  ]
  const router = createRouter({
    routeTree: rootRoute.addChildren(routes),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  })
  return render(<RouterProvider router={router} />)
}

describe('BlockRenderer', () => {
  test('renders text markdown with inline math', () => {
    render(<BlockRenderer blocks={[{ type: 'text', md: '**bold** and $x^2$' }]} />)
    expect(screen.getByText('bold')).toBeInTheDocument()
    expect(document.querySelector('.katex')).not.toBeNull()
  })

  test('renders display math via katex', () => {
    render(<BlockRenderer blocks={[{ type: 'math', latex: '\\int_0^1 x^2\\,dx', display: true }]} />)
    expect(document.querySelector('.katex-display')).not.toBeNull()
  })

  test('renders mermaid diagrams', async () => {
    render(<BlockRenderer blocks={[{ type: 'diagram', mermaid: 'graph LR; A-->B' }]} />)
    const svg = await screen.findByTestId('mermaid-svg')
    expect(svg).toBeInTheDocument()
  })

  test('renders mermaid fences inside text blocks as diagrams', async () => {
    render(
      <BlockRenderer
        blocks={[
          {
            type: 'text',
            md: '```mermaid\nflowchart TD\n    A[x^3 + 1] --> B[(x + 1)(x^2 - x + 1)]\n```',
          },
        ]}
      />
    )
    const svg = await screen.findByTestId('mermaid-svg')
    expect(svg.getAttribute('data-code')).toContain('flowchart TD')
  })

  test('non-mermaid code fences inside text blocks stay code blocks', () => {
    render(<BlockRenderer blocks={[{ type: 'text', md: '```python\nprint(1)\n```' }]} />)
    expect(screen.getByText('print(1)')).toBeInTheDocument()
    expect(screen.getByRole('code', { hidden: true }) ?? document.querySelector('code')).not.toBeNull()
  })

  test('renders tables with caption', () => {
    render(
      <BlockRenderer
        blocks={[{ type: 'table', rows: [['x', 'y'], ['1', '2']], caption: 'values' }]}
      />
    )
    expect(screen.getByText('values')).toBeInTheDocument()
    expect(screen.getByRole('table')).toBeInTheDocument()
  })

  test('renders code blocks', () => {
    render(<BlockRenderer blocks={[{ type: 'code', lang: 'python', code: 'print(1)' }]} />)
    expect(screen.getByText('print(1)')).toBeInTheDocument()
  })

  test('renders inline mention chips inside markdown text', async () => {
    renderWithRouter(
      <BlockRenderer
        blocks={[
          {
            type: 'text',
            md: 'Review [M12] before [Q3], not [M999].',
            mentions: [
              { ref: 'M12', kind: 'material', id: 12, title: 'Lecture 3', course_id: 1 },
              { ref: 'Q3', kind: 'quiz', id: 3, title: 'Limits quiz', course_id: 1 },
            ],
          },
        ]}
      />,
    )
    expect(await screen.findByText('Lecture 3')).toBeInTheDocument()
    expect(await screen.findByText('Limits quiz')).toBeInTheDocument()
    expect(screen.getByText(/\[M999\]/)).toBeInTheDocument()
    expect(screen.queryByText('M12')).not.toBeInTheDocument()
  })

  test('renders a standalone mention block as a chip', async () => {
    renderWithRouter(
      <BlockRenderer
        blocks={[
          {
            type: 'mention',
            ref: 'N7',
            kind: 'note',
            id: 7,
            title: 'Derivatives note',
            course_id: 2,
          },
        ]}
      />,
    )
    expect(await screen.findByText('Derivatives note')).toBeInTheDocument()
  })

  test('renders unknown block types as fallback preserving the type', () => {
    render(<BlockRenderer blocks={[{ type: 'hologram', data: 1 }]} />)
    expect(screen.getByText(/hologram/)).toBeInTheDocument()
  })

  test('renders drawing blocks with the png and a transcript', () => {
    render(
      <BlockRenderer
        blocks={[{ type: 'drawing', drawing_id: 5 }]}
        resolveDrawing={(id) =>
          id === 5
            ? { id: 5, png_sha: 'deadbeef', ocr_markdown: '$2x$' }
            : undefined
        }
      />,
    )
    const img = screen.getByAltText(/handwritten/i)
    expect(img).toHaveAttribute('src', '/api/v1/blobs/deadbeef')
    expect(screen.getByText('OCR text')).toBeInTheDocument()
  })

  test('renders drawing blocks as a placeholder without a resolver', () => {
    render(<BlockRenderer blocks={[{ type: 'drawing', drawing_id: 9 }]} />)
    expect(screen.getByText(/#9/)).toBeInTheDocument()
  })

  test('code blocks expose a copy button that writes the code', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    render(
      <BlockRenderer
        blocks={[
          {
            type: 'text',
            md: '```python\nprint(42)\n```',
          } as unknown as Block,
        ]}
      />,
    )
    fireEvent.click(await screen.findByTitle('Copy code'))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('print(42)'))
    expect(await screen.findByTitle('Copy code')).toHaveAttribute('data-copied', 'true')
  })

})
