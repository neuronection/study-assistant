import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'
import {
  createNote,
  deleteNote,
  listNoteTags,
  listNotes,
  moveNote,
  updateNote,
  primeDefaults,
  renderWorkspace,
  navigateMock,
  routerHolder,
} from './harness'

describe('NotesTab', () => {
  test('notes tab rolls up notes with node chips and opens a row in the drawer', async () => {
    primeDefaults()
    listNotes.mockResolvedValue({
      items: [
        {
          id: '21',
          title: 'Chain rule note',
          course_id: '3',
          node_id: '11',
          owner_type: 'standalone',
          owner_id: null,
          tags: [],
          pinned: false,
          updated_at: '2026-08-19T00:00:00Z',
        },
      ],
      next_cursor: null,
    })
    renderWorkspace('/courses/3/n/5?tab=notes')
    expect(await screen.findByText('Chain rule note')).toBeInTheDocument()
    expect(screen.getByText('Chain rule')).toBeInTheDocument()
    expect(listNotes).toHaveBeenCalledWith(undefined, '3', {
      tag: undefined,
      node_id: '5',
      limit: 50,
      cursor: undefined,
    })

    fireEvent.doubleClick(screen.getByRole('button', { name: /chain rule note/i }))
    await waitFor(() =>
      expect(routerHolder.current!.state.location.search).toMatchObject({ note: '21' })
    )
    expect(
      screen.queryByRole('textbox', { name: 'Note title' })
    ).not.toBeInTheDocument()

    const openCall = navigateMock.mock.calls.find(
      (call) =>
        call[0].to === '/courses/$courseId/n/$nodeId' && typeof call[0].search === 'function'
    )
    expect(openCall).toBeDefined()
    expect(
      navigateMock.mock.calls.every((call) => call[0].to !== '/notes/$noteId')
    ).toBe(true)
  })

  test('notes tab renames and deletes through the row menu', async () => {
    primeDefaults()
    listNotes.mockResolvedValue({
      items: [
        {
          id: '21',
          title: 'Chain rule note',
          course_id: '3',
          node_id: '11',
          owner_type: 'standalone',
          owner_id: null,
          tags: [],
          pinned: false,
          updated_at: '2026-08-19T00:00:00Z',
        },
      ],
      next_cursor: null,
    })
    updateNote.mockResolvedValue({})
    deleteNote.mockResolvedValue(undefined)
    renderWorkspace('/courses/3/n/5?tab=notes')
    await screen.findByText('Chain rule note')
    const kebabs = screen.getAllByRole('button', { name: 'Actions' })
    fireEvent.click(kebabs[kebabs.length - 1])
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Rename' }))
    const input = await screen.findByRole('textbox', { name: 'Rename note' })
    fireEvent.change(input, { target: { value: 'Renamed note' } })
    fireEvent.submit(input.closest('form')!)
    await waitFor(() => expect(updateNote).toHaveBeenCalledWith('21', { title: 'Renamed note' }))

    fireEvent.click(screen.getAllByRole('button', { name: 'Actions' })[0])
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Delete' }))
    expect(deleteNote).not.toHaveBeenCalled()
    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(deleteNote).toHaveBeenCalledWith('21'))
  })

  test('notes tab creates a note here and pins it in the dock URL', async () => {
    primeDefaults()
    createNote.mockResolvedValue({ id: '30', body: [], drawings: [], tags: [] })
    renderWorkspace('/courses/3/n/5?tab=notes')
    fireEvent.click(await screen.findByRole('button', { name: /new note here/i }))
    await waitFor(() =>
      expect(createNote).toHaveBeenCalledWith({
        title: 'Untitled note',
        course_id: '3',
        node_id: '5',
        tags: [],
      })
    )
    await waitFor(() =>
      expect(routerHolder.current!.state.location.search).toMatchObject({ note: '30' })
    )
    expect(
      screen.queryByRole('textbox', { name: 'Note title' })
    ).not.toBeInTheDocument()
    expect(
      navigateMock.mock.calls.every((call) => call[0].to !== '/notes/$noteId')
    ).toBe(true)
  })

  test('notes tab filters by tag and submitted search text', async () => {
    primeDefaults()
    listNotes.mockResolvedValue({
      items: [
        {
          id: '21',
          title: 'Chain rule note',
          course_id: '3',
          node_id: '11',
          owner_type: 'standalone',
          owner_id: null,
          tags: ['exam'],
          pinned: false,
          updated_at: '2026-08-19T00:00:00Z',
        },
      ],
      next_cursor: null,
    })
    listNoteTags.mockResolvedValue([{ tag: 'exam', count: 1 }])
    renderWorkspace('/courses/3/n/5?tab=notes')
    fireEvent.click(await screen.findByRole('button', { name: 'exam' }))
    await waitFor(() =>
      expect(listNotes).toHaveBeenLastCalledWith(undefined, '3', {
        tag: 'exam',
        node_id: '5',
        limit: 50,
        cursor: undefined,
      })
    )

    fireEvent.click(screen.getByRole('button', { name: 'Search' }))
    const input = await screen.findByRole('textbox', { name: /search notes/i })
    fireEvent.change(input, { target: { value: 'chain rule' } })
    await waitFor(() =>
      expect(listNotes).toHaveBeenLastCalledWith('chain rule', '3', {
        tag: 'exam',
        node_id: '5',
        limit: 50,
        cursor: undefined,
      })
    )
  })

  test('closing the notes side keeps the material docked (plan 62-A)', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5?tab=materials&material=7&study=77')
    expect(await screen.findByTestId('study-note-editor-stub')).toHaveTextContent('note:77')

    fireEvent.click(screen.getByRole('button', { name: 'Close notes' }))

    await waitFor(() =>
      expect(routerHolder.current!.state.location.search).toMatchObject({ material: 7 })
    )
    expect(
      (routerHolder.current!.state.location.search as { study?: string }).study
    ).toBeUndefined()
  })

  test('notes tab right-click on empty pane opens the create menu', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5?tab=notes')
    await screen.findByRole('button', { name: 'New note here' })
    const text = await screen.findByText('No notes here yet.')
    fireEvent.contextMenu(text)
    expect(await screen.findByRole('menu')).toBeInTheDocument()
    expect(
      screen.getByRole('menuitem', { name: 'New note here' })
    ).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Draft notes' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem', { name: 'New note here' }))
    await waitFor(() => expect(createNote).toHaveBeenCalled())
  })

  test('notes tab bulk-deletes and moves the selection to a node', async () => {
    primeDefaults()
    listNotes.mockResolvedValue({
      items: [
        {
          id: '21',
          title: 'Limits note',
          course_id: '3',
          node_id: '5',
          owner_type: 'standalone',
          owner_id: null,
          tags: [],
          pinned: false,
          updated_at: '2026-08-19T00:00:00Z',
        },
        {
          id: '22',
          title: 'Chain note',
          course_id: '3',
          node_id: '5',
          owner_type: 'standalone',
          owner_id: null,
          tags: [],
          pinned: false,
          updated_at: '2026-08-19T00:00:00Z',
        },
      ],
      next_cursor: null,
    })
    deleteNote.mockResolvedValue({ deleted_item_id: '90' })
    moveNote.mockResolvedValue(undefined)
    renderWorkspace('/courses/3/n/5?tab=notes')
    await screen.findByText('Limits note')

    fireEvent.mouseDown(screen.getByText('Limits note'))
    fireEvent.mouseDown(screen.getByText('Chain note'), { ctrlKey: true })

    fireEvent.contextMenu(screen.getByText('Limits note'))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Delete' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(deleteNote).toHaveBeenCalledWith('21'))
    await waitFor(() => expect(deleteNote).toHaveBeenCalledWith('22'))

    fireEvent.mouseDown(screen.getByText('Limits note'))
    fireEvent.mouseDown(screen.getByText('Chain note'), { ctrlKey: true })
    fireEvent.contextMenu(screen.getByText('Limits note'))
    fireEvent.click(await screen.findByRole('menuitem', { name: /Move to node/i }))
    fireEvent.click(await screen.findByRole('treeitem', { name: /Chain rule/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Move' }))
    await waitFor(() => expect(moveNote).toHaveBeenCalledWith('21', '11'))
    await waitFor(() => expect(moveNote).toHaveBeenCalledWith('22', '11'))
  })

  test('notes tab marquee drag selects the intersecting notes without a count bar', async () => {
    primeDefaults()
    listNotes.mockResolvedValue({
      items: [
        {
          id: '21',
          title: 'Limits note',
          course_id: '3',
          node_id: '5',
          owner_type: 'standalone',
          owner_id: null,
          tags: [],
          pinned: false,
          updated_at: '2026-08-19T00:00:00Z',
        },
      ],
      next_cursor: null,
    })
    const rectSpy = vi
      .spyOn(Element.prototype, 'getBoundingClientRect')
      .mockReturnValue({
        left: 0, top: 0, right: 400, bottom: 400, width: 400, height: 400, x: 0, y: 0,
        toJSON: () => ({}),
      } as DOMRect)
    renderWorkspace('/courses/3/n/5?tab=notes')
    await screen.findByText('Limits note')

    const pane = document.querySelector('[data-marquee-surface]') as HTMLElement
    fireEvent.mouseDown(pane, { clientX: 0, clientY: 0, button: 0 })
    fireEvent.mouseMove(window, { clientX: 200, clientY: 200 })
    fireEvent.mouseUp(window, { clientX: 200, clientY: 200 })

    const wrapper = screen
      .getByText('Limits note')
      .closest('[data-selectable-id]') as HTMLElement
    await waitFor(() => expect(wrapper.className).toContain('bg-primary/10'))
    expect(screen.queryByText(/selected/i)).not.toBeInTheDocument()

    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(wrapper.className).not.toContain('bg-primary/10'))
    rectSpy.mockRestore()
  })

  test('notes drag carries the whole selection when a selected note is dragged', async () => {
    primeDefaults()
    listNotes.mockResolvedValue({
      items: [
        {
          id: '21',
          title: 'Limits note',
          course_id: '3',
          node_id: '5',
          owner_type: 'standalone',
          owner_id: null,
          tags: [],
          pinned: false,
          updated_at: '2026-08-19T00:00:00Z',
        },
        {
          id: '22',
          title: 'Chain note',
          course_id: '3',
          node_id: '5',
          owner_type: 'standalone',
          owner_id: null,
          tags: [],
          pinned: false,
          updated_at: '2026-08-19T00:00:00Z',
        },
      ],
      next_cursor: null,
    })
    renderWorkspace('/courses/3/n/5?tab=notes')
    await screen.findByText('Limits note')

    fireEvent.mouseDown(screen.getByText('Limits note'))
    fireEvent.mouseDown(screen.getByText('Chain note'), { ctrlKey: true })

    const payload: Record<string, string> = {}
    const wrapper = screen
      .getByText('Limits note')
      .closest('[data-selectable-id]') as HTMLElement
    fireEvent.mouseDown(screen.getByText('Limits note'))
    fireEvent.dragStart(wrapper, {
      dataTransfer: {
        setData: (mime: string, value: string) => {
          payload[mime] = value
        },
        getData: (mime: string) => payload[mime] ?? '',
        types: ['application/x-sa-item'],
        effectAllowed: '',
      },
    })

    const item = JSON.parse(payload['application/x-sa-item']) as {
      folderIds: string[]
      materialIds: string[]
      noteIds: string[]
    }
    expect(item.noteIds).toEqual(['21', '22'])
  })

  test('notes drag of an unselected note carries just it and selects it', async () => {
    primeDefaults()
    listNotes.mockResolvedValue({
      items: [
        {
          id: '21',
          title: 'Limits note',
          course_id: '3',
          node_id: '5',
          owner_type: 'standalone',
          owner_id: null,
          tags: [],
          pinned: false,
          updated_at: '2026-08-19T00:00:00Z',
        },
      ],
      next_cursor: null,
    })
    renderWorkspace('/courses/3/n/5?tab=notes')
    await screen.findByText('Limits note')

    const payload: Record<string, string> = {}
    const wrapper = screen
      .getByText('Limits note')
      .closest('[data-selectable-id]') as HTMLElement
    fireEvent.dragStart(wrapper, {
      dataTransfer: {
        setData: (mime: string, value: string) => {
          payload[mime] = value
        },
        getData: (mime: string) => payload[mime] ?? '',
        types: ['application/x-sa-item'],
        effectAllowed: '',
      },
    })

    const item = JSON.parse(payload['application/x-sa-item']) as {
      folderIds: string[]
      materialIds: string[]
      noteIds: string[]
    }
    expect(item.noteIds).toEqual(['21'])
    await waitFor(() => expect(wrapper.className).toContain('bg-primary/10'))
  })

})
