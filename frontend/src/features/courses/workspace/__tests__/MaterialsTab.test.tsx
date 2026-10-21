import { getWindowDropTarget } from '@/lib/window-drop-store'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'
import {
  allocateMaterial,
  allocateNodeFolder,
  assignCourseTask,
  browseSource,
  createFolder,
  createTextMaterial,
  deallocateMaterial,
  deallocateNodeFolder,
  deriveMaterialsMock,
  getMaterial,
  getPlacementSuggestions,
  getUnassignedMaterials,
  listCourseTaskDefaults,
  listCourseTasks,
  listFolders,
  listMaterials,
  listModels,
  mirrorFolder,
  nodeWorkspace,
  uploadMaterial,
  ROOT_WS,
  NODE_WS,
  primeDefaults,
  renderWorkspace,
  routerHolder,
} from './harness'

describe('MaterialsTab', () => {
  test('material rows open the dock in place (URL param), close lives in the dock', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5?tab=materials')
    const row = await screen.findByRole('button', { name: /chain-rule\.pdf/i })
    fireEvent.click(row, { detail: 1 })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    fireEvent.doubleClick(row)
    await waitFor(() =>
      expect(routerHolder.current!.state.location.search).toMatchObject({ material: '7' })
    )
    expect(routerHolder.current!.state.location.pathname).toBe('/courses/3/n/5')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  test('materials tab toggles to grid and back', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5?tab=materials')
    await screen.findByRole('button', { name: /chain-rule\.pdf/i })
    fireEvent.click(screen.getByRole('button', { name: 'Grid view' }))
    await screen.findByRole('button', { name: /chain-rule\.pdf/i })
    fireEvent.click(screen.getByRole('button', { name: 'List view' }))
    expect(await screen.findByRole('button', { name: /chain-rule\.pdf/i })).toBeInTheDocument()
  })

  test('materials tab search filters materials and shows a no-results note', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5?tab=materials')
    await screen.findByRole('button', { name: /chain-rule\.pdf/i })
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))
    const input = await screen.findByRole('textbox', { name: 'Filter materials…' })
    fireEvent.change(input, { target: { value: 'no-such-material' } })
    expect(screen.queryByRole('button', { name: /chain-rule\.pdf/i })).not.toBeInTheDocument()
    expect(screen.getByText('Nothing matches this filter.')).toBeInTheDocument()
    fireEvent.change(input, { target: { value: 'chain' } })
    expect(screen.getByRole('button', { name: /chain-rule\.pdf/i })).toBeInTheDocument()
    expect(screen.queryByText('Nothing matches this filter.')).not.toBeInTheDocument()
  })

  test('materials tab right-click menu unassigns from the node', async () => {
    primeDefaults()
    deallocateMaterial.mockResolvedValue(undefined)
    renderWorkspace('/courses/3/n/5?tab=materials')
    const row = await screen.findByRole('button', { name: /chain-rule\.pdf/i })
    fireEvent.contextMenu(row)
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Remove from node' }))
    await waitFor(() => expect(deallocateMaterial).toHaveBeenCalledWith('5', '7'))
  })

  test('materials tab right-click on a pdf offers Re-extract and opens the dialog', async () => {
    primeDefaults()
    getMaterial.mockImplementation((id: string) =>
      Promise.resolve({
        material: {
          id,
          title: 'chain-rule.pdf',
          kind: 'pdf',
          status: 'ready',
          filename: 'chain-rule.pdf',
          mime: 'application/pdf',
          pages: 4,
          course_id: '3',
          folder_id: null,
          blob_sha: 'b'.repeat(64),
          created_at: '2026-09-01T00:00:00Z',
          reextract_modes: ['auto', 'text', 'ocr'],
        },
        extraction: null,
        index_card: null,
        drawings: [],
        images: [],
      }),
    )
    renderWorkspace('/courses/3/n/5?tab=materials')
    const row = await screen.findByRole('button', { name: /chain-rule\.pdf/i })
    fireEvent.contextMenu(row)
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Re-extract…' }))
    expect(await screen.findByTestId('reextract-dialog')).toBeInTheDocument()
    expect(await screen.findByTestId('reextract-mode-text')).toBeInTheDocument()
  })

  test('materials tab uploads place at the node in the single upload call', async () => {
    primeDefaults()
    uploadMaterial.mockResolvedValue({
      material: { id: '77', title: 'problems.pdf', kind: 'pdf', status: 'pending' },
      job_id: null,
      deduped: false,
      node_id: '5',
    })
    renderWorkspace('/courses/3/n/5?tab=materials')
    await screen.findByRole('button', { name: /chain-rule\.pdf/i })
    const input = screen.getByLabelText('Upload files')
    fireEvent.change(input, {
      target: { files: [new File(['data'], 'problems.pdf', { type: 'application/pdf' })] },
    })
    await waitFor(() => expect(uploadMaterial).toHaveBeenCalledTimes(1))
    expect(uploadMaterial.mock.calls[0][1]).toBe('3')
    expect(uploadMaterial.mock.calls[0][2]).toBeNull()
    expect(uploadMaterial.mock.calls[0][3]).toBe('5')
    await waitFor(() => expect(allocateMaterial).not.toHaveBeenCalled())
  })

  test('empty materials tab offers an upload dropzone at course root', async () => {
    primeDefaults()
    renderWorkspace('/courses/3?tab=materials')
    expect(
      await screen.findByText('No materials here yet — upload files or assign from the library')
    ).toBeInTheDocument()
    expect(
      screen.getByLabelText('Drop files here or click to browse')
    ).toBeInTheDocument()
  })

  test('materials tab new menu offers create and upload entries', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5?tab=materials')
    await screen.findByRole('button', { name: /chain-rule\.pdf/i })

    fireEvent.click(screen.getByRole('button', { name: 'New…' }))
    expect(await screen.findByRole('menu')).toBeInTheDocument()
    for (const label of [
      'New folder',
      'New text file',
      'New Markdown file',
      'Upload files…',
      'Upload folder…',
    ]) {
      expect(screen.getByRole('menuitem', { name: label })).toBeInTheDocument()
    }
    expect(
      screen.queryByRole('button', { name: 'Choose what to upload' })
    ).not.toBeInTheDocument()
  })

  test('materials tab new Markdown file creates it unfiled and assigns it to the node', async () => {
    primeDefaults()
    createTextMaterial.mockResolvedValue({
      materialId: '88',
      content: '$x^2$ rules',
      refToReal: {},
      jobId: null,
    })
    allocateMaterial.mockResolvedValue({ node_id: '5', material_id: '88' })
    renderWorkspace('/courses/3/n/5?tab=materials')
    await screen.findByRole('button', { name: /chain-rule\.pdf/i })

    fireEvent.click(screen.getByRole('button', { name: 'New…' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'New Markdown file' }))
    const nameInput = await screen.findByPlaceholderText('File name')
    fireEvent.change(nameInput, { target: { value: 'derivation' } })
    fireEvent.change(screen.getByLabelText('File content (markdown + LaTeX)'), {
      target: { value: '$x^2$ rules' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    await waitFor(() =>
      expect(createTextMaterial).toHaveBeenCalledWith({
        course_id: '3',
        folder_id: null,
        filename: 'derivation.md',
        content: '$x^2$ rules',
        description: '',
        drawings: [],
      })
    )
    await waitFor(() => expect(allocateMaterial).toHaveBeenCalledWith('5', '88'))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Save' })).not.toBeNull()
    )
    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    await waitFor(() =>
      expect(screen.queryByPlaceholderText('File name')).not.toBeInTheDocument()
    )
  })

  test('materials tab new folder creates it at library root and assigns it to the node', async () => {
    primeDefaults()
    allocateNodeFolder.mockResolvedValue(undefined)
    renderWorkspace('/courses/3/n/5?tab=materials')
    await screen.findByRole('button', { name: /chain-rule\.pdf/i })

    fireEvent.click(screen.getByRole('button', { name: 'New…' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'New folder' }))
    fireEvent.change(await screen.findByPlaceholderText('Folder name'), {
      target: { value: 'Practice set' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    await waitFor(() => expect(createFolder).toHaveBeenCalledWith('Practice set', null, '3'))
    await waitFor(() => expect(allocateNodeFolder).toHaveBeenCalledWith('5', '901'))
    await waitFor(() =>
      expect(screen.queryByPlaceholderText('Folder name')).not.toBeInTheDocument()
    )
  })

  test('materials tab right-click on empty pane opens the create menu', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5?tab=materials')
    await screen.findByRole('button', { name: /chain-rule\.pdf/i })

    const pane = document.querySelector('[data-marquee-surface]') as HTMLElement
    fireEvent.contextMenu(pane)
    expect(await screen.findByRole('menu')).toBeInTheDocument()
    expect(
      screen.getByRole('menuitem', { name: 'New Markdown file' })
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem', { name: 'New text file' }))
    expect(await screen.findByPlaceholderText('File name')).toBeInTheDocument()
  })

  test('materials tab marquee drag selects the intersecting entries', async () => {
    primeDefaults()
    const rectSpy = vi
      .spyOn(Element.prototype, 'getBoundingClientRect')
      .mockReturnValue({
        left: 0, top: 0, right: 400, bottom: 400, width: 400, height: 400, x: 0, y: 0,
        toJSON: () => ({}),
      } as DOMRect)
    renderWorkspace('/courses/3/n/5?tab=materials')
    await screen.findByRole('button', { name: /chain-rule\.pdf/i })

    const pane = document.querySelector('[data-marquee-surface]') as HTMLElement
    fireEvent.mouseDown(pane, { clientX: 0, clientY: 0, button: 0 })
    fireEvent.mouseMove(window, { clientX: 200, clientY: 200 })
    fireEvent.mouseUp(window, { clientX: 200, clientY: 200 })

    const wrapper = screen
      .getByText('chain-rule.pdf')
      .closest('[data-selectable-id]') as HTMLElement
    await waitFor(() =>
      expect(wrapper.querySelector('[class*="bg-primary/10"]')).not.toBeNull()
    )
    expect(screen.queryByText(/selected/i)).not.toBeInTheDocument()

    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() =>
      expect(wrapper.querySelector('[class*="bg-primary/10"]')).toBeNull()
    )
    rectSpy.mockRestore()
  })

  test('materials tab folder upload assigns the folder to the node, not the files', async () => {
    primeDefaults()
    uploadMaterial.mockClear()
    allocateMaterial.mockClear()
    createFolder.mockClear()
    allocateNodeFolder.mockClear()
    allocateNodeFolder.mockResolvedValue(undefined)
    uploadMaterial.mockImplementation(async (sent: File) => ({
      material: { id: String(70 + sent.name.charCodeAt(0)), title: sent.name, kind: 'pdf', status: 'pending' },
      job_id: null,
      deduped: false,
    }))
    allocateMaterial.mockResolvedValue(undefined)
    renderWorkspace('/courses/3/n/5?tab=materials')
    await screen.findByRole('button', { name: /chain-rule\.pdf/i })

    const input = screen.getByLabelText('Upload a folder')
    const pack = new File(['x'], 'pack.pdf')
    Object.defineProperty(pack, 'webkitRelativePath', { value: 'Lecture pack/pack.pdf' })
    const deep = new File(['x'], 'deep.pdf')
    Object.defineProperty(deep, 'webkitRelativePath', { value: 'Lecture pack/week1/deep.pdf' })
    fireEvent.change(input, { target: { files: [pack, deep] } })

    await waitFor(() => expect(uploadMaterial).toHaveBeenCalledTimes(2))
    expect(createFolder).toHaveBeenCalledWith('Lecture pack', null, '3')
    expect(createFolder).toHaveBeenCalledWith('week1', '901', '3')
    const targetFolders = uploadMaterial.mock.calls.map((call) => call[2])
    expect(new Set(targetFolders)).toEqual(new Set(['901', '902']))
    await waitFor(() =>
      expect(allocateNodeFolder).toHaveBeenCalledWith('5', '901')
    )
    expect(allocateNodeFolder).toHaveBeenCalledTimes(1)
    expect(allocateMaterial).not.toHaveBeenCalled()
  })

  test('materials tab registers the window drop target for the node', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5?tab=materials')
    await screen.findByRole('button', { name: /chain-rule\.pdf/i })
    const target = getWindowDropTarget()
    expect(target?.label).toBe('Derivatives')
    expect(target?.upload()).not.toBeNull()
  })

  test('materials tab right-click unassigns and assigns to a node', async () => {
    primeDefaults()
    deallocateMaterial.mockResolvedValue(undefined)
    allocateMaterial.mockResolvedValue(undefined)
    renderWorkspace('/courses/3/n/5?tab=materials')
    expect(await screen.findByText('chain-rule.pdf')).toBeInTheDocument()

    fireEvent.contextMenu(screen.getByText('chain-rule.pdf'))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Remove from node' }))
    await waitFor(() => expect(deallocateMaterial).toHaveBeenCalledWith('5', '7'))

    fireEvent.contextMenu(screen.getByText('chain-rule.pdf'))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Assign to node…' }))
    fireEvent.click(await screen.findByRole('treeitem', { name: /Chain rule/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Assign' }))
    await waitFor(() => expect(allocateMaterial).toHaveBeenCalledWith('11', '7'))
  })

  test('materials tab right-click saves extracted text as a material', async () => {
    primeDefaults()
    deriveMaterialsMock.mockResolvedValue({
      results: [
        {
          material_id: '7',
          outcome: 'created',
          material: null,
          job_id: '41',
        },
      ],
      created: 1,
      deduped: 0,
      skipped: 0,
    })
    renderWorkspace('/courses/3/n/5?tab=materials')
    expect(await screen.findByText('chain-rule.pdf')).toBeInTheDocument()

    fireEvent.contextMenu(screen.getByText('chain-rule.pdf'))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Save as material' }))
    await waitFor(() => expect(deriveMaterialsMock).toHaveBeenCalledWith(['7']))
    expect(await screen.findByText('Saved 1 material')).toBeInTheDocument()
  })

  test('materials tab shows assigned folders as folder rows with unassign', async () => {
    primeDefaults()
    deallocateNodeFolder.mockResolvedValue(undefined)
    nodeWorkspace.mockImplementation((id: string) =>
      Promise.resolve(
        id === '1'
          ? ROOT_WS
          : {
              ...NODE_WS,
              folders: [
                {
                  folder_id: '10',
                  name: 'Lectures',
                  source_id: null,
                  member_count: 2,
                  rationale: null,
                  auto_assigned: false,
                },
              ],
              materials: [NODE_WS.materials[0]],
              folder_material_ids: ['9'],
            }
      )
    )
    renderWorkspace('/courses/3/n/5?tab=materials')
    await screen.findByRole('button', { name: /chain-rule\.pdf/i })

    expect(screen.queryByText('Assigned folders:')).not.toBeInTheDocument()
    const row = screen.getByTitle('2 materials in this folder join this node')
    expect(within(row).getByText('Lectures')).toBeInTheDocument()
    expect(within(row).getByText('2')).toBeInTheDocument()

    fireEvent.click(within(row).getByTitle('Unassign folder'))
    await waitFor(() => expect(deallocateNodeFolder).toHaveBeenCalledWith('5', '10'))
  })

  test('materials tab does not list files from an assigned folder', async () => {
    primeDefaults()
    nodeWorkspace.mockImplementation((id: string) =>
      Promise.resolve(
        id === '1'
          ? ROOT_WS
          : {
              ...NODE_WS,
              folders: [
                {
                  folder_id: '10',
                  name: 'Lectures',
                  source_id: null,
                  member_count: 2,
                  rationale: null,
                  auto_assigned: false,
                },
              ],
              materials: [],
              folder_material_ids: ['8', '9'],
            }
      )
    )
    renderWorkspace('/courses/3/n/5?tab=materials')
    await screen.findByTitle('2 materials in this folder join this node')

    expect(screen.queryByText(/week1\.pdf/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/notes\.pdf/i)).not.toBeInTheDocument()
    expect(screen.getByTitle('2 materials in this folder join this node')).toBeInTheDocument()
  })

  test('assigned folders render as grid tiles too', async () => {
    primeDefaults()
    nodeWorkspace.mockImplementation((id: string) =>
      Promise.resolve(
        id === '1'
          ? ROOT_WS
          : {
              ...NODE_WS,
              folders: [
                {
                  folder_id: '10',
                  name: 'Lectures',
                  source_id: null,
                  member_count: 2,
                  rationale: null,
                  auto_assigned: false,
                },
              ],
              materials: [],
            }
      )
    )
    renderWorkspace('/courses/3/n/5?tab=materials')
    await screen.findByTitle('2 materials in this folder join this node')
    fireEvent.click(screen.getByRole('button', { name: 'Grid view' }))
    expect(
      await screen.findByTitle('2 materials in this folder join this node')
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Lectures/ })).toBeInTheDocument()
  })

  test('double-clicking an assigned folder drills in inside the tab (plan 76 B)', async () => {
    primeDefaults()
    nodeWorkspace.mockImplementation((id: string) =>
      Promise.resolve(
        id === '1'
          ? ROOT_WS
          : {
              ...NODE_WS,
              folders: [
                {
                  folder_id: '10',
                  name: 'Lectures',
                  source_id: null,
                  member_count: 2,
                  rationale: null,
                  auto_assigned: false,
                },
              ],
            }
      )
    )
    renderWorkspace('/courses/3/n/5?tab=materials')
    const row = await screen.findByTitle('2 materials in this folder join this node')
    fireEvent.doubleClick(row)
    await waitFor(() =>
      expect(routerHolder.current!.state.location.search).toMatchObject({
        tab: 'materials',
        folder: '10',
      })
    )
    expect(routerHolder.current!.state.location.pathname).toBe('/courses/3/n/5')
  })

  test('linked-source assigned folder browses its source in the tab (plan 76 C)', async () => {
    primeDefaults()
    nodeWorkspace.mockImplementation((id: string) =>
      Promise.resolve(
        id === '1'
          ? ROOT_WS
          : {
              ...NODE_WS,
              folders: [
                {
                  folder_id: '10',
                  name: 'Lectures',
                  source_id: '77',
                  member_count: 2,
                  rationale: null,
                  auto_assigned: false,
                },
              ],
            }
      )
    )
    listFolders.mockResolvedValue([
      {
        id: '10',
        name: 'Lectures',
        path: '/Lectures',
        course_id: '3',
        parent_id: null,
        source_id: '77',
        created_at: '2026-09-01T00:00:00Z',
      },
    ])
    browseSource.mockResolvedValue({
      source_id: '77',
      label: 'Lecture vault',
      path: '/vault',
      subdir: '',
      missing_target: false,
      enabled: true,
      scan_interval_sec: 300,
      last_scan_error: null,
      last_scanned_at: null,
      subdirs: [{ name: 'week-1' }],
      materials: [
        {
          id: '55',
          title: 'intro-scan.pdf',
          kind: 'pdf',
          status: 'ready',
          filename: 'intro-scan.pdf',
          relpath: 'intro-scan.pdf',
        },
      ],
      uningested: [
        { name: 'new-notes.txt', relpath: 'new-notes.txt', size_bytes: 12, mtime: 1 },
      ],
    })
    renderWorkspace('/courses/3/n/5?tab=materials')
    const row = await screen.findByTitle('2 materials in this folder join this node')
    fireEvent.doubleClick(row)
    await waitFor(() =>
      expect(routerHolder.current!.state.location.search).toMatchObject({
        tab: 'materials',
        folder: '10',
      })
    )
    expect(await screen.findByText('intro-scan.pdf')).toBeInTheDocument()
    expect(browseSource).toHaveBeenCalledWith('77', '')
    expect(screen.getByText('week-1')).toBeInTheDocument()
    expect(screen.getByText('new-notes.txt')).toBeInTheDocument()

    fireEvent.click(screen.getByText('week-1'))
    await waitFor(() => expect(browseSource).toHaveBeenCalledWith('77', 'week-1'))
  })

  test('assigned folder context menu unassigns it', async () => {
    primeDefaults()
    deallocateNodeFolder.mockResolvedValue(undefined)
    nodeWorkspace.mockImplementation((id: string) =>
      Promise.resolve(
        id === '1'
          ? ROOT_WS
          : {
              ...NODE_WS,
              folders: [
                {
                  folder_id: '10',
                  name: 'Lectures',
                  source_id: null,
                  member_count: 2,
                  rationale: null,
                  auto_assigned: false,
                },
              ],
            }
      )
    )
    renderWorkspace('/courses/3/n/5?tab=materials')
    const row = await screen.findByTitle('2 materials in this folder join this node')
    fireEvent.contextMenu(row)
    expect(
      await screen.findByRole('menuitem', { name: 'Open in library' })
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Unassign folder' }))
    await waitFor(() => expect(deallocateNodeFolder).toHaveBeenCalledWith('5', '10'))
  })

  test('materials tab folder menu mirrors the folder structure into nodes', async () => {
    primeDefaults()
    mirrorFolder.mockResolvedValue({
      created_nodes: 2,
      reused_nodes: 0,
      folder_links: 3,
      skipped_folders: [],
    })
    nodeWorkspace.mockImplementation((id: string) =>
      Promise.resolve(
        id === '1'
          ? ROOT_WS
          : {
              ...NODE_WS,
              folders: [
                {
                  folder_id: '10',
                  name: 'Lectures',
                  source_id: null,
                  member_count: 2,
                  rationale: null,
                  auto_assigned: false,
                },
              ],
            }
      )
    )
    renderWorkspace('/courses/3/n/5?tab=materials')
    const row = await screen.findByTitle('2 materials in this folder join this node')
    fireEvent.contextMenu(row)
    fireEvent.click(
      await screen.findByRole('menuitem', { name: 'Mirror folder structure into nodes' })
    )
    await waitFor(() => expect(mirrorFolder).toHaveBeenCalledWith('5', '10'))
    expect(
      await screen.findByText('2 nodes created')
    ).toBeInTheDocument()
  })

  test('materials tab mirroring reports reused and skipped counts honestly', async () => {
    primeDefaults()
    mirrorFolder.mockResolvedValue({
      created_nodes: 0,
      reused_nodes: 1,
      folder_links: 2,
      skipped_folders: ['pack/a/b/c'],
    })
    nodeWorkspace.mockImplementation((id: string) =>
      Promise.resolve(
        id === '1'
          ? ROOT_WS
          : {
              ...NODE_WS,
              folders: [
                {
                  folder_id: '10',
                  name: 'Lectures',
                  source_id: null,
                  member_count: 2,
                  rationale: null,
                  auto_assigned: false,
                },
              ],
            }
      )
    )
    renderWorkspace('/courses/3/n/5?tab=materials')
    const row = await screen.findByTitle('2 materials in this folder join this node')
    fireEvent.contextMenu(row)
    fireEvent.click(
      await screen.findByRole('menuitem', { name: 'Mirror folder structure into nodes' })
    )
    expect(
      await screen.findByText(/1 node reused/)
    ).toBeInTheDocument()
    const notice = await screen.findByText(/deeper level/)
    expect(notice.textContent).toContain('1')
  })

  test('course-level materials tab shows a needs-placement strip and assign flow', async () => {
    primeDefaults()
    getUnassignedMaterials.mockResolvedValue({
      count: 2,
      materials: [
        { id: '51', title: 'orphan-a.pdf' },
        { id: '52', title: 'orphan-b.pdf' },
      ],
    })
    allocateMaterial.mockResolvedValue(undefined)
    nodeWorkspace.mockImplementation(() => Promise.resolve(ROOT_WS))
    renderWorkspace('/courses/3/n/1?tab=materials')
    const strip = await screen.findByTestId('needs-placement-strip')
    expect(strip.textContent).toContain('2 materials need placement')

    fireEvent.click(strip)
    expect(await screen.findByTestId('needs-placement-panel')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('needs-placement-assign-51'))
    const placeDialog = await screen.findByRole('dialog', { name: 'Assign…' })
    fireEvent.click(within(placeDialog).getByRole('treeitem', { name: 'Derivatives' }))
    fireEvent.click(
      within(placeDialog).getByRole('button', { name: 'Assign' })
    )
    await waitFor(() => expect(allocateMaterial).toHaveBeenCalledWith(expect.anything(), '51'))
    await waitFor(() =>
      expect(getUnassignedMaterials).toHaveBeenCalled()
    )
  })

  test('needs-placement strip is hidden when the course has nothing unassigned', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/1?tab=materials')
    await screen.findByRole('button', { name: /chain-rule\.pdf/i })
    expect(screen.queryByTestId('needs-placement-strip')).not.toBeInTheDocument()
  })

  test('suggest for all renders candidate chips with matched tokens and assign on click', async () => {
    primeDefaults()
    getUnassignedMaterials.mockResolvedValue({
      count: 1,
      materials: [{ id: '51', title: 'integration by parts worked examples.pdf' }],
    })
    getPlacementSuggestions.mockResolvedValue({
      suggestions: [
        {
          material_id: '51',
          candidates: [
            {
              node_id: '11',
              node_title: 'Integration techniques',
              breadcrumb: [
                { id: '1', title: 'Calculus I' },
                { id: '11', title: 'Integration techniques' },
              ],
              score: 0.42,
              matched_on: ['integration'],
            },
          ],
        },
      ],
    })
    allocateMaterial.mockResolvedValue(undefined)
    nodeWorkspace.mockImplementation(() => Promise.resolve(ROOT_WS))
    renderWorkspace('/courses/3/n/1?tab=materials')
    fireEvent.click(await screen.findByTestId('needs-placement-strip'))
    fireEvent.click(await screen.findByRole('button', { name: 'Suggest for all' }))
    await waitFor(() =>
      expect(getPlacementSuggestions).toHaveBeenCalledWith('3', ['51'])
    )
    const chip = await screen.findByRole('button', {
      name: 'Calculus I › Integration techniques',
    })
    expect(chip).toHaveAttribute('title', 'integration')
    fireEvent.click(chip)
    await waitFor(() => expect(allocateMaterial).toHaveBeenCalledWith('11', '51'))
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Calculus I › Integration techniques' }))
        .not.toBeInTheDocument()
    )
  })

  test('materials tab bulk unassign removes selected materials and folders', async () => {
    primeDefaults()
    deallocateMaterial.mockResolvedValue(undefined)
    deallocateNodeFolder.mockResolvedValue(undefined)
    nodeWorkspace.mockImplementation((id: string) =>
      Promise.resolve(
        id === '1'
          ? ROOT_WS
          : {
              ...NODE_WS,
              folders: [
                {
                  folder_id: '10',
                  name: 'Lectures',
                  source_id: null,
                  member_count: 2,
                  rationale: null,
                  auto_assigned: false,
                },
              ],
            }
      )
    )
    renderWorkspace('/courses/3/n/5?tab=materials')
    const row = await screen.findByTitle('2 materials in this folder join this node')
    fireEvent.mouseDown(row)
    fireEvent.mouseDown(screen.getByText('chain-rule.pdf'), { ctrlKey: true })
    expect(screen.queryByText(/selected/i)).not.toBeInTheDocument()
    fireEvent.mouseDown(screen.getByText('chain-rule.pdf'), { button: 2 })
    fireEvent.contextMenu(screen.getByText('chain-rule.pdf'))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Unassign' }))

    await waitFor(() => expect(deallocateMaterial).toHaveBeenCalledWith('5', '7'))
    await waitFor(() => expect(deallocateNodeFolder).toHaveBeenCalledWith('5', '10'))
  })

  test('materials tab assign-to-node also moves selected folders', async () => {
    primeDefaults()
    allocateMaterial.mockResolvedValue(undefined)
    allocateNodeFolder.mockResolvedValue(undefined)
    nodeWorkspace.mockImplementation((id: string) =>
      Promise.resolve(
        id === '1'
          ? ROOT_WS
          : {
              ...NODE_WS,
              folders: [
                {
                  folder_id: '10',
                  name: 'Lectures',
                  source_id: null,
                  member_count: 2,
                  rationale: null,
                  auto_assigned: false,
                },
              ],
            }
      )
    )
    renderWorkspace('/courses/3/n/5?tab=materials')
    const row = await screen.findByTitle('2 materials in this folder join this node')
    fireEvent.mouseDown(row)
    fireEvent.mouseDown(screen.getByText('chain-rule.pdf'), { ctrlKey: true })
    fireEvent.mouseDown(screen.getByText('chain-rule.pdf'), { button: 2 })
    fireEvent.contextMenu(screen.getByText('chain-rule.pdf'))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Assign to node…' }))
    fireEvent.click(await screen.findByRole('treeitem', { name: /Chain rule/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Assign' }))
    await waitFor(() => expect(allocateMaterial).toHaveBeenCalledWith('11', '7'))
    await waitFor(() => expect(allocateNodeFolder).toHaveBeenCalledWith('11', '10'))
  })

  test('materials tab bulk unassign skips folder-member materials', async () => {
    primeDefaults()
    deallocateMaterial.mockResolvedValue(undefined)
    nodeWorkspace.mockImplementation((id: string) =>
      Promise.resolve(
        id === '1'
          ? ROOT_WS
          : {
              ...NODE_WS,
              materials: [NODE_WS.materials[0]],
              folders: [
                {
                  folder_id: '10',
                  name: 'Lectures',
                  source_id: null,
                  member_count: 1,
                  rationale: null,
                  auto_assigned: false,
                },
              ],
              folder_material_ids: ['9'],
            }
      )
    )
    renderWorkspace('/courses/3/n/5?tab=materials')
    expect(await screen.findByText('chain-rule.pdf')).toBeInTheDocument()

    fireEvent.mouseDown(screen.getByText('chain-rule.pdf'))
    fireEvent.mouseDown(screen.getByText('chain-rule.pdf'), { button: 2 })
    fireEvent.contextMenu(screen.getByText('chain-rule.pdf'))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Remove from node' }))

    await waitFor(() => expect(deallocateMaterial).toHaveBeenCalledWith('5', '7'))
    expect(deallocateMaterial).not.toHaveBeenCalledWith('5', '9')
  })

  test('settings tasks subtab lists overrides and assigns a course model', async () => {
    primeDefaults()
    listModels.mockResolvedValue([
      { id: '1', label: 'local-mini', caps: ['text'], enabled: true, missing: false },
      { id: '2', label: 'vision-pro', caps: ['text', 'vision'], enabled: true, missing: false },
    ])
    listCourseTaskDefaults.mockResolvedValue([])
    listCourseTasks.mockResolvedValue([
      {
        task: 'chat',
        description: 'Tutor chat turns',
        requires: 'text',
        model_id: null,
        fallback_model_id: null,
        model_label: null,
        fallback_model_label: null,
        global_model_label: 'global-chat',
        global_fallback_model_label: null,
      },
      {
        task: 'ocr',
        description: 'Scanned page OCR',
        requires: 'vision',
        model_id: '2',
        fallback_model_id: null,
        model_label: 'vision-pro',
        fallback_model_label: null,
        global_model_label: null,
        global_fallback_model_label: null,
      },
    ])
    assignCourseTask.mockResolvedValue({})
    renderWorkspace('/courses/3?tab=settings')
    await screen.findByTestId('course-settings-tab')
    fireEvent.click(screen.getByRole('tab', { name: 'Tasks' }))

    expect(await screen.findByText('chat')).toBeInTheDocument()
    expect(screen.getByText(/using global-chat/i)).toBeInTheDocument()

    const chatModel = screen.getByRole('combobox', { name: 'chat course model' })
    expect(chatModel).toHaveValue('')
    fireEvent.change(chatModel, { target: { value: '1' } })
    await waitFor(() =>
      expect(assignCourseTask).toHaveBeenCalledWith('3', 'chat', '1', null)
    )

    const ocrModel = screen.getByRole('combobox', { name: 'ocr course model' })
    expect(ocrModel).toHaveValue('2')
    const ocrOptions = within(ocrModel).getAllByRole('option')
    expect(ocrOptions.map((entry) => entry.textContent)).toEqual([
      '— unassigned —',
      'vision-pro',
    ])
  })

  describe('materials tab folder browsing (plan 76 B)', () => {
    const FOLDERS = [
      {
        id: '901',
        name: 'Lectures',
        path: '/Lectures',
        course_id: '3',
        parent_id: null,
        source_id: null,
        created_at: '2026-09-01T00:00:00Z',
      },
      {
        id: '902',
        name: 'Week 1',
        path: '/Lectures/Week 1',
        course_id: '3',
        parent_id: '901',
        source_id: null,
        created_at: '2026-09-01T00:00:00Z',
      },
    ]
    const FOLDER_MATERIAL = {
      id: '44',
      title: 'limits-notes.md',
      kind: 'md',
      status: 'ready',
      course_id: '3',
      folder_id: '901',
      created_at: '2026-09-01T00:00:00Z',
      provenance: null,
    }

    function primeFolderWorkspace() {
      primeDefaults()
      nodeWorkspace.mockImplementation((id: string) =>
        Promise.resolve(
          id === '1'
            ? ROOT_WS
            : {
                ...NODE_WS,
                folders: [
                  {
                    folder_id: '901',
                    name: 'Lectures',
                    source_id: null,
                    member_count: 1,
                    rationale: null,
                    auto_assigned: false,
                  },
                ],
                materials: [NODE_WS.materials[0]],
              }
        )
      )
    }

    test('double-clicking an assigned folder drills in place under the same tab', async () => {
      primeFolderWorkspace()
      renderWorkspace('/courses/3/n/5?tab=materials')
      const row = await screen.findByTitle('1 material in this folder joins this node')
      fireEvent.doubleClick(row)
      await waitFor(() =>
        expect(routerHolder.current!.state.location.search).toMatchObject({
          tab: 'materials',
          folder: '901',
        })
      )
      expect(routerHolder.current!.state.location.pathname).toBe('/courses/3/n/5')
    })

    test('folder view shows full folder contents with breadcrumbs', async () => {
      primeFolderWorkspace()
      listFolders.mockResolvedValue(FOLDERS)
      listMaterials.mockImplementation((folderId: string) =>
        Promise.resolve(folderId === '901' ? [FOLDER_MATERIAL] : [])
      )
      renderWorkspace('/courses/3/n/5?tab=materials&folder=901')
      expect(await screen.findByRole('button', { name: /limits-notes\.md/i })).toBeInTheDocument()
      expect(screen.getByText('Week 1')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Materials' })).toBeInTheDocument()
    })

    test('clicking the root crumb leaves the folder view', async () => {
      primeFolderWorkspace()
      listFolders.mockResolvedValue(FOLDERS)
      listMaterials.mockImplementation((folderId: string) =>
        Promise.resolve(folderId === '901' ? [FOLDER_MATERIAL] : [])
      )
      renderWorkspace('/courses/3/n/5?tab=materials&folder=901')
      expect(await screen.findByRole('button', { name: /limits-notes\.md/i })).toBeInTheDocument()
      fireEvent.click(screen.getByRole('button', { name: 'Materials' }))
      await waitFor(() =>
        expect(
          (routerHolder.current!.state.location.search as { folder?: string }).folder
        ).toBeUndefined()
      )
      expect(await screen.findByRole('button', { name: /chain-rule\.pdf/i })).toBeInTheDocument()
    })

    test('a subfolder click navigates deeper inside the tab', async () => {
      primeFolderWorkspace()
      listFolders.mockResolvedValue(FOLDERS)
      listMaterials.mockResolvedValue([])
      renderWorkspace('/courses/3/n/5?tab=materials&folder=901')
      const sub = await screen.findByText('Week 1')
      fireEvent.doubleClick(sub)
      await waitFor(() =>
        expect(routerHolder.current!.state.location.search).toMatchObject({ folder: '902' })
      )
    })

    test('a stale folder id falls back to the root view', async () => {
      primeFolderWorkspace()
      listFolders.mockResolvedValue([])
      renderWorkspace('/courses/3/n/5?tab=materials&folder=404')
      expect(await screen.findByRole('button', { name: /chain-rule\.pdf/i })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Materials' })).not.toBeInTheDocument()
    })

    test('a material inside a folder opens the dock in place', async () => {
      primeFolderWorkspace()
      listFolders.mockResolvedValue(FOLDERS)
      listMaterials.mockImplementation((folderId: string) =>
        Promise.resolve(folderId === '901' ? [FOLDER_MATERIAL] : [])
      )
      renderWorkspace('/courses/3/n/5?tab=materials&folder=901')
      const row = await screen.findByRole('button', { name: /limits-notes\.md/i })
      fireEvent.doubleClick(row)
      await waitFor(() =>
        expect(routerHolder.current!.state.location.search).toMatchObject({ material: '44' })
      )
    })

    test('folder contents context menu offers open and open-in-library', async () => {
      primeFolderWorkspace()
      listFolders.mockResolvedValue(FOLDERS)
      listMaterials.mockResolvedValue([])
      renderWorkspace('/courses/3/n/5?tab=materials&folder=901')
      const sub = await screen.findByText('Week 1')
      fireEvent.contextMenu(sub)
      expect(
        await screen.findByRole('menuitem', { name: 'Open in library' })
      ).toBeInTheDocument()
      fireEvent.click(screen.getByRole('menuitem', { name: 'Open' }))
      await waitFor(() =>
        expect(routerHolder.current!.state.location.search).toMatchObject({ folder: '902' })
      )
    })
  })

})
