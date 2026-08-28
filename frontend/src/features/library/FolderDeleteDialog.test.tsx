import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { FolderDeleteDialog } from './FolderDeleteDialog'
import type { Folder, FolderDeleteInfo } from '@/lib/api'

const FOLDER: Folder = {
  id: 11,
  name: 'Lectures',
  path: 'Lectures',
  course_id: 3,
  parent_id: null,
  source_id: null,
  created_at: '2026-08-22T00:00:00Z',
}

const INFO: FolderDeleteInfo = {
  subfolders: 1,
  materials: 2,
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
    {
      node_id: 15,
      owner_title: 'Exercises',
      breadcrumb: [
        { id: 2, title: 'Calculus' },
        { id: 15, title: 'Exercises' },
      ],
      is_course_level: false,
      course_title: 'Calculus',
      folder_count: 0,
      material_count: 2,
    },
  ],
}

function renderDialog(onConfirm = () => undefined, onCancel = () => undefined) {
  render(
    <FolderDeleteDialog
      folder={FOLDER}
      info={INFO}
      onConfirm={onConfirm}
      onCancel={onCancel}
    />
  )
}

describe('FolderDeleteDialog', () => {
  test('summarizes the subtree and lists each linked path with counts', () => {
    renderDialog()
    expect(screen.getByRole('dialog', { name: 'Delete folder' })).toBeInTheDocument()
    expect(
      screen.getByText(
        'Deleting \'Lectures\' permanently removes 1 subfolder and 2 files.'
      )
    ).toBeInTheDocument()
    expect(screen.getByText('Calculus / Limits')).toBeInTheDocument()
    expect(screen.getByText('1 folder')).toBeInTheDocument()
    expect(screen.getByText('Calculus / Exercises')).toBeInTheDocument()
    expect(screen.getByText('2 files')).toBeInTheDocument()
  })

  test('confirm fires onConfirm', () => {
    const onConfirm = vi.fn()
    renderDialog(onConfirm)
    fireEvent.click(screen.getByRole('button', { name: 'Delete folder and contents' }))
    expect(onConfirm).toHaveBeenCalled()
  })

  test('cancel button cancels', () => {
    const onCancel = vi.fn()
    renderDialog(() => undefined, onCancel)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onCancel).toHaveBeenCalled()
  })

  test('no links renders no link section', () => {
    render(
      <FolderDeleteDialog
        folder={FOLDER}
        info={{ subfolders: 0, materials: 0, node_links: [] }}
        onConfirm={() => undefined}
        onCancel={() => undefined}
      />
    )
    expect(screen.queryByText('Also removes links from:')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete folder and contents' })).toBeInTheDocument()
  })
})