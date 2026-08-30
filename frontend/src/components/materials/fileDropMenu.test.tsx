import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { useFileDropMenu } from './fileDropMenu'
import type { MaterialUploadController } from './materialUpload'

function upload(): MaterialUploadController {
  return {
    uploadFiles: vi.fn().mockResolvedValue([]),
    uploading: false,
    currentName: null,
    errors: [],
    clearErrors: vi.fn(),
    reportError: vi.fn(),
  }
}

function Harness({ controller }: { controller: MaterialUploadController }) {
  const drop = useFileDropMenu(controller)
  return (
    <div data-testid="pane" onDragOver={drop.onDragOver} onDrop={drop.onDrop}>
      pane
      {drop.menu}
    </div>
  )
}

describe('useFileDropMenu', () => {
  test('file drop opens a menu with only the files option', async () => {
    const controller = upload()
    render(<Harness controller={controller} />)
    const pane = screen.getByTestId('pane')
    const file = new File(['x'], 'notes.pdf')
    fireEvent.drop(pane, {
      clientX: 50,
      clientY: 60,
      dataTransfer: {
        types: ['Files'],
        items: [file],
        files: [file],
      } as unknown as DataTransfer,
    })
    expect(await screen.findByRole('menuitem', { name: 'Upload files…' })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Upload folder…' })).not.toBeInTheDocument()
  })

  test('folder drop offers both folder and files options and uploads as a folder', async () => {
    const controller = upload()
    render(<Harness controller={controller} />)
    const pane = screen.getByTestId('pane')
    const file = new File(['x'], 'a.pdf')
    Object.defineProperty(file, 'webkitRelativePath', { value: 'pack/a.pdf' })
    const children = [
      { isFile: true, isDirectory: false, name: 'a.pdf', file: (ok: (f: File) => void) => ok(file) },
    ]
    const dirEntry = {
      isFile: false,
      isDirectory: true,
      name: 'pack',
      createReader: () => ({
        readEntries: (success: (entries: unknown[]) => void) => {
          success(children.slice())
          children.length = 0
        },
      }),
    }
    fireEvent.drop(pane, {
      clientX: 50,
      clientY: 60,
      dataTransfer: {
        types: ['Files'],
        items: [{ webkitGetAsEntry: () => dirEntry }],
        files: [file],
      } as unknown as DataTransfer,
    })
    expect(await screen.findByRole('menuitem', { name: 'Upload folder…' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Upload files…' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('menuitem', { name: 'Upload folder…' }))
    await waitFor(() =>
      expect(controller.uploadFiles).toHaveBeenCalledWith([
        { file, relativePath: 'pack/a.pdf' },
      ])
    )
  })

  test('non-file drags are ignored', async () => {
    const controller = upload()
    render(<Harness controller={controller} />)
    const pane = screen.getByTestId('pane')
    fireEvent.drop(pane, {
      clientX: 50,
      clientY: 60,
      dataTransfer: {
        types: ['application/x-ca-item'],
        items: [],
        files: [],
      } as unknown as DataTransfer,
    })
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(controller.uploadFiles).not.toHaveBeenCalled()
  })
})