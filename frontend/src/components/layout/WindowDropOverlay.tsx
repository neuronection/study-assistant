import { useEffect, useRef, useState, type DragEvent as ReactDragEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { FolderUp } from 'lucide-react'

import { useFileDropMenu } from '@/components/materials/fileDropMenu'
import type { MaterialUploadController } from '@/components/materials/materialUpload'
import { useWindowDropTarget } from '@/lib/window-drop-store'

interface DragLike {
  dataTransfer?: { types?: readonly string[] } | null
}

function isFileDrag(event: DragLike): boolean {
  return Array.from(event.dataTransfer?.types ?? []).includes('Files')
}

const noopController: MaterialUploadController = {
  uploadFiles: async () => [],
  uploading: false,
  currentName: null,
  errors: [],
  clearErrors: () => {},
  reportError: () => {},
}

export function WindowDropOverlay() {
  const { t } = useTranslation()
  const target = useWindowDropTarget()
  const upload = target?.upload() ?? noopController
  const drop = useFileDropMenu(upload)
  const [dragging, setDragging] = useState(false)
  const counter = useRef(0)

  useEffect(() => {
    const onDragEnter = (event: DragEvent) => {
      if (!isFileDrag(event)) {
        return
      }
      counter.current += 1
      setDragging(true)
    }
    const onDragLeave = (event: DragEvent) => {
      if (!isFileDrag(event)) {
        return
      }
      counter.current = Math.max(0, counter.current - 1)
      if (counter.current === 0) {
        setDragging(false)
      }
    }
    const onDragOver = (event: DragEvent) => {
      const transfer = event.dataTransfer
      if (!isFileDrag(event) || transfer === null) {
        return
      }
      event.preventDefault()
      transfer.dropEffect = 'copy'
    }
    const settle = () => {
      counter.current = 0
      setDragging(false)
    }
    window.addEventListener('dragenter', onDragEnter)
    window.addEventListener('dragleave', onDragLeave)
    window.addEventListener('dragover', onDragOver)
    window.addEventListener('drop', settle)
    window.addEventListener('dragend', settle)
    return () => {
      window.removeEventListener('dragenter', onDragEnter)
      window.removeEventListener('dragleave', onDragLeave)
      window.removeEventListener('dragover', onDragOver)
      window.removeEventListener('drop', settle)
      window.removeEventListener('dragend', settle)
    }
  }, [])

  const onOverlayDrop = (event: ReactDragEvent) => {
    if (target === null) {
      return
    }
    void drop.onDrop(event)
  }

  return (
    <>
      {dragging && target !== null ? (
        <div
          className="bg-primary/5 pointer-events-auto fixed inset-0 z-40 p-3"
          data-testid="window-drop-overlay"
          onDragEnter={(event) => {
            event.preventDefault()
          }}
          onDragOver={(event) => {
            event.preventDefault()
            event.dataTransfer.dropEffect = 'copy'
          }}
          onDrop={onOverlayDrop}
        >
          <div className="border-primary/60 bg-surface/90 pointer-events-none flex h-full w-full flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed">
            <FolderUp className="text-primary size-10" aria-hidden />
            <p className="text-foreground text-lg font-semibold">{t('library.windowDropTitle')}</p>
            <p className="text-muted-foreground text-sm">
              {t('library.windowDropTarget', { target: target.label })}
            </p>
          </div>
        </div>
      ) : null}
      {drop.menu}
    </>
  )
}
