import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider, createMemoryHistory, createRootRoute, createRoute, createRouter } from '@tanstack/react-router'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { ExtractionView } from './ExtractionView'
import { useChatStore } from '@/lib/chat-store'

const getMaterial = vi.fn()
const editExtraction = vi.fn()
const setMaterialDescription = vi.fn()
const addMaterialDrawing = vi.fn()
const mindmapViewer = vi.fn()
const createChatSession = vi.fn()

beforeEach(() => {
  vi.clearAllMocks()
  useChatStore.setState({
    open: false,
    session: null,
    pendingSend: null,
    viewerAsks: {},
    width: 384,
  })
})

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getMaterial: (id: number) => getMaterial(id),
    editExtraction: (id: number, markdown: string) => editExtraction(id, markdown),
    setMaterialDescription: (id: number, description: string) =>
      setMaterialDescription(id, description),
    addMaterialDrawing: (...args: unknown[]) =>
      addMaterialDrawing(...(args as [number, unknown[], string])),
    createChatSession: (...args: unknown[]) => createChatSession(...(args as [])),
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

function renderView(
  scopeNodeId?: number,
  probes?: React.ReactNode,
  onQuoteSelection?: (text: string) => void
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const rootRoute = createRootRoute()
  const homeRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/',
    component: () => (
      <QueryClientProvider client={client}>
        <ExtractionView
          materialId={7}
          scopeNodeId={scopeNodeId}
          onQuoteSelection={onQuoteSelection}
        />
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

const textMaterial = {
  material: {
    id: 7,
    title: 'My notes',
    kind: 'md',
    mime: 'text/markdown',
    description: 'seeded description',
    provenance: null,
    status: 'ready',
    course_id: 3,
  },
  extraction: ordinaryMaterial.extraction,
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

  test('reading row keeps Edit as an icon action; the overflow moved to the material header (plan 62-E)', async () => {
    getMaterial.mockResolvedValue(ordinaryMaterial)
    renderView(8)
    await screen.findByText('hello')
    expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'More actions' })
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('menuitem', { name: 'Save as material' })
    ).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Print' })).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'History' })).not.toBeInTheDocument()
  })

  test('selecting a passage offers Ask AI about this which prefills the pinned chat (plan 61-D)', async () => {
    createChatSession.mockResolvedValue({
      id: 21,
      public_id: 'uuid-21',
      course_id: 3,
      title: 'Notes',
    })
    getMaterial.mockResolvedValue(ordinaryMaterial)
    renderView(8)
    expect(await screen.findByText('hello')).toBeInTheDocument()

    const target = screen.getByText('hello')
    const range = document.createRange()
    range.selectNodeContents(target)
    const selection = window.getSelection()
    selection?.removeAllRanges()
    selection?.addRange(range)
    fireEvent.mouseUp(target.closest("div")!)

    const ask = await screen.findByRole('button', { name: 'Ask AI about this' })
    fireEvent.click(ask)

    await waitFor(() =>
      expect(useChatStore.getState().pendingSend).toEqual({
        content: '> hello\n\n',
        attachments: [{ kind: 'material', id: 7, title: 'Notes' }],
        mode: 'prefill',
      }),
    )
    expect(createChatSession).toHaveBeenCalledWith(3, 8, 'Notes')
  })

  test('the selection toolbar quotes into the note when a handler is provided (plan 61-D)', async () => {
    getMaterial.mockResolvedValue(ordinaryMaterial)
    const onQuoteSelection = vi.fn()
    renderView(undefined, undefined, onQuoteSelection)
    expect(await screen.findByText('hello')).toBeInTheDocument()

    const target = screen.getByText('hello')
    const range = document.createRange()
    range.selectNodeContents(target)
    const selection = window.getSelection()
    selection?.removeAllRanges()
    selection?.addRange(range)
    fireEvent.mouseUp(target.closest("div")!)

    const quote = await screen.findByRole('button', { name: /quote into note/i })
    fireEvent.click(quote)
    expect(onQuoteSelection).toHaveBeenCalledWith('hello')
    expect(useChatStore.getState().pendingSend).toBeNull()
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

  test('text materials edit through Content and Description tabs', async () => {
    editExtraction.mockResolvedValue({})
    setMaterialDescription.mockResolvedValue({})
    getMaterial.mockResolvedValue(textMaterial)
    renderView()

    fireEvent.click(await screen.findByRole('button', { name: 'Edit' }))
    expect(await screen.findByRole('tab', { name: 'Content' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Description' })).toBeInTheDocument()
    expect(screen.getByLabelText('Extraction markdown editor')).toHaveValue('hello $x^2$')

    fireEvent.click(screen.getByRole('tab', { name: 'Description' }))
    const description = screen.getByLabelText('Description')
    expect(description).toHaveValue('seeded description')
    fireEvent.change(description, { target: { value: 'updated description' } })

    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(editExtraction).toHaveBeenCalledWith(7, 'hello $x^2$'))
    await waitFor(() =>
      expect(setMaterialDescription).toHaveBeenCalledWith(7, 'updated description')
    )
  })

  test('an unchanged description is not re-saved', async () => {
    editExtraction.mockResolvedValue({})
    getMaterial.mockResolvedValue(textMaterial)
    renderView()

    fireEvent.click(await screen.findByRole('button', { name: 'Edit' }))
    await screen.findByLabelText('Extraction markdown editor')
    fireEvent.change(screen.getByLabelText('Extraction markdown editor'), {
      target: { value: 'changed body' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(editExtraction).toHaveBeenCalledWith(7, 'changed body'))
    expect(setMaterialDescription).not.toHaveBeenCalled()
  })

  test('non-text materials keep the single-surface editor', async () => {
    editExtraction.mockResolvedValue({})
    getMaterial.mockResolvedValue(ordinaryMaterial)
    renderView()

    fireEvent.click(await screen.findByRole('button', { name: 'Edit' }))
    await screen.findByLabelText('Extraction markdown editor')
    expect(screen.queryByRole('tab', { name: 'Description' })).not.toBeInTheDocument()
  })
})
