import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { RouterProvider, createMemoryHistory, createRootRoute, createRoute, createRouter } from '@tanstack/react-router'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { ExtractionView } from './ExtractionView'

const getMaterial = vi.fn()
const editExtraction = vi.fn()
const deriveMaterial = vi.fn()
const addMaterialDrawing = vi.fn()
const mindmapViewer = vi.fn()

beforeEach(() => {
  vi.clearAllMocks()
})

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getMaterial: (id: number) => getMaterial(id),
    editExtraction: (id: number, markdown: string) => editExtraction(id, markdown),
    deriveMaterial: (id: number, options?: { nodeId?: number | null }) =>
      deriveMaterial(id, options),
    addMaterialDrawing: (...args: unknown[]) =>
      addMaterialDrawing(...(args as [number, unknown[], string])),
  }
})

vi.mock('@/components/editor/LazyMarkdownEditor', () => ({
  LazyMarkdownEditor: ({
    value,
    onChange,
    ariaLabel,
    drawings,
    drawingAdapter,
    aiHelper,
  }: {
    value: string
    onChange: (markdown: string) => void
    ariaLabel: string
    drawings?: unknown[]
    drawingAdapter?: {
      create: (strokes: unknown[], pngBase64: string, ocr: boolean) => Promise<number | null>
    }
    aiHelper?: { courseId?: number; title: string }
  }) => (
    <div>
      <input
        aria-label={ariaLabel}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <button
        type="button"
        aria-label={`extraction-ai-helper-${aiHelper?.courseId ?? 'none'}`}
      >
        extraction-ai-helper
      </button>
      {drawingAdapter ? (
        <button
          type="button"
          onClick={() => void drawingAdapter.create([], 'AAA', true)}
        >
          editor-create-drawing
        </button>
      ) : null}
      <span data-testid="drawings-count">{drawings?.length ?? 0}</span>
    </div>
  ),
}))

vi.mock('./MindmapViewer', () => ({
  MindmapViewer: (props: Record<string, unknown>) => {
    mindmapViewer(props)
    return <div data-testid="mindmap-viewer" />
  },
}))

function renderView(scopeNodeId?: number, probes?: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const rootRoute = createRootRoute()
  const homeRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/',
    component: () => (
      <QueryClientProvider client={client}>
        <ExtractionView materialId={7} scopeNodeId={scopeNodeId} />
        {probes}
      </QueryClientProvider>
    ),
  })
  const materialRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/library/$materialId',
    component: () => null,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([homeRoute, materialRoute]),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  })
  render(<RouterProvider router={router} />)
  return client
}

const ordinaryMaterial = {
  material: { id: 7, title: 'Notes', provenance: null, status: 'ready', course_id: 3 },
  extraction: {
    id: 1,
    material_id: 7,
    version: 2,
    extractor: 'ocr',
    markdown: 'hello $x^2$',
    blocks: [{ type: 'text', md: 'hello' }],
  },
  index_card: null,
  drawings: [],
}

describe('ExtractionView', () => {
  test('renders the interactive mindmap for mindmap materials', async () => {
    getMaterial.mockResolvedValue({
      material: {
        id: 7,
        title: 'Limits map',
        provenance: { source: 'ai-composed', kind: 'mindmap' },
        status: 'ready',
      },
      extraction: {
        id: 1,
        material_id: 7,
        version: 1,
        extractor: 'compose',
        markdown: '# Limits\n- definition',
        blocks: [],
      },
      index_card: null,
    })
    renderView()
    expect(await screen.findByTestId('mindmap-viewer')).toBeInTheDocument()
    expect(mindmapViewer).toHaveBeenCalledWith(
      expect.objectContaining({ markdown: '# Limits\n- definition' })
    )
  })

  test('renders block content for ordinary materials', async () => {
    getMaterial.mockResolvedValue(ordinaryMaterial)
    renderView()
    expect(await screen.findByText('hello')).toBeInTheDocument()
    expect(screen.queryByTestId('mindmap-viewer')).not.toBeInTheDocument()
  })

  test('edits through the rich markdown editor', async () => {
    editExtraction.mockResolvedValue({})
    getMaterial.mockResolvedValue(ordinaryMaterial)
    renderView()

    fireEvent.click(await screen.findByRole('button', { name: 'Edit' }))
    const editor = await screen.findByLabelText('Extraction markdown editor')
    expect(editor).toHaveValue('hello $x^2$')
    expect(
      screen.getByRole('button', { name: 'extraction-ai-helper-3' })
    ).not.toBeNull()

    fireEvent.change(editor, { target: { value: 'fixed $x^2$' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(editExtraction).toHaveBeenCalledWith(7, 'fixed $x^2$'))
  })

  test('save is disabled for an empty draft', async () => {
    editExtraction.mockResolvedValue({})
    getMaterial.mockResolvedValue(ordinaryMaterial)
    renderView()

    fireEvent.click(await screen.findByRole('button', { name: 'Edit' }))
    const editor = await screen.findByLabelText('Extraction markdown editor')
    fireEvent.change(editor, { target: { value: '' } })
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
  })

  test('cancel returns to the rendered view without saving', async () => {
    getMaterial.mockResolvedValue(ordinaryMaterial)
    renderView()

    fireEvent.click(await screen.findByRole('button', { name: 'Edit' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    await screen.findByText('hello')
    expect(editExtraction).not.toHaveBeenCalled()
  })

  test('derives a new material and offers to open it', async () => {
    deriveMaterial.mockResolvedValue({
      material: { id: 12, title: 'Notes (extracted)' },
      job_id: 4,
      deduped: false,
    })
    getMaterial.mockResolvedValue(ordinaryMaterial)
    renderView()

    fireEvent.click(await screen.findByRole('button', { name: 'Save as material' }))
    await waitFor(() => expect(deriveMaterial).toHaveBeenCalledWith(7, { nodeId: null }))
    expect(
      await screen.findByText('Saved as Notes (extracted)')
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open' })).toBeInTheDocument()
  })

  test('derive passes the opened node so the material lands there', async () => {
    deriveMaterial.mockResolvedValue({
      material: { id: 12, title: 'Notes (extracted)' },
      job_id: 4,
      deduped: false,
    })
    getMaterial.mockResolvedValue(ordinaryMaterial)
    renderView(5)

    fireEvent.click(await screen.findByRole('button', { name: 'Save as material' }))
    await waitFor(() => expect(deriveMaterial).toHaveBeenCalledWith(7, { nodeId: 5 }))
  })

  test('derive refreshes the workspace materials tab and tree without a reload', async () => {
    deriveMaterial.mockResolvedValue({
      material: { id: 12, title: 'Notes (extracted)' },
      job_id: 4,
      deduped: false,
    })
    getMaterial.mockResolvedValue(ordinaryMaterial)
    const treeFn = vi.fn().mockResolvedValue([])
    const workspaceFn = vi.fn().mockResolvedValue({})
    function Probes() {
      useQuery({ queryKey: ['tree'], queryFn: treeFn })
      useQuery({ queryKey: ['node-workspace', '5'], queryFn: workspaceFn })
      return null
    }
    renderView(5, <Probes />)
    await waitFor(() => expect(treeFn).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(workspaceFn).toHaveBeenCalledTimes(1))

    fireEvent.click(await screen.findByRole('button', { name: 'Save as material' }))
    await screen.findByText('Saved as Notes (extracted)')
    await waitFor(() => expect(treeFn).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(workspaceFn).toHaveBeenCalledTimes(2))
  })

  test('derive surfaces the duplicate notice when deduped', async () => {
    deriveMaterial.mockResolvedValue({
      material: { id: 12, title: 'Notes (extracted)' },
      job_id: null,
      deduped: true,
    })
    getMaterial.mockResolvedValue(ordinaryMaterial)
    renderView()

    fireEvent.click(await screen.findByRole('button', { name: 'Save as material' }))
    expect(
      await screen.findByText('An identical material already exists')
    ).toBeInTheDocument()
  })

  test('derive failure shows an inline error', async () => {
    deriveMaterial.mockRejectedValue(new Error('boom'))
    getMaterial.mockResolvedValue(ordinaryMaterial)
    renderView()

    fireEvent.click(await screen.findByRole('button', { name: 'Save as material' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not save as material'
    )
  })

  test('the drawing adapter create wires through to addMaterialDrawing', async () => {
    addMaterialDrawing.mockResolvedValue({
      ...ordinaryMaterial,
      drawings: [
        {
          id: 11,
          png_sha: 'sha11',
          strokes: [],
          ocr_version: 1,
          ocr_markdown: 'fresh',
          created_at: '2026-08-22T10:00:00',
        },
      ],
    })
    getMaterial.mockResolvedValue(ordinaryMaterial)
    renderView()

    fireEvent.click(await screen.findByRole('button', { name: 'Edit' }))
    await screen.findByLabelText('Extraction markdown editor')
    fireEvent.click(screen.getByRole('button', { name: 'editor-create-drawing' }))
    await waitFor(() => expect(addMaterialDrawing).toHaveBeenCalledWith(7, [], 'AAA', true, undefined))
  })
})
