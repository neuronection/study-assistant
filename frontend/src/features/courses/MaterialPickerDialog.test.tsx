import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { MaterialPickerDialog } from './MaterialPickerDialog'

const listFolders = vi.fn()
const listMaterials = vi.fn()
const browseSource = vi.fn()
const ingestSourceFile = vi.fn()
const allocateMaterial = vi.fn()
const allocateNodeFolder = vi.fn()
const uploadMaterial = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listFolders: (...args: unknown[]) => listFolders(...(args as [number?])),
    listMaterials: (...args: unknown[]) =>
      listMaterials(...(args as [number | undefined, number | undefined, boolean | undefined])),
    browseSource: (...args: unknown[]) => browseSource(...(args as [number, string])),
    ingestSourceFile: (...args: unknown[]) => ingestSourceFile(...(args as [number, string])),
    allocateMaterial: (...args: unknown[]) =>
      allocateMaterial(...(args as [number, number])),
    allocateNodeFolder: (...args: unknown[]) =>
      allocateNodeFolder(...(args as [number, number])),
    uploadMaterial: (...args: unknown[]) => uploadMaterial(...(args as [])),
  }
})

function renderDialog(
  assignedIds: Set<number> = new Set(),
  props: {
    assignedFolderIds?: Set<number>
    mode?: 'allocate' | 'select'
    nodeId?: number | null
    onSelect?: (ids: number[]) => void
  } = {}
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MaterialPickerDialog
        courseId={1}
        nodeId={props.nodeId !== undefined ? props.nodeId : 7}
        nodeTitle="Derivatives"
        assignedIds={assignedIds}
        assignedFolderIds={props.assignedFolderIds}
        mode={props.mode ?? 'allocate'}
        onSelect={props.onSelect}
        onClose={() => undefined}
      />
    </QueryClientProvider>
  )
}

function material(id: number, title: string, folderId: number | null) {
  return {
    id,
    title,
    kind: 'pdf',
    status: 'ready',
    filename: `${title}.pdf`,
    mime: 'application/pdf',
    pages: 3,
    course_id: 1,
    group_id: null,
    folder_id: folderId,
    blob_sha: null,
    created_at: '2026-08-01T00:00:00Z',
  }
}

const ALL = [
  material(101, 'Lecture 1', 10),
  material(102, 'Lecture 2', 11),
  material(103, 'Scan A', 12),
  material(104, 'Loose notes', null),
]

const FOLDERS = [
  { id: 10, name: 'Lectures', path: '/Lectures', course_id: 1, parent_id: null, source_id: null, created_at: '2026-08-01T00:00:00Z' },
  { id: 11, name: 'Week 1', path: '/Lectures/Week 1', course_id: 1, parent_id: 10, source_id: null, created_at: '2026-08-01T00:00:00Z' },
  { id: 12, name: 'Scans', path: '/Scans', course_id: 1, parent_id: null, source_id: 3, created_at: '2026-08-01T00:00:00Z' },
]

function rowFor(title: string) {
  const row = screen
    .getAllByText(title)
    .map((node) => node.closest('div'))
    .find((div) => div !== null && div.querySelector('[role="checkbox"]') !== null)
  expect(row).not.toBeNull()
  return row as HTMLElement
}

describe('MaterialPickerDialog', () => {
  beforeEach(() => {
    listFolders.mockReset()
    listMaterials.mockReset()
    browseSource.mockReset()
    ingestSourceFile.mockReset()
    allocateMaterial.mockReset()
    allocateNodeFolder.mockReset()
    uploadMaterial.mockReset()
    listFolders.mockResolvedValue(FOLDERS)
    listMaterials.mockImplementation(async (_folderId, _courseId, unfiled) =>
      unfiled ? ALL.filter((entry) => entry.folder_id === null) : ALL
    )
    allocateMaterial.mockResolvedValue(undefined)
    allocateNodeFolder.mockResolvedValue(undefined)
  })

  test('assigns a whole folder alongside selected materials', async () => {
    renderDialog()
    expect(await screen.findByText('Loose notes')).toBeInTheDocument()

    fireEvent.click(screen.getAllByTitle(/assign the whole folder “lectures”/i)[0])
    const chip = await screen.findByTitle('Lectures — whole folder')
    expect(chip).toBeInTheDocument()

    fireEvent.click(screen.getByRole('checkbox', { name: /loose notes/i }))
    fireEvent.click(screen.getByRole('button', { name: /^assign material$/i }))

    await waitFor(() => expect(allocateNodeFolder).toHaveBeenCalledWith(7, 10))
    await waitFor(() => expect(allocateMaterial).toHaveBeenCalledWith(7, 104))
    expect(allocateNodeFolder).toHaveBeenCalledTimes(1)
  })

  test('deselects a folder via its chip', async () => {
    renderDialog()
    expect(await screen.findByText('Loose notes')).toBeInTheDocument()

    fireEvent.click(screen.getAllByTitle(/assign the whole folder “lectures”/i)[0])
    expect(await screen.findByTitle('Lectures — whole folder')).toBeInTheDocument()
    fireEvent.click(screen.getByTitle('Lectures — whole folder'))
    await waitFor(() =>
      expect(screen.queryByTitle('Lectures — whole folder')).not.toBeInTheDocument()
    )
    const confirm = screen.getByRole('button', { name: /^assign 0 materials$/i })
    expect(confirm).toBeDisabled()
  })

  test('a folder alone can be assigned', async () => {
    renderDialog()
    expect(await screen.findByText('Loose notes')).toBeInTheDocument()

    fireEvent.click(screen.getAllByTitle(/assign the whole folder “scans”/i)[0])
    fireEvent.click(screen.getByRole('button', { name: /^assign folder$/i }))

    await waitFor(() => expect(allocateNodeFolder).toHaveBeenCalledWith(7, 12))
    expect(allocateMaterial).not.toHaveBeenCalled()
  })

  test('folders already assigned to the node are locked, source folders assignable', async () => {
    renderDialog(new Set(), { assignedFolderIds: new Set([10]) })
    expect(await screen.findByText('Loose notes')).toBeInTheDocument()

    expect(
      screen.getAllByTitle('Folder already assigned here').length
    ).toBeGreaterThan(0)
    expect(
      screen.queryByTitle(/assign the whole folder “lectures”/i)
    ).not.toBeInTheDocument()

    const scansButton = screen.getAllByTitle(/assign the whole folder “scans”/i)[0]
    expect(scansButton).toBeEnabled()
  })

  test('select mode hides folder assignment buttons', async () => {
    renderDialog(new Set(), { mode: 'select', onSelect: () => undefined })
    expect(await screen.findByText('Loose notes')).toBeInTheDocument()
    expect(
      screen.queryByTitle(/assign the whole folder/i)
    ).not.toBeInTheDocument()
  })

  test('opens at course root showing folders and loose materials; assigns selections in one batch', async () => {
    renderDialog()
    expect(await screen.findByText('Loose notes')).toBeInTheDocument()
    expect(screen.getAllByText('Lectures').length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('checkbox', { name: /loose notes/i }))
    fireEvent.click(screen.getByRole('button', { name: /^assign material$/i }))

    await waitFor(() => expect(allocateMaterial).toHaveBeenCalledWith(7, 104))
    expect(allocateMaterial).toHaveBeenCalledTimes(1)
  })

  test('marks already-assigned materials as locked', async () => {
    renderDialog(new Set([104]))
    expect(await screen.findByText('Loose notes')).toBeInTheDocument()
    expect(screen.getByText('Assigned here')).toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: /loose notes/i })).not.toBeInTheDocument()
  })

  test('navigates into a folder, selects a subtree via the folder toggle, and deselects via the chip', async () => {
    renderDialog(new Set([101]))
    fireEvent.click((await screen.findAllByText('Lectures'))[0])

    expect(await screen.findByText('Lecture 1')).toBeInTheDocument()
    expect(screen.getByText('Assigned here')).toBeInTheDocument()

    fireEvent.click(within(rowFor('Week 1')).getByRole('checkbox'))
    expect(await screen.findByText('1 material selected')).toBeInTheDocument()

    fireEvent.click(screen.getByTitle('Lecture 2'))
    await waitFor(() => expect(screen.getByText('0 materials selected')).toBeInTheDocument())

    fireEvent.click(within(rowFor('Week 1')).getByRole('checkbox'))
    expect(await screen.findByText('1 material selected')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /^assign material$/i }))
    await waitFor(() => expect(allocateMaterial).toHaveBeenCalledWith(7, 102))
    expect(allocateMaterial).toHaveBeenCalledTimes(1)
  })

  test('select-all-shown toggles every visible unassigned material', async () => {
    renderDialog()
    expect(await screen.findByText('Loose notes')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('checkbox', { name: /select shown/i }))
    expect(await screen.findByText('1 material selected')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('checkbox', { name: /select shown/i }))
    await waitFor(() => expect(screen.getByText('0 materials selected')).toBeInTheDocument())
  })

  test('All materials view lists everything with fuzzy filtering', async () => {
    renderDialog()
    fireEvent.click(await screen.findByRole('button', { name: /all materials/i }))

    expect(await screen.findByText('Lecture 1')).toBeInTheDocument()
    expect(screen.getByText('Scan A')).toBeInTheDocument()
    expect(screen.getByText('Loose notes')).toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText('Filter materials…'), {
      target: { value: 'lect 2' },
    })
    await waitFor(() => expect(screen.queryByText('Lecture 1')).not.toBeInTheDocument())
    expect(screen.getByText('Lecture 2')).toBeInTheDocument()
  })

  test('linked folders browse the source and ingest-and-select pending files', async () => {
    browseSource.mockResolvedValue({
      source_id: 3,
      label: 'Scans',
      path: '/tmp/scans',
      subdir: '',
      missing_target: false,
      enabled: true,
      scan_interval_sec: null,
      last_scan_error: null,
      last_scanned_at: null,
      subdirs: [],
      materials: [ALL[2]],
      uningested: [{ name: 'new-scan.pdf', relpath: 'new-scan.pdf', size_bytes: 10, mtime: 1 }],
    })
    ingestSourceFile.mockResolvedValue({ material_id: 105, job_id: null, deduped: false })

    renderDialog()
    fireEvent.click((await screen.findAllByText('Scans'))[0])

    expect(await screen.findByText('new-scan.pdf')).toBeInTheDocument()
    expect(browseSource).toHaveBeenCalledWith(3, '')

    fireEvent.click(screen.getByRole('checkbox', { name: /scan a/i }))
    fireEvent.click(screen.getByRole('button', { name: /new-scan\.pdf/i }))
    await waitFor(() => expect(ingestSourceFile).toHaveBeenCalledWith(3, 'new-scan.pdf'))
    expect(await screen.findByText('2 materials selected')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /assign 2 materials/i }))
    await waitFor(() => {
      expect(allocateMaterial).toHaveBeenCalledWith(7, 103)
      expect(allocateMaterial).toHaveBeenCalledWith(7, 105)
    })
  })

  test('uploads from the picker land in the browsed folder and are auto-selected', async () => {
    uploadMaterial.mockResolvedValue({
      material: { ...material(105, 'Fresh upload.pdf', null), title: 'Fresh upload.pdf' },
      job_id: null,
      deduped: false,
    })
    renderDialog()
    expect(await screen.findByText('Loose notes')).toBeInTheDocument()

    fireEvent.click(screen.getAllByText('Lectures')[0])
    expect(await screen.findByText('Lecture 1')).toBeInTheDocument()
    expect(screen.getByText('Upload to this folder')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Upload to this folder'), {
      target: { files: [new File(['data'], 'Fresh upload.pdf', { type: 'application/pdf' })] },
    })
    await waitFor(() => expect(uploadMaterial).toHaveBeenCalledTimes(1))
    expect(uploadMaterial.mock.calls[0][1]).toBe(1)
    expect(uploadMaterial.mock.calls[0][2]).toBe(10)
    expect(await screen.findByText('1 material selected')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /^assign material$/i }))
    await waitFor(() => expect(allocateMaterial).toHaveBeenCalledWith(7, 105))
  })

  test('select mode returns the selection instead of allocating', async () => {
    const onSelect = vi.fn()
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <MaterialPickerDialog
          courseId={1}
          nodeTitle="Pick context"
          assignedIds={new Set()}
          onClose={() => undefined}
          mode="select"
          onSelect={onSelect}
        />
      </QueryClientProvider>
    )
    expect(await screen.findByText('Loose notes')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: /loose notes/i }))
    fireEvent.click(screen.getByRole('button', { name: /^add material$/i }))
    await waitFor(() => expect(onSelect).toHaveBeenCalledWith([104]))
    expect(allocateMaterial).not.toHaveBeenCalled()
  })
})
