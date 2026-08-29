import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from '@tanstack/react-router'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { LibraryPage } from './LibraryPage'
import { MaterialDetailPage } from './MaterialDetailPage'
import { useWorkspaceStore } from '@/lib/workspace-store'

const listMaterials = vi.fn()
const getMaterial = vi.fn()
const uploadMaterial = vi.fn()
const listFolders = vi.fn()
const createFolder = vi.fn()
const renameFolder = vi.fn()
const deleteFolder = vi.fn()
const getFolderDeleteInfo = vi.fn()
const unlinkFolder = vi.fn()
const editExtraction = vi.fn()
const searchMock = vi.fn()
const listSources = vi.fn()
const scanSource = vi.fn()
const listCourses = vi.fn()
const getMaterialLinks = vi.fn()
const listStudyStates = vi.fn()
const setStudyState = vi.fn()
const browseSource = vi.fn()
const ingestSourceFile = vi.fn()
const relinkSource = vi.fn()
const revealSource = vi.fn()
const addSource = vi.fn()
const createTextMaterial = vi.fn()
const updateTextMaterial = vi.fn()
const renameMaterial = vi.fn()
const deleteMaterial = vi.fn()
const listFsDirs = vi.fn()
const apiFetchMock = vi.fn()
const moveMaterial = vi.fn()
const copyMaterial = vi.fn()
const moveFolder = vi.fn()
const allocateMaterial = vi.fn()
const allocateNodeFolder = vi.fn()
const courseTree = vi.fn()
const reingestMaterialMock = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listMaterials: (...args: unknown[]) => listMaterials(...(args as [])),
    getMaterial: (...args: unknown[]) => getMaterial(...(args as [number])),
    uploadMaterial: (...args: unknown[]) => uploadMaterial(...(args as [])),
    listFolders: (...args: unknown[]) => listFolders(...(args as [])),
    createFolder: (...args: unknown[]) => createFolder(...(args as [])),
    renameFolder: (...args: unknown[]) => renameFolder(...(args as [number, string])),
    deleteFolder: (...args: unknown[]) => deleteFolder(...(args as [number])),
    getFolderDeleteInfo: (...args: unknown[]) => getFolderDeleteInfo(...(args as [number])),
    unlinkFolder: (...args: unknown[]) => unlinkFolder(...(args as [number])),
    editExtraction: (...args: unknown[]) => editExtraction(...(args as [number, string])),
    search: (...args: unknown[]) => searchMock(...(args as [string])),
    listSources: () => listSources(),
    scanSource: (...args: unknown[]) => scanSource(...(args as [number])),
    listCourses: () => listCourses(),
    getMaterialLinks: (...args: unknown[]) => getMaterialLinks(...(args as [number])),
    listStudyStates: () => listStudyStates(),
    setStudyState: (...args: unknown[]) => setStudyState(...(args as [])),
    browseSource: (...args: unknown[]) => browseSource(...(args as [])),
    ingestSourceFile: (...args: unknown[]) => ingestSourceFile(...(args as [])),
    relinkSource: (...args: unknown[]) => relinkSource(...(args as [])),
    revealSource: (...args: unknown[]) => revealSource(...(args as [number])),
    addSource: (...args: unknown[]) => addSource(...(args as [])),
    createTextMaterial: (...args: unknown[]) => createTextMaterial(...(args as [])),
    updateTextMaterial: (...args: unknown[]) => updateTextMaterial(...(args as [])),
    renameMaterial: (...args: unknown[]) => renameMaterial(...(args as [])),
    deleteMaterial: (...args: unknown[]) => deleteMaterial(...(args as [number])),
    listFsDirs: (...args: unknown[]) => listFsDirs(...(args as [])),
    moveMaterial: (...args: unknown[]) => moveMaterial(...(args as [number, number | null])),
    copyMaterial: (...args: unknown[]) => copyMaterial(...(args as [number, number | null])),
    moveFolder: (...args: unknown[]) => moveFolder(...(args as [number, number | null])),
    allocateMaterial: (...args: unknown[]) => allocateMaterial(...(args as [number, number])),
    allocateNodeFolder: (...args: unknown[]) =>
      allocateNodeFolder(...(args as [number, number])),
    courseTree: (...args: unknown[]) => courseTree(...(args as [number])),
    reingestMaterial: (...args: unknown[]) =>
      reingestMaterialMock(...(args as [number])),
    apiFetch: (...args: unknown[]) => apiFetchMock(...(args as [])),
  }
})

vi.mock('@/lib/ws-client', () => ({
  getWsClient: () => ({
    subscribe: vi.fn(() => () => undefined),
  }),
}))

vi.mock('@/components/editor/LazyMarkdownEditor', () => ({
  LazyMarkdownEditor: ({
    value,
    onChange,
    ariaLabel,
  }: {
    value: string
    onChange: (markdown: string) => void
    ariaLabel: string
  }) => (
    <input
      aria-label={ariaLabel}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  ),
}))

const COURSES = [
  {
    id: 3,
    title: 'Calculus I',
    subject: null,
    level: null,
    description: null,
    color: null,
    archived_at: null,
    material_count: 2,
  },
]

const FOLDERS = [
  { id: 11, name: 'Lectures', path: 'Lectures', course_id: 3, parent_id: null, created_at: '', source_id: null },
  {
    id: 12,
    name: 'Week 1',
    path: 'Lectures/Week 1',
    course_id: 3,
    parent_id: 11,
    created_at: '',
    source_id: null,
  },
  {
    id: 13,
    name: 'My Lectures',
    path: 'My Lectures',
    course_id: 3,
    parent_id: null,
    created_at: '',
    source_id: 77,
  },
]

const MATERIAL = {
  id: 7,
  title: 'chain-rule.pdf',
  kind: 'pdf',
  status: 'ready',
  filename: 'chain-rule.pdf',
  mime: 'application/pdf',
  pages: 1,
  course_id: 3,
  group_id: null,
  folder_id: null,
  blob_sha: 'a'.repeat(64),
  created_at: '2026-08-18T00:00:00Z',
}

const DETAIL = {
  material: MATERIAL,
  extraction: {
    id: 1,
    material_id: 7,
    version: 1,
    extractor: 'pymupdf',
    markdown: 'the **chain rule**',
    blocks: [{ type: 'text', md: 'the **chain rule**' }],
  },
  index_card: null,
}

function makeRouter(initial: string) {
  const rootRoute = createRootRoute()
  const libraryRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/library',
    validateSearch: (search: Record<string, unknown>): { course?: number; folder?: number } => ({
      course: typeof search.course === 'number' ? search.course : undefined,
      folder: typeof search.folder === 'number' ? search.folder : undefined,
    }),
    component: LibraryPage,
  })
  const materialRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/library/$materialId',
    validateSearch: (search: Record<string, unknown>): { tab?: string } => ({
      tab: typeof search.tab === 'string' ? search.tab : undefined,
    }),
    component: MaterialDetailPage,
  })
  return createRouter({
    routeTree: rootRoute.addChildren([libraryRoute, materialRoute]),
    history: createMemoryHistory({ initialEntries: [initial] }),
  })
}

function renderAt(initial: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = makeRouter(initial)
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}

afterEach(() => {
  useWorkspaceStore.getState().setCourse(null)
  window.localStorage.clear()
  vi.clearAllMocks()
})

describe('LibraryPage', () => {
  test('root shows course cards', async () => {
    listCourses.mockResolvedValue(COURSES)
    listSources.mockResolvedValue([])
    renderAt('/library')
    expect(await screen.findByText('Calculus I')).toBeInTheDocument()
    expect(screen.getByText('1 course')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Grid view' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /upload/i })).not.toBeInTheDocument()
  })

  test('navigating into a course shows folders and unfiled materials', async () => {
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue(FOLDERS)
    listMaterials.mockResolvedValue([MATERIAL])
    listSources.mockResolvedValue([])
    renderAt('/library?course=3')
    expect(await screen.findByText('Lectures')).toBeInTheDocument()
    expect(await screen.findByText('chain-rule.pdf')).toBeInTheDocument()
    await waitFor(() => expect(listMaterials).toHaveBeenCalledWith(undefined, 3, true))
    expect(await screen.findByText('2 folders · 1 materials')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Upload$/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'New…' })).toBeInTheDocument()
  })

  test('workspace store course is applied on entry', async () => {
    useWorkspaceStore.getState().setCourse(3)
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue([])
    listMaterials.mockResolvedValue([])
    listSources.mockResolvedValue([])
    renderAt('/library')
    await waitFor(() => expect(listFolders).toHaveBeenCalledWith(3))
    expect(await screen.findByRole('button', { name: 'New…' })).toBeInTheDocument()
  })

  test('uploading from the pane menu sends files to the current folder and refreshes', async () => {
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue(FOLDERS)
    listMaterials.mockResolvedValue([])
    listSources.mockResolvedValue([])
    uploadMaterial.mockResolvedValue({
      material: MATERIAL,
      job_id: null,
      deduped: false,
    })
    renderAt('/library?course=3&folder=11')
    expect(await screen.findByRole('button', { name: 'New…' })).toBeEnabled()

    const uploadInputs = screen.getAllByLabelText('Upload files')
    expect(uploadInputs.length).toBeGreaterThan(0)
    fireEvent.change(uploadInputs[0], {
      target: { files: [new File(['data'], 'sheet.pdf', { type: 'application/pdf' })] },
    })
    await waitFor(() => expect(uploadMaterial).toHaveBeenCalledTimes(1))
    expect(uploadMaterial.mock.calls[0][1]).toBe(3)
    expect(uploadMaterial.mock.calls[0][2]).toBe(11)
    await waitFor(() => expect(listMaterials).toHaveBeenCalledWith(11))
  })

  test('pane menu upload entries trigger the file and folder pickers', async () => {
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue([])
    listMaterials.mockResolvedValue([])
    listSources.mockResolvedValue([])
    renderAt('/library?course=3')
    fireEvent.click(await screen.findByRole('button', { name: 'New…' }))

    expect(await screen.findByRole('menuitem', { name: 'Upload files…' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Upload$/ })).not.toBeInTheDocument()

    const clickSpy = vi.spyOn(HTMLInputElement.prototype, 'click').mockImplementation(() => {})
    fireEvent.click(screen.getByRole('menuitem', { name: 'Upload files…' }))
    expect(clickSpy).toHaveBeenCalled()
    clickSpy.mockClear()

    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'New…' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Upload folder…' }))
    expect(clickSpy).toHaveBeenCalled()
    clickSpy.mockRestore()
  })

  test('folder navigation and breadcrumbs', async () => {
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue(FOLDERS)
    listMaterials.mockResolvedValue([])
    listSources.mockResolvedValue([])
    renderAt('/library?course=3')
    fireEvent.doubleClick(await screen.findByText('Lectures'))
    expect(await screen.findByText('Week 1')).toBeInTheDocument()
    await waitFor(() => expect(listMaterials).toHaveBeenCalledWith(11))
    expect(screen.getByText('Calculus I')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Calculus I'))
    await waitFor(() => expect(listMaterials).toHaveBeenCalledWith(undefined, 3, true))
  })

  test('single click selects without opening; double click opens the material', async () => {
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue(FOLDERS)
    listMaterials.mockResolvedValue([MATERIAL])
    listSources.mockResolvedValue([])
    getMaterial.mockResolvedValue(DETAIL)
    getMaterialLinks.mockResolvedValue([])
    listStudyStates.mockResolvedValue({})
    renderAt('/library?course=3')
    expect(await screen.findByText('chain-rule.pdf')).toBeInTheDocument()

    fireEvent.mouseDown(screen.getByText('chain-rule.pdf'))
    fireEvent.click(screen.getByText('chain-rule.pdf'), { detail: 1 })
    expect(
      await screen.findByText('1 item selected — click to clear')
    ).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'chain-rule.pdf' })).not.toBeInTheDocument()

    fireEvent.doubleClick(screen.getByText('chain-rule.pdf'))
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'chain-rule.pdf' })).toBeInTheDocument()
    )
  })

  test('Enter opens the single selected folder', async () => {
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue(FOLDERS)
    listMaterials.mockResolvedValue([])
    listSources.mockResolvedValue([])
    renderAt('/library?course=3')
    expect(await screen.findByText('Lectures')).toBeInTheDocument()

    fireEvent.mouseDown(screen.getByText('Lectures'))
    expect(
      await screen.findByText('1 item selected — click to clear')
    ).toBeInTheDocument()

    fireEvent.keyDown(window, { key: 'Enter' })
    expect(await screen.findByText('Week 1')).toBeInTheDocument()
  })

  test('grid and list toggle persists', async () => {
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue([])
    listMaterials.mockResolvedValue([])
    listSources.mockResolvedValue([])
    renderAt('/library?course=3')
    fireEvent.click(await screen.findByRole('button', { name: 'List view' }))
    await waitFor(() =>
      expect(window.localStorage.getItem('ca-library-view')).toBe('list')
    )
  })

  test('folder context menu rename and delete', async () => {
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue(FOLDERS.slice(0, 1))
    listMaterials.mockResolvedValue([])
    listSources.mockResolvedValue([])
    renameFolder.mockResolvedValue(FOLDERS[0])
    deleteFolder.mockResolvedValue(undefined)
    getFolderDeleteInfo.mockResolvedValue({ subfolders: 0, materials: 0, node_links: [] })
    renderAt('/library?course=3')
    const folderTile = await screen.findByText('Lectures')
    fireEvent.contextMenu(folderTile.closest('button')!)
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Rename folder' }))
    const input = await screen.findByDisplayValue('Lectures')
    expect(input.tagName).toBe('TEXTAREA')
    fireEvent.change(input, { target: { value: 'Lects' } })
    fireEvent.submit(input.closest('form')!)
    await waitFor(() => expect(renameFolder).toHaveBeenCalledWith(11, 'Lects'))

    fireEvent.contextMenu((await screen.findByText('Lectures')).closest('button')!)
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Rename folder' }))
    const multiline = await screen.findByDisplayValue('Lectures')
    fireEvent.change(multiline, { target: { value: 'Lecture\nNotes' } })
    fireEvent.submit(multiline.closest('form')!)
    await waitFor(() => expect(renameFolder).toHaveBeenCalledWith(11, 'Lecture Notes'))

    fireEvent.contextMenu((await screen.findByText('Lectures')).closest('button')!)
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Delete folder' }))
    const dialog = await screen.findByRole('dialog', { name: 'Delete folder' })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete folder and contents' }))
    await waitFor(() => expect(deleteFolder).toHaveBeenCalledWith(11, true))
  })

  test('folder delete refusal surfaces the backend message', async () => {
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue(FOLDERS.slice(0, 1))
    listMaterials.mockResolvedValue([])
    listSources.mockResolvedValue([])
    getFolderDeleteInfo.mockResolvedValue({ subfolders: 0, materials: 0, node_links: [] })
    deleteFolder.mockRejectedValue(
      new Error('folder is assigned to nodes — unassign it there first')
    )
    renderAt('/library?course=3')
    const folderTile = (await screen.findByText('Lectures')).closest('button')!
    fireEvent.contextMenu(folderTile)
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Delete folder' }))
    const dialog = await screen.findByRole('dialog', { name: 'Delete folder' })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete folder and contents' }))
    expect(
      await screen.findByText('folder is assigned to nodes — unassign it there first')
    ).toBeInTheDocument()
  })

  test('assigned folder delete shows linked paths and force-deletes via dialog', async () => {
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue(FOLDERS.slice(0, 1))
    listMaterials.mockResolvedValue([])
    listSources.mockResolvedValue([])
    getFolderDeleteInfo.mockResolvedValue({
      subfolders: 1,
      materials: 1,
      node_links: [
        {
          node_id: 14,
          owner_title: 'Limits',
          breadcrumb: [
            { id: 2, title: 'Calculus' },
            { id: 14, title: 'Limits' },
          ],
          is_course_level: false,
          course_title: 'Calculus',
          folder_count: 1,
          material_count: 0,
        },
      ],
    })
    deleteFolder.mockResolvedValue(undefined)
    renderAt('/library?course=3')
    const folderTile = (await screen.findByText('Lectures')).closest('button')!
    fireEvent.contextMenu(folderTile)
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Delete folder' }))
    const dialog = await screen.findByRole('dialog', { name: 'Delete folder' })
    expect(await within(dialog).findByText('Calculus / Limits')).toBeInTheDocument()
    expect(await within(dialog).findByText('1 folder')).toBeInTheDocument()
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Delete folder and contents' })
    )
    await waitFor(() => expect(deleteFolder).toHaveBeenCalledWith(11, true))
    await waitFor(() => expect(dialog).not.toBeInTheDocument())
  })

  test('search replaces the pane with results', async () => {
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue([])
    listMaterials.mockResolvedValue([])
    listSources.mockResolvedValue([])
    searchMock.mockResolvedValue({
      query: 'limits',
      hits: [{ material_id: 7, title: 'chain-rule.pdf', snippet: '…chain rule…', score: 0.5 }],
    })
    renderAt('/library?course=3')
    fireEvent.click(await screen.findByRole('button', { name: 'Search' }))
    const input = await screen.findByPlaceholderText('Search all materials…')
    fireEvent.change(input, { target: { value: 'limits' } })
    expect(await screen.findByText('…chain rule…')).toBeInTheDocument()
    expect(screen.getAllByText('1 result').length).toBeGreaterThan(0)
  })

  test('zero courses shows the workspace gate', async () => {
    listCourses.mockResolvedValue([])
    renderAt('/library')
    expect(await screen.findByText('No course yet')).toBeInTheDocument()
  })

  test('pane context menu offers create, upload and link actions', async () => {
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue([])
    listMaterials.mockResolvedValue([])
    const pane = await renderAtPane('/library?course=3')
    fireEvent.contextMenu(pane)
    for (const label of [
      'New folder',
      'New text file',
      'New Markdown file',
      'Upload files…',
      'Upload folder…',
      'Add linked folder…',
    ]) {
      expect(await screen.findByRole('menuitem', { name: label })).toBeInTheDocument()
    }
    fireEvent.keyDown(window, { key: 'Escape' })
  })

  test('pane context menu opens when right-clicking the empty-state text', async () => {
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue([])
    listMaterials.mockResolvedValue([])
    renderAt('/library?course=3')
    const text = await screen.findByText(
      'No materials here yet — drop in a PDF to get started.'
    )
    fireEvent.contextMenu(text)
    for (const label of [
      'New folder',
      'New text file',
      'New Markdown file',
      'Upload files…',
      'Upload folder…',
      'Add linked folder…',
    ]) {
      expect(await screen.findByRole('menuitem', { name: label })).toBeInTheDocument()
    }
    fireEvent.keyDown(window, { key: 'Escape' })
  })

  test('dropping files on the pane opens the upload menu with auto-detected options', async () => {
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue([])
    listMaterials.mockResolvedValue([])
    uploadMaterial.mockResolvedValue({
      material: {
        id: 51,
        title: 'notes.pdf',
        kind: 'pdf',
        status: 'ready',
        course_id: 3,
        folder_id: null,
        created_at: '2026-08-19T00:00:00Z',
      },
      job_id: null,
      deduped: false,
    })
    renderAt('/library?course=3')
    await screen.findByText('No materials here yet — drop in a PDF to get started.')

    const pane = document.querySelector(
      '.mx-auto [data-marquee-surface]:not([class*="flex-1"])'
    ) as HTMLElement
    const file = new File(['x'], 'notes.pdf')
    const transfer = {
      types: ['Files'],
      items: [file],
      files: [file],
    } as unknown as DataTransfer
    fireEvent.drop(pane, {
      clientX: 120,
      clientY: 140,
      dataTransfer: transfer,
    })

    expect(await screen.findByRole('menuitem', { name: 'Upload files…' })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Upload folder…' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Upload files…' }))
    await waitFor(() => expect(uploadMaterial).toHaveBeenCalledTimes(1))
    fireEvent.keyDown(window, { key: 'Escape' })
  })

  test('dropping a folder on the pane offers the folder upload option', async () => {
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue([])
    listMaterials.mockResolvedValue([])
    createFolder.mockResolvedValue({
      id: 61,
      name: 'pack',
      path: 'pack',
      course_id: 3,
      parent_id: null,
      source_id: null,
      created_at: '2026-08-19T00:00:00Z',
    })
    uploadMaterial.mockResolvedValue({
      material: {
        id: 52,
        title: 'a.pdf',
        kind: 'pdf',
        status: 'ready',
        course_id: 3,
        folder_id: null,
        created_at: '2026-08-19T00:00:00Z',
      },
      job_id: null,
      deduped: false,
    })
    renderAt('/library?course=3')
    await screen.findByText('No materials here yet — drop in a PDF to get started.')

    const pane = document.querySelector(
      '.mx-auto [data-marquee-surface]:not([class*="flex-1"])'
    ) as HTMLElement
    const file = new File(['x'], 'a.pdf')
    Object.defineProperty(file, 'webkitRelativePath', { value: 'pack/a.pdf' })
    const dirEntry = {
      isFile: false,
      isDirectory: true,
      name: 'pack',
      createReader: () => {
        const children = [
          { isFile: true, isDirectory: false, name: 'a.pdf', file: (ok: (f: File) => void) => ok(file) },
        ]
        return {
          readEntries: (success: (entries: unknown[]) => void) => {
            success(children.slice())
            children.length = 0
          },
        }
      },
    }
    const transfer = {
      types: ['Files'],
      items: [{ webkitGetAsEntry: () => dirEntry }],
      files: [file],
    } as unknown as DataTransfer
    fireEvent.drop(pane, {
      clientX: 120,
      clientY: 140,
      dataTransfer: transfer,
    })

    expect(await screen.findByRole('menuitem', { name: 'Upload folder…' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Upload files…' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Upload folder…' }))
    await waitFor(() => expect(uploadMaterial).toHaveBeenCalledTimes(1))
    fireEvent.keyDown(window, { key: 'Escape' })
  })

  test('plus button opens the same create menu as right-click', async () => {
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue([])
    listMaterials.mockResolvedValue([])
    renderAt('/library?course=3')
    fireEvent.click(await screen.findByRole('button', { name: 'New…' }))
    for (const label of [
      'New folder',
      'New text file',
      'New Markdown file',
      'Upload files…',
      'Upload folder…',
      'Add linked folder…',
    ]) {
      expect(await screen.findByRole('menuitem', { name: label })).toBeInTheDocument()
    }
    fireEvent.keyDown(window, { key: 'Escape' })
  })

  test('new text file dialog creates a file', async () => {
    createTextMaterial.mockResolvedValue({
      materialId: 7,
      content: '$x^2$ rules',
      refToReal: {},
      jobId: null,
    })
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue([])
    listMaterials.mockResolvedValue([])
    const pane = await renderAtPane('/library?course=3')
    fireEvent.contextMenu(pane)
    fireEvent.click(await screen.findByRole('menuitem', { name: 'New Markdown file' }))
    const nameInput = await screen.findByPlaceholderText('File name')
    fireEvent.change(nameInput, { target: { value: 'derivation' } })
    const contentBox = screen.getByLabelText('File content (markdown + LaTeX)')
    fireEvent.change(contentBox, { target: { value: '$x^2$ rules' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    await waitFor(() =>
      expect(createTextMaterial).toHaveBeenCalledWith({
        course_id: 3,
        folder_id: null,
        filename: 'derivation.md',
        content: '$x^2$ rules',
        drawings: [],
      })
    )
  })

  test('material context menu renames and deletes', async () => {
    renameMaterial.mockResolvedValue({ ...MATERIAL, title: 'Renamed' })
    deleteMaterial.mockResolvedValue(undefined)
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue([])
    listMaterials.mockResolvedValue([MATERIAL])
    renderAt('/library?course=3')
    const tile = (await screen.findByText('chain-rule.pdf')).closest('button')!
    fireEvent.contextMenu(tile)
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Rename' }))
    const input = await screen.findByDisplayValue('chain-rule.pdf')
    fireEvent.change(input, { target: { value: 'Renamed' } })
    fireEvent.submit(input.closest('form')!)
    await waitFor(() => expect(renameMaterial).toHaveBeenCalledWith(7, 'Renamed'))

    fireEvent.contextMenu((await screen.findByText('chain-rule.pdf')).closest('button')!)
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Delete' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(deleteMaterial).toHaveBeenCalledWith(7))
  })

  test('right-click on an unselected file offers re-ingest without its name', async () => {
    reingestMaterialMock.mockResolvedValue({ job_id: 9, material_id: 7, deduped: false })
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue([])
    listMaterials.mockResolvedValue([MATERIAL])
    renderAt('/library?course=3')
    const tile = (await screen.findByText('chain-rule.pdf')).closest('button')!
    fireEvent.contextMenu(tile)
    const item = await screen.findByRole('menuitem', {
      name: 'Re-ingest this file (OCR again)',
    })
    expect(screen.queryByRole('menuitem', { name: /chain-rule/ })).toBeNull()
    fireEvent.click(item)
    await waitFor(() => expect(reingestMaterialMock).toHaveBeenCalledWith(7))
  })

  test('right-click on a multi-selection re-ingests every file-backed row', async () => {
    reingestMaterialMock.mockResolvedValue({ job_id: 9, material_id: 7, deduped: false })
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue([])
    listMaterials.mockResolvedValue([
      MATERIAL,
      { ...MATERIAL, id: 8, title: 'limits.pdf', filename: 'limits.pdf' },
    ])
    renderAt('/library?course=3')
    const tile = (await screen.findByText('chain-rule.pdf')).closest('button')!
    fireEvent.mouseDown(tile)
    const otherTile = (await screen.findByText('limits.pdf')).closest('button')!
    fireEvent.mouseDown(otherTile, { ctrlKey: true })
    fireEvent.contextMenu(tile)
    const item = await screen.findByRole('menuitem', {
      name: 'Re-ingest 2 files (OCR again)',
    })
    fireEvent.click(item)
    await waitFor(() => expect(reingestMaterialMock).toHaveBeenCalledTimes(2))
    expect(reingestMaterialMock).toHaveBeenCalledWith(7)
    expect(reingestMaterialMock).toHaveBeenCalledWith(8)
  })

  test('link node navigates via browse, shows pending, ingests', async () => {
    browseSource.mockResolvedValue({
      source_id: 77,
      label: 'My Lectures',
      path: '/home/you/lectures',
      subdir: '',
      missing_target: false,
      subdirs: [{ name: 'week1' }],
      materials: [
        {
          id: 9,
          title: 'board.png',
          kind: 'image',
          status: 'ready',
          filename: 'board.png',
          relpath: 'board.png',
        },
      ],
      uningested: [
        { name: 'new-scan.pdf', relpath: 'new-scan.pdf', size_bytes: 10, mtime: 1 },
      ],
    })
    ingestSourceFile.mockResolvedValue({
      material_id: 12,
      job_id: null,
      deduped: false,
    })
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue(FOLDERS)
    listMaterials.mockResolvedValue([])
    renderAt('/library?course=3')
    fireEvent.doubleClick(await screen.findByText('My Lectures'))
    expect(await screen.findByText('week1')).toBeInTheDocument()
    expect(await screen.findByText('board.png')).toBeInTheDocument()
    expect(await screen.findByText('new-scan.pdf')).toBeInTheDocument()
    expect(await screen.findByText('1 folders · 1 materials · 1 pending')).toBeInTheDocument()
    await waitFor(() => expect(browseSource).toHaveBeenCalledWith(77, ''))
    fireEvent.click(screen.getByRole('button', { name: 'Ingest 1 file' }))
    await waitFor(() =>
      expect(ingestSourceFile).toHaveBeenCalledWith(77, 'new-scan.pdf')
    )
  })

  test('link node context menu rescans and unlinks', async () => {
    browseSource.mockResolvedValue({
      source_id: 77,
      label: 'My Lectures',
      path: '/home/you/lectures',
      subdir: '',
      missing_target: false,
      subdirs: [],
      materials: [],
      uningested: [],
    })
    scanSource.mockResolvedValue({
      stats: { new: 0, updated: 0, unchanged: 0, missing: 0 },
      queued_jobs: 0,
    })
    unlinkFolder.mockResolvedValue(undefined)
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue(FOLDERS)
    listMaterials.mockResolvedValue([])
    renderAt('/library?course=3')
    const tile = (await screen.findByText('My Lectures')).closest('button')!
    fireEvent.contextMenu(tile)
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Rescan' }))
    await waitFor(() => expect(scanSource).toHaveBeenCalledWith(77))

    fireEvent.contextMenu(tile)
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Unlink' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Unlink' }))
    await waitFor(() => expect(unlinkFolder).toHaveBeenCalledWith(13))
  })

  test('dangling link shows missing target and relink dialog', async () => {
    browseSource.mockResolvedValue({
      source_id: 77,
      label: 'My Lectures',
      path: '/gone/lectures',
      subdir: '',
      missing_target: true,
      subdirs: [],
      materials: [],
      uningested: [],
    })
    relinkSource.mockResolvedValue({
      id: 77,
      label: 'My Lectures',
      path: '/new/lectures',
      recursive: true,
      include_globs: null,
      course_id: 3,
      enabled: true,
      material_count: 0,
      last_scanned_at: null,
    })
    listFsDirs.mockResolvedValue({
      path: '/home/you',
      parent: '/home',
      home: '/home/you',
      dirs: [{ name: 'lectures', path: '/home/you/lectures' }],
    })
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue(FOLDERS)
    listMaterials.mockResolvedValue([])
    renderAt('/library?course=3')
    fireEvent.click(await screen.findByText('My Lectures'))
    expect(
      await screen.findByText('Target folder is missing: /gone/lectures')
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Re-link/ }))
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toBeInTheDocument()
    fireEvent.click(await within(dialog).findByText('lectures'))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Choose' }))
    await waitFor(() => expect(relinkSource).toHaveBeenCalledWith(77, '/home/you/lectures'))
  })

  test('add linked folder opens the picker and creates a source', async () => {
    addSource.mockResolvedValue({
      id: 78,
      label: 'lectures',
      path: '/home/you/lectures',
      recursive: true,
      include_globs: null,
      course_id: 3,
      enabled: true,
      material_count: 0,
      last_scanned_at: null,
    })
    listFsDirs.mockImplementation((path?: string) => {
      if (path === '/home/you/lectures') {
        return Promise.resolve({
          path: '/home/you/lectures',
          parent: '/home/you',
          home: '/home/you',
          dirs: [],
        })
      }
      return Promise.resolve({
        path: path ?? '/home/you',
        parent: path ? path.split('/').slice(0, -1).join('/') || null : null,
        home: '/home/you',
        dirs: [{ name: 'lectures', path: '/home/you/lectures' }],
      })
    })
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue([])
    listMaterials.mockResolvedValue([])
    const pane = await renderAtPane('/library?course=3')
    fireEvent.contextMenu(pane)
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Add linked folder…' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(await within(dialog).findByText('lectures'))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Choose' }))
    await waitFor(() =>
      expect(addSource).toHaveBeenCalledWith({
        label: 'lectures',
        path: '/home/you/lectures',
        course_id: 3,
      })
    )
  })

  test('folder picker breadcrumbs navigate the filesystem path', async () => {
    listFsDirs.mockImplementation((path?: string) =>
      Promise.resolve({
        path: path ?? '/home/you/lectures',
        parent: '/home/you',
        home: '/home/you/lectures',
        dirs: [],
      })
    )
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue([])
    listMaterials.mockResolvedValue([])
    const pane = await renderAtPane('/library?course=3')
    fireEvent.contextMenu(pane)
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Add linked folder…' }))
    const dialog = await screen.findByRole('dialog')
    expect(await within(dialog).findByText('lectures')).toBeInTheDocument()
    expect(within(dialog).getByText('you')).toBeInTheDocument()
    fireEvent.click(within(dialog).getByText('you'))
    await waitFor(() => expect(listFsDirs).toHaveBeenCalledWith('/home/you'))
    fireEvent.click(within(dialog).getByText('/'))
    await waitFor(() => expect(listFsDirs).toHaveBeenCalledWith('/'))
  })
  test('marquee drag over the pane selects items and the footer counts them', async () => {
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue(FOLDERS)
    listMaterials.mockResolvedValue([MATERIAL])
    listSources.mockResolvedValue([])
    const rectSpy = vi
      .spyOn(Element.prototype, 'getBoundingClientRect')
      .mockReturnValue({
        left: 0, top: 0, right: 400, bottom: 400, width: 400, height: 400, x: 0, y: 0,
        toJSON: () => ({}),
      } as DOMRect)
    renderAt('/library?course=3')
    expect(await screen.findByText('chain-rule.pdf')).toBeInTheDocument()

    const pane = document.querySelector('[data-marquee-surface]') as HTMLElement
    fireEvent.mouseDown(pane, { clientX: 0, clientY: 0, button: 0 })
    fireEvent.mouseMove(window, { clientX: 200, clientY: 200 })
    fireEvent.mouseUp(window, { clientX: 200, clientY: 200 })

    expect(await screen.findByText(/3 items selected/)).toBeInTheDocument()
    fireEvent.click(screen.getByText(/3 items selected/))
    expect(screen.queryByText(/selected/)).not.toBeInTheDocument()
    rectSpy.mockRestore()
  })

  test('cut then paste into a folder moves the material', async () => {
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue(FOLDERS)
    listMaterials.mockResolvedValue([MATERIAL])
    listSources.mockResolvedValue([])
    moveMaterial.mockResolvedValue(MATERIAL)
    renderAt('/library?course=3')
    expect(await screen.findByText('chain-rule.pdf')).toBeInTheDocument()

    fireEvent.contextMenu(screen.getByText('chain-rule.pdf'))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Cut' }))

    fireEvent.contextMenu(screen.getByText('Lectures'))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Paste into folder' }))

    await waitFor(() => expect(moveMaterial).toHaveBeenCalledWith(7, 11))
  })

  test('copy then paste into a folder duplicates the material', async () => {
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue(FOLDERS)
    listMaterials.mockResolvedValue([MATERIAL])
    listSources.mockResolvedValue([])
    copyMaterial.mockResolvedValue(MATERIAL)
    renderAt('/library?course=3')
    expect(await screen.findByText('chain-rule.pdf')).toBeInTheDocument()

    fireEvent.contextMenu(screen.getByText('chain-rule.pdf'))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Copy' }))

    fireEvent.contextMenu(screen.getByText('Lectures'))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Paste into folder' }))

    await waitFor(() => expect(copyMaterial).toHaveBeenCalledWith(7, 11))
    expect(moveMaterial).not.toHaveBeenCalled()
  })

  test('keyboard delete removes the selection after confirm', async () => {
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue(FOLDERS)
    listMaterials.mockResolvedValue([MATERIAL])
    listSources.mockResolvedValue([])
    renderAt('/library?course=3')
    expect(await screen.findByText('chain-rule.pdf')).toBeInTheDocument()

    fireEvent.mouseDown(screen.getByText('chain-rule.pdf'))
    fireEvent.keyDown(window, { key: 'Delete' })
    fireEvent.click(await screen.findByRole('button', { name: 'Remove' }))

    await waitFor(() => expect(deleteMaterial).toHaveBeenCalledWith(7))
  })

  test('ctrl+x then ctrl+v moves the selection into the open folder', async () => {
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue(FOLDERS)
    listMaterials.mockResolvedValue([MATERIAL])
    listSources.mockResolvedValue([])
    moveMaterial.mockResolvedValue(MATERIAL)
    renderAt('/library?course=3&folder=11')
    expect(await screen.findByText('chain-rule.pdf')).toBeInTheDocument()

    fireEvent.mouseDown(screen.getByText('chain-rule.pdf'))
    fireEvent.keyDown(window, { key: 'x', ctrlKey: true })
    fireEvent.keyDown(window, { key: 'v', ctrlKey: true })

    await waitFor(() => expect(moveMaterial).toHaveBeenCalledWith(7, 11))
  })

  test('dropping a dragged material onto a folder moves it there', async () => {
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue(FOLDERS)
    listMaterials.mockResolvedValue([MATERIAL])
    listSources.mockResolvedValue([])
    moveMaterial.mockResolvedValue(MATERIAL)
    renderAt('/library?course=3')
    expect(await screen.findByText('chain-rule.pdf')).toBeInTheDocument()

    const payload = JSON.stringify({ folderIds: [], materialIds: [7] })
    const dataTransfer = {
      types: ['application/x-ca-item'],
      getData: (mime: string) =>
        mime === 'application/x-ca-item' ? payload : '',
      setData: vi.fn(),
      effectAllowed: '',
    }
    const material = screen.getByText('chain-rule.pdf').closest('[data-selectable-id]')
    expect(material).not.toBeNull()
    fireEvent.dragStart(material as Element, { dataTransfer })
    const folder = screen.getByText('Lectures').closest('button')
    expect(folder).not.toBeNull()
    fireEvent.dragOver(folder as Element, { dataTransfer })
    fireEvent.drop(folder as Element, { dataTransfer })

    await waitFor(() => expect(moveMaterial).toHaveBeenCalledWith(7, 11))
  })

  test('assign to node assigns every selected material', async () => {
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue(FOLDERS)
    listMaterials.mockResolvedValue([MATERIAL])
    listSources.mockResolvedValue([])
    courseTree.mockResolvedValue([
      {
        id: 50,
        title: 'Calculus I',
        summary: null,
        objectives: [],
        order_idx: 0,
        depth: 0,
        is_root: true,
        children: [
          {
            id: 51,
            title: 'Chapter 1',
            summary: null,
            objectives: [],
            order_idx: 0,
            depth: 1,
            is_root: false,
            children: [],
            materials: [],
          },
        ],
        materials: [],
      },
    ])
    allocateMaterial.mockResolvedValue(undefined)
    renderAt('/library?course=3')
    expect(await screen.findByText('chain-rule.pdf')).toBeInTheDocument()

    fireEvent.contextMenu(screen.getByText('chain-rule.pdf'))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Assign to node…' }))

    fireEvent.click(await screen.findByRole('treeitem', { name: /Chapter 1/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Assign' }))

    await waitFor(() => expect(allocateMaterial).toHaveBeenCalledWith(51, 7))
    await waitFor(() =>
      expect(screen.getByText('Assigned to node')).toBeInTheDocument()
    )
  })

  test('assign folder to node assigns the whole folder selection', async () => {
    listCourses.mockResolvedValue(COURSES)
    listFolders.mockResolvedValue(FOLDERS)
    listMaterials.mockResolvedValue([MATERIAL])
    listSources.mockResolvedValue([])
    courseTree.mockResolvedValue([
      {
        id: 50,
        title: 'Calculus I',
        summary: null,
        objectives: [],
        order_idx: 0,
        depth: 0,
        is_root: true,
        children: [
          {
            id: 51,
            title: 'Chapter 1',
            summary: null,
            objectives: [],
            order_idx: 0,
            depth: 1,
            is_root: false,
            children: [],
            materials: [],
          },
        ],
        materials: [],
      },
    ])
    allocateNodeFolder.mockResolvedValue(undefined)
    renderAt('/library?course=3')
    expect(await screen.findByText('Lectures')).toBeInTheDocument()

    fireEvent.contextMenu(screen.getByText('Lectures'))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Assign folder to node…' }))

    expect(
      await screen.findByRole('dialog', { name: 'Assign folder to node' })
    ).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('treeitem', { name: /Chapter 1/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Assign' }))

    await waitFor(() => expect(allocateNodeFolder).toHaveBeenCalledWith(51, 11))
    await waitFor(() =>
      expect(screen.getByText('Assigned to node')).toBeInTheDocument()
    )
  })
})

async function renderAtPane(initial: string): Promise<HTMLElement> {
  renderAt(initial)
  const pane = await screen.findByText('No materials here yet — drop in a PDF to get started.')
  return pane.parentElement as HTMLElement
}

describe('MaterialDetailPage', () => {
  test('shows header, chips and default extraction tab', async () => {
    listCourses.mockResolvedValue(COURSES)
    getMaterial.mockResolvedValue(DETAIL)
    getMaterialLinks.mockResolvedValue([
      {
        node_id: 21,
        owner_title: 'Limit intuition',
        breadcrumb: [
          { id: 1, title: 'Calculus I' },
          { id: 2, title: 'Limits' },
          { id: 21, title: 'Limit intuition' },
        ],
        is_course_level: false,
        course_id: 3,
        course_title: 'Calculus I',
        auto_assigned: true,
        rationale: 'why',
        via_folder: null,
      },
    ])
    listStudyStates.mockResolvedValue({ '7': { status: 'reading', progress: 0.4 } })
    renderAt('/library/7')
    expect(await screen.findByRole('heading', { name: 'chain-rule.pdf' })).toBeInTheDocument()
    expect(screen.getAllByText('Calculus I').length).toBeGreaterThan(1)
    expect(screen.getByText('Assigned: Limits · Limit intuition')).toBeInTheDocument()
    expect(screen.getByText('Version 1 · extracted by pymupdf')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Extraction', selected: true })).toBeInTheDocument()
  })

  test('folder-derived assignment shows a via-folder chip', async () => {
    listCourses.mockResolvedValue(COURSES)
    getMaterial.mockResolvedValue(DETAIL)
    getMaterialLinks.mockResolvedValue([
      {
        node_id: 21,
        owner_title: 'Limit intuition',
        breadcrumb: [
          { id: 1, title: 'Calculus I' },
          { id: 2, title: 'Limits' },
          { id: 21, title: 'Limit intuition' },
        ],
        is_course_level: false,
        course_id: 3,
        course_title: 'Calculus I',
        auto_assigned: false,
        rationale: null,
        via_folder: { id: 11, name: 'Lectures' },
      },
    ])
    listStudyStates.mockResolvedValue({})
    renderAt('/library/7')
    expect(
      await screen.findByText('Assigned via “Lectures”: Limits · Limit intuition')
    ).toBeInTheDocument()
  })

  test('original tab renders text files inline instead of a link', async () => {
    apiFetchMock.mockResolvedValue({
      ok: true,
      text: async () => 'plain lecture notes',
    })
    listCourses.mockResolvedValue(COURSES)
    getMaterial.mockResolvedValue({
      ...DETAIL,
      material: { ...MATERIAL, kind: 'txt', mime: 'text/plain' },
    })
    getMaterialLinks.mockResolvedValue([])
    listStudyStates.mockResolvedValue({})
    renderAt('/library/7?tab=original')
    expect(await screen.findByText('plain lecture notes')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /open original/i })).not.toBeInTheDocument()
  })

  test('original and side-by-side tabs', async () => {
    listCourses.mockResolvedValue(COURSES)
    getMaterial.mockResolvedValue(DETAIL)
    getMaterialLinks.mockResolvedValue([])
    listStudyStates.mockResolvedValue({})
    renderAt('/library/7?tab=original')
    expect(await screen.findByTitle('chain-rule.pdf')).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('tab', { name: 'Side-by-side' }))
    const originals = await screen.findAllByTitle('chain-rule.pdf')
    expect(originals.length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('chain rule').length).toBeGreaterThan(0)
  })

  test('study state buttons update status', async () => {
    listCourses.mockResolvedValue(COURSES)
    getMaterial.mockResolvedValue(DETAIL)
    getMaterialLinks.mockResolvedValue([])
    listStudyStates.mockResolvedValue({})
    setStudyState.mockResolvedValue({ status: 'studied', progress: 1 })
    renderAt('/library/7')
    const studied = await screen.findByRole('button', { name: 'Studied' })
    fireEvent.click(studied)
    await waitFor(() => expect(setStudyState).toHaveBeenCalledWith(7, 'studied'))
  })
})
