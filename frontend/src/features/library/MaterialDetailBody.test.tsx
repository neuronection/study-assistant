import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { MaterialDetailBody } from './MaterialDetailBody'

const getMaterial = vi.fn()
const getMaterialLinks = vi.fn()
const listCourses = vi.fn()
const listStudyStates = vi.fn()
const setStudyState = vi.fn()
const deriveMaterial = vi.fn()
const navigate = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getMaterial: (id: number) => getMaterial(id),
    getMaterialLinks: (id: number) => getMaterialLinks(id),
    listCourses: () => listCourses(),
    listStudyStates: () => listStudyStates(),
    setStudyState: (id: number, status: string) => setStudyState(id, status),
    deriveMaterial: (id: number, options?: { nodeId?: number | null }) =>
      deriveMaterial(id, options),
  }
})

vi.mock('./ExtractionView', () => ({
  ExtractionView: () => <div data-testid="extraction-view" />,
}))
vi.mock('./OriginalView', () => ({
  OriginalView: () => <div data-testid="original-view" />,
}))
vi.mock('./ExtractionHistoryDialog', () => ({
  ExtractionHistoryDialog: () => <div data-testid="extraction-history-dialog" />,
}))
vi.mock('@/components/print/MarkdownPrintDoc', () => ({
  MarkdownPrintDoc: () => <div data-testid="markdown-print-doc" />,
}))

vi.mock('@tanstack/react-router', () => ({
  Link: ({
    children,
    to,
    params,
    title,
  }: {
    children: React.ReactNode
    to: string
    params?: Record<string, string>
    title?: string
  }) => {
    let href = to
    for (const [key, value] of Object.entries(params ?? {})) {
      href = href.replace(`$${key}`, value)
    }
    return (
      <a href={href} title={title}>
        {children}
      </a>
    )
  },
  useNavigate: () => navigate,
}))

const exportMarkdownWithDrawings = vi.fn()

vi.mock('@/components/materials/exportMarkdown', () => ({
  exportMarkdownWithDrawings: (markdown: string, drawings: unknown[]) =>
    exportMarkdownWithDrawings(markdown, drawings),
}))

const MATERIAL = {
  material: {
    id: 5,
    course_id: 2,
    title: 'Chain rule worksheet',
    status: 'ready',
    reextract_modes: ['auto', 'text', 'ocr'],
  },
  extraction: null,
  index_card: null,
  drawings: [],
}

function renderBody(props: Partial<Parameters<typeof MaterialDetailBody>[0]> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MaterialDetailBody
        materialId={5}
        activeTab="extraction"
        onTabChange={vi.fn()}
        {...props}
      />
    </QueryClientProvider>
  )
}

function renderBodyWithProbes(
  props: Partial<Parameters<typeof MaterialDetailBody>[0]> = {},
  probes?: React.ReactNode
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MaterialDetailBody
        materialId={5}
        activeTab="extraction"
        onTabChange={vi.fn()}
        {...props}
      />
      {probes}
    </QueryClientProvider>
  )
}

async function openMoreMaterialActions() {
  fireEvent.pointerDown(
    await screen.findByRole('button', { name: 'More material actions' })
  )
}

const EXTRACTION_FIXTURE = {
  ...MATERIAL,
  extraction: {
    id: 1,
    material_id: 5,
    version: 2,
    extractor: 'ocr',
    markdown: 'body ![drawing](ca-drawing://3)',
    blocks: [{ type: 'text', md: 'body' }],
  },
  drawings: [{ id: 3, png_sha: 'sha3', strokes: [], ocr_version: 1, ocr_markdown: null }],
}

describe('MaterialDetailBody take-notes', () => {
  beforeEach(() => {
    getMaterial.mockReset()
    getMaterialLinks.mockReset()
    listCourses.mockReset()
    listStudyStates.mockReset()
    setStudyState.mockReset()
    deriveMaterial.mockReset()
    navigate.mockReset()
    getMaterial.mockResolvedValue(MATERIAL)
    getMaterialLinks.mockResolvedValue([])
    listCourses.mockResolvedValue([{ id: 2, title: 'Calculus' }])
    listStudyStates.mockResolvedValue({})
  })

  test('Take notes button renders and fires when provided', async () => {
    const onTakeNotes = vi.fn()
    renderBody({ onTakeNotes })
    const button = await screen.findByRole('button', { name: /take notes/i })
    fireEvent.click(button)
    expect(onTakeNotes).toHaveBeenCalled()
  })

  test('header band shows the material title, meta chips and view menu together (plan 62-E)', async () => {
    getMaterialLinks.mockResolvedValue([
      {
        node_id: 9,
        owner_title: 'Derivatives',
        rationale: null,
        breadcrumb: [
          { id: 1, title: 'Calculus' },
          { id: 9, title: 'Derivatives' },
        ],
        is_course_level: false,
      },
    ])
    renderBody({ activeTab: 'extraction' })
    expect(await screen.findByRole('heading', { name: 'Chain rule worksheet' })).toBeInTheDocument()
    expect(screen.getByText('ready')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Switch view' })).toHaveTextContent(
      'Extraction'
    )
    const assigned = screen.getByRole('link', { name: /derivatives/i })
    expect(assigned).toHaveAttribute('title', 'Calculus › Derivatives')
  })

  test('pane close rides the header and uses the given label (plan 62-B)', async () => {
    const onClose = vi.fn()
    renderBody({ onClose, closeLabel: 'Close pane' })
    await screen.findByRole('heading', { name: 'Chain rule worksheet' })
    fireEvent.click(screen.getByRole('button', { name: 'Close pane' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  test('no Take notes button without the callback', async () => {
    renderBody()
    expect(
      await screen.findByTestId('extraction-view')
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /take notes/i })).not.toBeInTheDocument()
  })

  test('Ask AI renders in the top action row when an extraction exists (plan 61-B follow-up)', async () => {
    getMaterial.mockResolvedValue({
      ...MATERIAL,
      extraction: {
        id: 1,
        material_id: 5,
        version: 1,
        extractor: 'ocr',
        markdown: 'body',
        blocks: [{ type: 'text', md: 'body' }],
      },
    })
    renderBody()
    fireEvent.click(
      await screen.findByRole('button', { name: 'Ask the AI about this material' })
    )
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Chain rule worksheet')).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Summarize' })).toBeInTheDocument()
  })

  test('no Ask AI while the material has no extraction', async () => {
    renderBody()
    expect(await screen.findByTestId('extraction-view')).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Ask the AI about this material' })
    ).not.toBeInTheDocument()
  })

  test('reading status is a compact dropdown that switches the state', async () => {
    listStudyStates.mockResolvedValue({ '5': { status: 'reading' } })
    renderBody()
    const trigger = await screen.findByRole('button', { name: 'Reading status' })
    expect(trigger).toHaveTextContent('Reading')
    expect(
      screen.queryByRole('menuitemcheckbox', { name: 'Studied' })
    ).not.toBeInTheDocument()
    fireEvent.pointerDown(trigger)
    fireEvent.click(screen.getByRole('menuitemcheckbox', { name: 'Studied' }))
    await waitFor(() => expect(setStudyState).toHaveBeenCalledWith(5, 'studied'))
  })

  test('Export .md downloads the extraction with embedded drawings (via the ⋯ menu, plan 62-E)', async () => {
    exportMarkdownWithDrawings.mockReset()
    exportMarkdownWithDrawings.mockResolvedValue(
      'body ![drawing](data:image/png;base64,AAA)'
    )
    getMaterial.mockResolvedValue(EXTRACTION_FIXTURE)
    const click = vi.fn()
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(click)
    const objectUrl = vi.fn(() => 'blob:export')
    const originalCreate = URL.createObjectURL
    URL.createObjectURL = objectUrl as unknown as typeof URL.createObjectURL

    renderBody()
    expect(
      screen.queryByRole('button', { name: 'Export .md' })
    ).not.toBeInTheDocument()
    await openMoreMaterialActions()
    const item = await screen.findByRole('menuitem', { name: 'Export .md' })
    expect(item).not.toHaveAttribute('aria-disabled', 'true')
    fireEvent.click(item)

    await waitFor(() =>
      expect(exportMarkdownWithDrawings).toHaveBeenCalledWith(
        'body ![drawing](ca-drawing://3)',
        [{ id: 3, png_sha: 'sha3', strokes: [], ocr_version: 1, ocr_markdown: null }]
      )
    )
    await waitFor(() => expect(click).toHaveBeenCalled())
    const anchor = click.mock.instances[0] as HTMLAnchorElement | undefined
    expect(anchor?.download).toBe('Chain rule worksheet.md')
    URL.createObjectURL = originalCreate
  })

  test('the ⋯ overflow is hidden entirely while the material has no extraction (plan 62-E)', async () => {
    getMaterial.mockResolvedValue(MATERIAL)
    renderBody()
    await screen.findByTestId('extraction-view')
    expect(
      screen.queryByRole('button', { name: 'More material actions' })
    ).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Export .md' })).not.toBeInTheDocument()
  })

  test('Print opens the print document overlay (plan 62-E)', async () => {
    getMaterial.mockResolvedValue(EXTRACTION_FIXTURE)
    renderBody()
    await openMoreMaterialActions()
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Print' }))
    expect(await screen.findByTestId('markdown-print-doc')).toBeInTheDocument()
  })

  test('⋯ menu offers Re-extract for mode-bearing materials and opens the dialog', async () => {
    getMaterial.mockResolvedValue(EXTRACTION_FIXTURE)
    renderBody()
    await openMoreMaterialActions()
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Re-extract…' }))
    expect(await screen.findByTestId('reextract-dialog')).toBeInTheDocument()
    expect(screen.getByTestId('reextract-mode-text')).toBeInTheDocument()
  })

  test('⋯ menu omits Re-extract for materials without mode choice (plan 74-D)', async () => {
    getMaterial.mockResolvedValue({
      ...EXTRACTION_FIXTURE,
      material: { ...EXTRACTION_FIXTURE.material, reextract_modes: ['auto'] },
    })
    renderBody()
    await openMoreMaterialActions()
    expect(await screen.findByRole('menuitem', { name: 'Export .md' })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Re-extract…' })).toBeNull()
  })

  test('History opens the extraction history dialog (plan 62-E)', async () => {
    getMaterial.mockResolvedValue(EXTRACTION_FIXTURE)
    renderBody()
    await openMoreMaterialActions()
    fireEvent.click(await screen.findByRole('menuitem', { name: 'History' }))
    expect(await screen.findByTestId('extraction-history-dialog')).toBeInTheDocument()
  })

  test('mindmap materials get Print and Save as material but no History (plan 62-E)', async () => {
    getMaterial.mockResolvedValue({
      ...EXTRACTION_FIXTURE,
      material: {
        ...MATERIAL.material,
        provenance: { source: 'ai-composed', kind: 'mindmap' },
      },
    })
    renderBody()
    await openMoreMaterialActions()
    expect(await screen.findByRole('menuitem', { name: 'Print' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Save as material' })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'History' })).not.toBeInTheDocument()
  })

  test('derives a new material and offers to open it (plan 62-E)', async () => {
    deriveMaterial.mockResolvedValue({
      material: { id: 12, title: 'Notes (extracted)' },
      job_id: 4,
      deduped: false,
    })
    getMaterial.mockResolvedValue(EXTRACTION_FIXTURE)
    renderBody()

    await openMoreMaterialActions()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Save as material' }))
    await waitFor(() => expect(deriveMaterial).toHaveBeenCalledWith(5, { nodeId: null }))
    expect(
      await screen.findByText('Saved as Notes (extracted)')
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Open' }))
    expect(navigate).toHaveBeenCalledWith(
      expect.objectContaining({ params: { materialId: '12' } })
    )
  })

  test('derive passes the assigned node so the material lands there (plan 62-E)', async () => {
    deriveMaterial.mockResolvedValue({
      material: { id: 12, title: 'Notes (extracted)' },
      job_id: 4,
      deduped: false,
    })
    getMaterial.mockResolvedValue(EXTRACTION_FIXTURE)
    getMaterialLinks.mockResolvedValue([
      {
        node_id: 9,
        owner_title: 'Derivatives',
        rationale: null,
        breadcrumb: [{ id: 1, title: 'Calculus' }],
        is_course_level: false,
      },
    ])
    renderBody()

    await openMoreMaterialActions()
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Save as material' }))
    await waitFor(() => expect(deriveMaterial).toHaveBeenCalledWith(5, { nodeId: 9 }))
  })

  test('derive refreshes the workspace materials tab and tree without a reload (plan 62-E)', async () => {
    deriveMaterial.mockResolvedValue({
      material: { id: 12, title: 'Notes (extracted)' },
      job_id: 4,
      deduped: false,
    })
    getMaterial.mockResolvedValue(EXTRACTION_FIXTURE)
    const treeFn = vi.fn().mockResolvedValue([])
    const workspaceFn = vi.fn().mockResolvedValue({})
    function Probes() {
      useQuery({ queryKey: ['tree'], queryFn: treeFn })
      useQuery({ queryKey: ['node-workspace', '5'], queryFn: workspaceFn })
      return null
    }
    renderBodyWithProbes({}, <Probes />)
    await waitFor(() => expect(treeFn).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(workspaceFn).toHaveBeenCalledTimes(1))

    await openMoreMaterialActions()
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Save as material' }))
    await screen.findByText('Saved as Notes (extracted)')
    await waitFor(() => expect(treeFn).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(workspaceFn).toHaveBeenCalledTimes(2))
  })

  test('derive surfaces the duplicate notice when deduped (plan 62-E)', async () => {
    deriveMaterial.mockResolvedValue({
      material: { id: 12, title: 'Notes (extracted)' },
      job_id: null,
      deduped: true,
    })
    getMaterial.mockResolvedValue(EXTRACTION_FIXTURE)
    renderBody()

    await openMoreMaterialActions()
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Save as material' }))
    expect(
      await screen.findByText('An identical material already exists')
    ).toBeInTheDocument()
  })

  test('derive failure shows an inline error (plan 62-E)', async () => {
    deriveMaterial.mockRejectedValue(new Error('boom'))
    getMaterial.mockResolvedValue(EXTRACTION_FIXTURE)
    renderBody()

    await openMoreMaterialActions()
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Save as material' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not save as material'
    )
  })
})

describe('MaterialDetailBody text-file tabs', () => {
  beforeEach(() => {
    getMaterial.mockReset()
    getMaterialLinks.mockReset()
    listCourses.mockReset()
    listStudyStates.mockReset()
    setStudyState.mockReset()
    getMaterial.mockResolvedValue({
      ...MATERIAL,
      material: {
        ...MATERIAL.material,
        kind: 'md',
        mime: 'text/markdown',
        description: 'A summary of the chain rule',
      },
      extraction: {
        id: 1,
        material_id: 5,
        version: 1,
        extractor: 'text',
        markdown: '# Chain rule\nbody',
        blocks: [{ type: 'text', md: 'body' }],
      },
    })
    getMaterialLinks.mockResolvedValue([])
    listCourses.mockResolvedValue([{ id: 2, title: 'Calculus' }])
    listStudyStates.mockResolvedValue({})
  })

  test('text materials use a view dropdown instead of a tab strip (plan 62-E)', async () => {
    const onTabChange = vi.fn()
    renderBody({ activeTab: 'formatted', onTabChange })
    await screen.findByTestId('extraction-view')
    expect(screen.queryByRole('tab')).not.toBeInTheDocument()

    const trigger = screen.getByRole('button', { name: 'Switch view' })
    expect(trigger).toHaveTextContent('Formatted')
    fireEvent.pointerDown(trigger)
    fireEvent.click(screen.getByRole('menuitemcheckbox', { name: 'Raw text' }))
    expect(onTabChange).toHaveBeenCalledWith('raw')
  })

  test('the legacy extraction tab maps onto Formatted for text materials', async () => {
    renderBody({ activeTab: 'extraction' })
    expect(await screen.findByTestId('extraction-view')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Switch view' })).toHaveTextContent(
      'Formatted'
    )
  })

  test('Raw text shows the markdown source', async () => {
    renderBody({ activeTab: 'raw' })
    expect(await screen.findByText('# Chain rule body')).toBeInTheDocument()
  })

  test('Description renders in the header info popover (plan 62-E)', async () => {
    renderBody({ activeTab: 'formatted' })
    await screen.findByTestId('extraction-view')
    expect(screen.queryByRole('tab', { name: 'Description' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Material description' }))
    expect(
      await screen.findByText('A summary of the chain rule')
    ).toBeInTheDocument()
  })

  test('no description info button when the description is empty (plan 62-E)', async () => {
    getMaterial.mockResolvedValue({
      ...MATERIAL,
      material: { ...MATERIAL.material, kind: 'txt', mime: 'text/plain' },
    })
    renderBody({ activeTab: 'formatted' })
    await screen.findByTestId('extraction-view')
    expect(
      screen.queryByRole('button', { name: 'Material description' })
    ).not.toBeInTheDocument()
  })

  test('non-text materials use the same view dropdown with the three views (plan 62-E)', async () => {
    getMaterial.mockResolvedValue({
      ...MATERIAL,
      material: { ...MATERIAL.material, kind: 'pdf', mime: 'application/pdf' },
    })
    const onTabChange = vi.fn()
    renderBody({ activeTab: 'extraction', onTabChange })
    await screen.findByTestId('extraction-view')
    expect(screen.queryByRole('tab')).not.toBeInTheDocument()

    const trigger = screen.getByRole('button', { name: 'Switch view' })
    expect(trigger).toHaveTextContent('Extraction')
    fireEvent.pointerDown(trigger)
    fireEvent.click(screen.getByRole('menuitemcheckbox', { name: 'Side-by-side' }))
    expect(onTabChange).toHaveBeenCalledWith('side-by-side')
  })
})
