import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { MindmapViewer } from './MindmapViewer'

const transform = vi.fn()
const create = vi.fn()
const fit = vi.fn()
const destroy = vi.fn()
const editExtraction = vi.fn()
const addNode = vi.fn()
const createNote = vi.fn()
const createChatSession = vi.fn()

let mockData: unknown = null
let mockFindElement: () => unknown = () => undefined

vi.mock('markmap-lib', () => ({
  Transformer: class {
    transform(markdown: string) {
      transform(markdown)
      return { root: { content: 'Limits' } }
    }
  },
}))

vi.mock('markmap-view', () => ({
  Markmap: {
    create: (...args: unknown[]) => {
      create(...args)
      return { fit, destroy, state: { data: mockData }, findElement: mockFindElement }
    },
  },
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    editExtraction: (id: number, md: string) => editExtraction(id, md),
    addNode: (id: number, parent: number, title: string) => addNode(id, parent, title),
    createNote: (body: unknown) => createNote(body),
    createChatSession: (courseId: number, nodeId: number, title: string) =>
      createChatSession(courseId, nodeId, title),
  }
})

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => vi.fn(),
  useRouterState: ({ select }: { select: (state: unknown) => unknown }) =>
    select({ location: { href: '/', search: {} } }),
}))

function renderViewer(markdown: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const invalidateSpy = vi.spyOn(client, 'invalidateQueries')
  const utils = render(
    <QueryClientProvider client={client}>
      <MindmapViewer
        markdown={markdown}
        materialId={7}
        materialTitle="Limits map"
        courseId={3}
        scopeNodeId={5}
      />
    </QueryClientProvider>
  )
  return { client, invalidateSpy, ...utils }
}

describe('MindmapViewer', () => {
  beforeEach(() => {
    transform.mockClear()
    create.mockClear()
    fit.mockClear()
    destroy.mockClear()
    editExtraction.mockReset().mockResolvedValue({
      id: 1,
      material_id: 7,
      version: 2,
      extractor: 'compose',
      markdown: '',
      blocks: [],
    })
    addNode.mockReset()
    createNote.mockReset()
    createChatSession.mockReset()
    mockData = null
    mockFindElement = () => undefined
  })

  test('transforms markdown, renders the svg, and exposes a fit control', async () => {
    const markdown = '# Limits\n- definition'
    const { unmount } = renderViewer(markdown)
    await waitFor(() => expect(transform).toHaveBeenCalledWith(markdown))
    expect(create).toHaveBeenCalled()
    expect(screen.getByRole('img')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /fit to view/i }))
    await waitFor(() => expect(fit).toHaveBeenCalled())

    unmount()
    expect(destroy).toHaveBeenCalled()
  })

  test('deleting a selected node saves the updated markdown and invalidates', async () => {
    mockData = { payload: { lines: '2,3' }, children: [] }
    mockFindElement = () => ({ g: { contains: () => true }, data: mockData })
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    const { invalidateSpy } = renderViewer('# Limits\n\n- Definition\n')
    await waitFor(() => expect(transform).toHaveBeenCalled())

    fireEvent.click(screen.getByRole('img'))
    expect(await screen.findByText('Definition')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /delete/i }))

    await waitFor(() => expect(editExtraction).toHaveBeenCalled())
    expect(editExtraction).toHaveBeenCalledWith(7, expect.not.stringContaining('Definition'))
    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['material', 7] })
    )
  })
})
