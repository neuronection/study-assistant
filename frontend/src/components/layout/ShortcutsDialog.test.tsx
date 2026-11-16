import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { ShortcutsDialog } from './ShortcutsDialog'
import { useCaptureStore } from '@/lib/capture-store'
import { useImportUrlStore } from '@/lib/import-url-store'
import { isTypingTarget } from '@/lib/shortcuts'
import { useWorkspaceStore } from '@/lib/workspace-store'

const navigate = vi.fn()

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return { ...actual, useNavigate: () => navigate }
})

const FEATURE_LABELS = [
  'Quick capture a thought',
  'Import from a URL',
  'Record a lecture',
  'Read a page aloud',
  'Open the library',
  'Open split view',
  'Search a transcript',
  'Practise a chapter',
  'Build a mock paper',
  'Solve a problem',
  'Print an answer key',
  'Review due cards',
  'Start Study now',
  'Open Studio',
  'Plan the week',
  'Check processing jobs',
  'Connect Zotero',
  'Connect an AI provider',
  'Back up or move data',
]

describe('ShortcutsDialog', () => {
  beforeEach(() => {
    navigate.mockReset()
    useCaptureStore.setState({ open: false })
    useImportUrlStore.setState({ open: false })
    useWorkspaceStore.getState().setCourse(null)
  })

  test('renders every group and keycap', () => {
    render(<ShortcutsDialog onClose={() => {}} />)
    expect(screen.getByText('Keyboard shortcuts')).toBeInTheDocument()
    for (const heading of ['General', 'Review', 'Library', 'Reading & study']) {
      expect(screen.getAllByRole('heading', { name: heading }).length).toBeGreaterThan(0)
    }
    for (const keys of ['Ctrl+K', 'Ctrl+Shift+K', '?', 'Space', '1–4', 'Enter', 'Ctrl+X', 'Del', 'Esc']) {
      expect(screen.getByText(keys)).toBeInTheDocument()
    }
    expect(screen.getAllByRole('button', { name: 'Close' }).length).toBeGreaterThan(0)
  })

  test('renders the full feature map for every group', () => {
    useWorkspaceStore.getState().setCourse('3')
    render(<ShortcutsDialog onClose={() => {}} />)
    for (const label of FEATURE_LABELS) {
      expect(screen.getByRole('option', { name: label })).toBeInTheDocument()
    }
    for (const group of ['Capture', 'Read', 'Practise', 'Review', 'Organise', 'Configure']) {
      expect(screen.getByRole('group', { name: group })).toBeInTheDocument()
    }
  })

  test('closes on Escape', async () => {
    const onClose = vi.fn()
    render(<ShortcutsDialog onClose={onClose} />)
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  test('finds a feature and opens it from the map', async () => {
    render(<ShortcutsDialog onClose={() => {}} />)
    fireEvent.change(screen.getByRole('combobox', { name: 'Search features' }), {
      target: { value: 'transcript' },
    })
    const feature = screen.getByRole('option', { name: 'Search a transcript' })
    expect(screen.getByText('1 features')).toBeInTheDocument()
    fireEvent.click(feature)
    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith({ to: '/library' }),
    )
  })

  test('Tab inside the feature map focuses chrome instead of selecting', async () => {
    render(<ShortcutsDialog onClose={() => {}} />)
    expect(screen.getAllByRole('dialog')).toHaveLength(1)
    const input = screen.getByRole('combobox', { name: 'Search features' })
    fireEvent.change(input, { target: { value: 'transcript' } })
    input.focus()
    await userEvent.tab()
    expect(navigate).not.toHaveBeenCalled()
    expect(input).not.toHaveFocus()
    expect(document.activeElement?.tagName).toBe('BUTTON')
  })

  test('quick capture runs its action and closes the dialog', () => {
    const onClose = vi.fn()
    render(<ShortcutsDialog onClose={onClose} />)
    fireEvent.click(screen.getByRole('option', { name: 'Quick capture a thought' }))
    expect(onClose).toHaveBeenCalled()
    expect(useCaptureStore.getState().open).toBe(true)
  })

  test('import runs its action and closes the dialog', () => {
    const onClose = vi.fn()
    render(<ShortcutsDialog onClose={onClose} />)
    fireEvent.click(screen.getByRole('option', { name: 'Import from a URL' }))
    expect(onClose).toHaveBeenCalled()
    expect(useImportUrlStore.getState().open).toBe(true)
  })

  test('closes on backdrop click', async () => {
    const onClose = vi.fn()
    render(<ShortcutsDialog onClose={onClose} />)
    await userEvent.click(document.querySelector('[data-as="modal-overlay"]')!)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  test('restores focus to the trigger after closing', async () => {
    function Harness() {
      const [open, setOpen] = useState(false)
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>
            Open shortcuts
          </button>
          {open ? <ShortcutsDialog onClose={() => setOpen(false)} /> : null}
        </>
      )
    }
    render(<Harness />)
    const trigger = screen.getByRole('button', { name: 'Open shortcuts' })
    trigger.focus()
    await userEvent.click(trigger)
    await userEvent.keyboard('{Escape}')
    await waitFor(() => expect(trigger).toHaveFocus())
  })
})

describe('isTypingTarget', () => {
  test('flags inputs, textareas, selects and contenteditable only', () => {
    const element = (html: string) => {
      const parent = document.createElement('div')
      parent.innerHTML = html
      return parent.firstElementChild
    }
    const editable = element('<div></div>') as HTMLElement
    Object.defineProperty(editable, 'isContentEditable', { value: true })
    expect(isTypingTarget(element('<input></input>'))).toBe(true)
    expect(isTypingTarget(element('<textarea></textarea>'))).toBe(true)
    expect(isTypingTarget(element('<select></select>'))).toBe(true)
    expect(isTypingTarget(editable)).toBe(true)
    expect(isTypingTarget(element('<div></div>'))).toBe(false)
    expect(isTypingTarget(window)).toBe(false)
  })
})
