import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { MaterialBrowser, MaterialBrowserSkeleton, type MaterialFolderSpec } from './MaterialBrowser'

function spec(overrides: Partial<MaterialFolderSpec> = {}): MaterialFolderSpec {
  return {
    key: 'f1',
    name: 'Lectures',
    onOpen: vi.fn(),
    ...overrides,
  }
}

describe('MaterialBrowser', () => {
  test('renders folder items and opens on double-click', () => {
    const onOpen = vi.fn()
    render(
      <MaterialBrowser
        view="grid"
        folders={[spec({ onOpen }), spec({ key: 'f2', name: 'Linked source', linked: true, onOpen })]}
      >
        <button type="button">chain-rule.pdf</button>
      </MaterialBrowser>
    )
    expect(screen.getByText('Lectures')).toBeInTheDocument()
    expect(screen.getByText('Linked source')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'chain-rule.pdf' })).toBeInTheDocument()

    fireEvent.doubleClick(screen.getByText('Lectures'))
    expect(onOpen).toHaveBeenCalledTimes(1)
  })

  test('list view opens via the row name button and shows trailing slot', () => {
    const onOpen = vi.fn()
    render(
      <MaterialBrowser
        view="list"
        folders={[spec({ onOpen, trailing: <span>Nested count</span> })]}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: 'Lectures' }), { detail: 0 })
    expect(onOpen).toHaveBeenCalledTimes(1)
    expect(screen.getByText('Nested count')).toBeInTheDocument()
  })

  test('keyboard click opens in grid view', () => {
    const onOpen = vi.fn()
    render(<MaterialBrowser view="grid" folders={[spec({ onOpen })]} />)
    fireEvent.click(screen.getByText('Lectures'), { detail: 0 })
    expect(onOpen).toHaveBeenCalledTimes(1)
  })

  test('renders breadcrumbs and extra crumb actions', () => {
    const onCrumb = vi.fn()
    render(
      <MaterialBrowser
        view="grid"
        folders={[]}
        crumbs={[
          { key: 'root', label: 'Materials', onClick: onCrumb },
          { key: 'f1', label: 'Lectures' },
        ]}
        crumbsExtra={<button type="button">Open in library</button>}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: 'Materials' }))
    expect(onCrumb).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: 'Open in library' })).toBeInTheDocument()
  })

  test('renders spec.render instead of a folder button (rename form case)', () => {
    render(
      <MaterialBrowser
        view="grid"
        folders={[
          spec({
            render: (
              <form aria-label="Rename folder">
                <input aria-label="Folder name" />
              </form>
            ),
          }),
        ]}
      />
    )
    expect(screen.queryByText('Lectures')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Rename folder')).toBeInTheDocument()
  })

  test('selection and drop-highlight classes land on the folder root', () => {
    const { container } = render(
      <MaterialBrowser
        view="grid"
        folders={[spec({ selectionState: 'selected' }), spec({ key: 'f2', name: 'B', dropHighlighted: true })]}
      />
    )
    const selected = container.querySelector('[data-selectable-id="f1"]')
    expect(selected?.className).toContain('bg-primary/10')
    const highlighted = container.querySelector('[data-selectable-id="f2"]')
    expect(highlighted?.className).toContain('ring-2')
  })
})

describe('MaterialBrowserSkeleton', () => {
  test('grid view renders tile-shaped placeholders in a busy container', () => {
    const { container } = render(<MaterialBrowserSkeleton view="grid" count={4} />)
    expect(container.firstElementChild).toHaveAttribute('aria-busy', 'true')
    const tiles = container.querySelectorAll('[data-as="skeleton"]')
    expect(tiles).toHaveLength(4 * 3)
    expect(container.firstElementChild?.className).toContain('grid')
  })

  test('list view renders row-shaped placeholders', () => {
    const { container } = render(<MaterialBrowserSkeleton view="list" count={3} />)
    expect(container.firstElementChild).toHaveAttribute('aria-busy', 'true')
    expect(container.querySelectorAll('[data-as="skeleton"]')).toHaveLength(3 * 3)
    expect(container.firstElementChild?.className).toContain('flex-col')
  })

  test('defaults to eight placeholders', () => {
    const { container } = render(<MaterialBrowserSkeleton view="grid" />)
    expect(container.querySelectorAll('[data-as="skeleton"]')).toHaveLength(8 * 3)
  })
})
