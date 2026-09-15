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

  test('renders image_ref blocks through the image resolver', () => {
    render(
      <BlockRenderer
        blocks={[{ type: 'image_ref', image_id: 7 }]}
        resolveImage={(id) =>
          id === 7 ? { blob_sha: 'cafe1234', ocr_markdown: 'unit circle' } : undefined
        }
      />,
    )
    const img = screen.getByAltText('unit circle')
    expect(img).toHaveAttribute('src', '/api/v1/blobs/cafe1234')
  })

  test('unresolved image_ref blocks fall back to a placeholder', () => {
    render(<BlockRenderer blocks={[{ type: 'image_ref', image_id: 9 }]} />)
    expect(screen.getByText('#9')).toBeInTheDocument()
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

  test('code blocks expose a direct copy button and the fenced copy in the menu', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    render(<BlockRenderer blocks={[{ type: 'code', lang: 'python', code: 'print(42)' }]} />)
    expect(screen.getByTitle('Copy code')).toBeInTheDocument()
    fireEvent.pointerDown(screen.getByRole('button', { name: 'Copy options' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Copy as fenced block' }))
    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith('```python\nprint(42)\n```')
    )
  })

  test('math blocks copy raw LaTeX from the menu (plan 63-B)', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    render(
      <BlockRenderer blocks={[{ type: 'math', latex: '\\int_0^1 x^2\\,dx', display: true }]} />
    )
    fireEvent.pointerDown(screen.getByRole('button', { name: 'Copy options' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Copy LaTeX' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('\\int_0^1 x^2\\,dx'))
  })

  test('display math markdown copy wraps in double dollars (plan 63-B)', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    render(
      <BlockRenderer blocks={[{ type: 'math', latex: 'e^x', display: true }]} />
    )
    fireEvent.pointerDown(screen.getByRole('button', { name: 'Copy options' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Copy as Markdown' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('$$e^x$$'))
  })

  test('tables copy as a markdown table (plan 63-B)', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    render(
      <BlockRenderer
        blocks={[{ type: 'table', rows: [['f(x)'], ['x^2']] }]}
      />
    )
    fireEvent.pointerDown(screen.getByRole('button', { name: 'Copy options' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Copy as markdown table' }))
    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith('| f(x) |\n| --- |\n| x^2 |')
    )
  })

  test('mention blocks get no copy menu (plan 63-B)', () => {
    renderWithRouter(
      <BlockRenderer
        blocks={[{ type: 'mention', ref: 'N1', kind: 'note', id: 1, title: 'Note' }]}
      />
    )
    expect(screen.queryByRole('button', { name: 'Copy options' })).toBeNull()
  })

  test('actions={false} suppresses every copy menu (plan 63-B)', () => {
    render(
      <BlockRenderer
        blocks={[
          { type: 'math', latex: 'x', display: true },
          { type: 'table', rows: [['a']] },
          { type: 'code', code: 'x' },
        ]}
        actions={false}
      />
    )
    expect(screen.queryByRole('button', { name: 'Copy options' })).toBeNull()
    expect(document.querySelector('.katex-display')).not.toBeNull()
  })

  test('multi-line $$ display math with content on the fence lines renders display (plan 63-E, material 84 payload)', () => {
    render(
      <BlockRenderer
        blocks={[
          {
            type: 'text',
            md: 'Θέτω $u=e^x \\Rightarrow du=e^x\\,dx$\n\n$$I=\\int \\frac{e^x}{e^x(e^{2x}-1)}\\,dx\n\\overset{(1),(2)}{\\Rightarrow}\nI=\\int \\frac{du}{u(u^2-1)}$$',
          },
        ]}
      />
    )
    expect(document.querySelector('.katex-display')).not.toBeNull()
    const rawParagraph = Array.from(document.querySelectorAll('p')).find((p) =>
      p.textContent?.includes('$$')
    )
    expect(rawParagraph).toBeUndefined()
  })

  test('single-line $$…$$ alone on its line renders display-style (plan 63-E)', () => {
    render(<BlockRenderer blocks={[{ type: 'text', md: '$$I=\\arctan(2x)+C$$' }]} />)
    expect(document.querySelector('.katex-display')).not.toBeNull()
  })

  test('display math indented inside a list item renders without leaking raw latex (material 93)', () => {
    const md = [
      '### Θέμα',
      '* **Ορισμός [M44]:** Η παράγωγος της $f(x)$:',
      '  $$f\'(x) = \\lim_{h \\to 0} \\frac{f(x+h) - f(x)}{h}$$',
      '  Η παράγωγος ($f\'(x) > 0 \\implies$ αύξουσα) [M44].',
      '* **Κανόνες [M44], [M56]:**',
      '  * Γραμμικότητα: $(af(x) + bg(x))\' = a f\'(x) + b g\'(x)$',
    ].join('\n')
    render(<BlockRenderer blocks={[{ type: 'text', md }]} />)
    expect(document.querySelector('.katex-display')).not.toBeNull()
    expect(document.querySelector('.katex-error')).toBeNull()
    const rawLeak = Array.from(document.querySelectorAll('p, li')).find((el) => {
      const clone = el.cloneNode(true) as HTMLElement
      clone.querySelectorAll('.katex').forEach((node) => node.remove())
      return /\\lim|\\frac|\$\$/.test(clone.textContent ?? '')
    })
    expect(rawLeak).toBeUndefined()
  })

})
