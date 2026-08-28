import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { MaterialDetailBody } from './MaterialDetailBody'

const getMaterial = vi.fn()
const getMaterialLinks = vi.fn()
const listCourses = vi.fn()
const listStudyStates = vi.fn()
const setStudyState = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getMaterial: (id: number) => getMaterial(id),
    getMaterialLinks: (id: number) => getMaterialLinks(id),
    listCourses: () => listCourses(),
    listStudyStates: () => listStudyStates(),
    setStudyState: (id: number, status: string) => setStudyState(id, status),
  }
})

vi.mock('./ExtractionView', () => ({
  ExtractionView: () => <div data-testid="extraction-view" />,
}))
vi.mock('./OriginalView', () => ({
  OriginalView: () => <div data-testid="original-view" />,
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

describe('MaterialDetailBody take-notes', () => {
  beforeEach(() => {
    getMaterial.mockReset()
    getMaterialLinks.mockReset()
    listCourses.mockReset()
    listStudyStates.mockReset()
    setStudyState.mockReset()
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

  test('no Take notes button without the callback', async () => {
    renderBody()
    expect(
      await screen.findByTestId('extraction-view')
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /take notes/i })).not.toBeInTheDocument()
  })

  test('Export .md downloads the extraction with embedded drawings', async () => {
    exportMarkdownWithDrawings.mockReset()
    exportMarkdownWithDrawings.mockResolvedValue(
      'body ![drawing](data:image/png;base64,AAA)'
    )
    getMaterial.mockResolvedValue({
      material: { id: 5, course_id: 2, title: 'Chain rule worksheet', status: 'ready' },
      extraction: {
        id: 1,
        material_id: 5,
        version: 2,
        extractor: 'ocr',
        markdown: 'body ![drawing](ca-drawing://3)',
        blocks: [{ type: 'text', md: 'body' }],
      },
      index_card: null,
      drawings: [{ id: 3, png_sha: 'sha3', strokes: [], ocr_version: 1, ocr_markdown: null }],
    })
    const click = vi.fn()
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(click)
    const objectUrl = vi.fn(() => 'blob:export')
    const originalCreate = URL.createObjectURL
    URL.createObjectURL = objectUrl as unknown as typeof URL.createObjectURL

    renderBody()
    const button = await screen.findByRole('button', { name: 'Export .md' })
    expect(button).not.toBeDisabled()
    fireEvent.click(button)

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

  test('Export .md is disabled while the material has no extraction', async () => {
    getMaterial.mockResolvedValue(MATERIAL)
    renderBody()
    const button = await screen.findByRole('button', { name: 'Export .md' })
    expect(button).toBeDisabled()
  })
})
