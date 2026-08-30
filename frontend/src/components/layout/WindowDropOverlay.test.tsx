import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { WindowDropOverlay } from './WindowDropOverlay'
import type { MaterialUploadController } from '@/components/materials/materialUpload'
import {
  clearWindowDropTarget,
  useWindowDropRegistration,
} from '@/lib/window-drop-store'

function dragEvent(type: string, dataTransfer: Partial<DataTransfer>): DragEvent {
  const event = new Event(type) as unknown as DragEvent
  Object.defineProperty(event, 'dataTransfer', { value: dataTransfer })
  return event
}

function controller(): MaterialUploadController {
  return {
    uploadFiles: vi.fn().mockResolvedValue([]),
    uploading: false,
    currentName: null,
    errors: [],
    clearErrors: vi.fn(),
    reportError: vi.fn(),
  }
}

function Harness({ upload, label }: { upload: MaterialUploadController; label: string }) {
  useWindowDropRegistration(true, label, () => upload)
  return <WindowDropOverlay />
}

function filesTransfer(files: File[]): Partial<DataTransfer> {
  return { types: ['Files'], items: [] as unknown as DataTransferItemList, files } as unknown as Partial<DataTransfer>
}

afterEach(() => {
  clearWindowDropTarget()
})

describe('WindowDropOverlay', () => {
  test('no overlay without a registered target', () => {
    render(<WindowDropOverlay />)
    act(() => {
      window.dispatchEvent(dragEvent('dragenter', { types: ['Files'] }))
    })
    expect(screen.queryByTestId('window-drop-overlay')).not.toBeInTheDocument()
  })

  test('shows on drag hover with the target label and hides when the drag leaves', () => {
    const upload = controller()
    render(<Harness upload={upload} label="Calculus I" />)
    act(() => {
      window.dispatchEvent(dragEvent('dragenter', { types: ['Files'] }))
    })
    expect(screen.getByTestId('window-drop-overlay')).toBeInTheDocument()
    expect(screen.getByText('Drop to upload')).toBeInTheDocument()
    expect(screen.getByText('Uploads go to Calculus I')).toBeInTheDocument()
    act(() => {
      window.dispatchEvent(dragEvent('dragleave', { types: ['Files'] }))
    })
    expect(screen.queryByTestId('window-drop-overlay')).not.toBeInTheDocument()
  })

  test('ignores non-file drags', () => {
    const upload = controller()
    render(<Harness upload={upload} label="Calculus I" />)
    act(() => {
      window.dispatchEvent(dragEvent('dragenter', { types: ['application/ca-node'] }))
    })
    expect(screen.queryByTestId('window-drop-overlay')).not.toBeInTheDocument()
  })

  test('dropping files opens the upload menu and uploads via the target', async () => {
    const upload = controller()
    render(<Harness upload={upload} label="Calculus I" />)
    act(() => {
      window.dispatchEvent(dragEvent('dragenter', { types: ['Files'] }))
    })
    const overlay = screen.getByTestId('window-drop-overlay')
    const file = new File(['x'], 'notes.pdf', { type: 'application/pdf' })
    fireEvent.drop(overlay, {
      clientX: 120,
      clientY: 140,
      dataTransfer: filesTransfer([file]),
    })
    expect(await screen.findByRole('menuitem', { name: 'Upload files…' })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Upload folder…' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Upload files…' }))
    await waitFor(() => expect(upload.uploadFiles).toHaveBeenCalledTimes(1))
  })

  test('dropping a folder offers the folder option and keeps relative paths', async () => {
    const upload = controller()
    render(<Harness upload={upload} label="Calculus I" />)
    act(() => {
      window.dispatchEvent(dragEvent('dragenter', { types: ['Files'] }))
    })
    const overlay = screen.getByTestId('window-drop-overlay')
    const file = new File(['x'], 'a.pdf')
    Object.defineProperty(file, 'webkitRelativePath', { value: 'pack/a.pdf' })
    const dirEntry = {
      isFile: false,
      isDirectory: true,
      name: 'pack',
      createReader: () => {
        const children = [
          {
            isFile: true,
            isDirectory: false,
            name: 'a.pdf',
            file: (ok: (f: File) => void) => ok(file),
          },
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
      files: [],
    } as unknown as DataTransfer
    fireEvent.drop(overlay, { clientX: 10, clientY: 10, dataTransfer: transfer })
    expect(await screen.findByRole('menuitem', { name: 'Upload folder…' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Upload folder…' }))
    await waitFor(() => expect(upload.uploadFiles).toHaveBeenCalledTimes(1))
    const items = vi.mocked(upload.uploadFiles).mock.calls[0][0] as { relativePath?: string }[]
    expect(items[0].relativePath).toBe('pack/a.pdf')
  })
})
