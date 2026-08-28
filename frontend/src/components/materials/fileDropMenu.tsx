import { useTranslation } from 'react-i18next'
import { useState, type DragEvent, type ReactNode } from 'react'

import { collectDropFiles } from '@/components/materials/dropFiles'
import type { MaterialUploadController, UploadItem } from '@/components/materials/materialUpload'
import { ContextMenu, type ContextMenuItem } from '@/components/ui/ContextMenu'

interface FileDropMenuState {
  x: number
  y: number
  items: UploadItem[]
  hasFolder: boolean
}

function menuItems(
  state: FileDropMenuState,
  upload: MaterialUploadController,
  t: (key: string) => string
): ContextMenuItem[] {
  const items: ContextMenuItem[] = []
  if (state.hasFolder) {
    items.push({
      key: 'upload-folder',
      label: t('library.uploadFolderMenu'),
      onSelect: () => void upload.uploadFiles(state.items),
    })
  }
  items.push({
    key: 'upload-files',
    label: t('library.uploadFiles'),
    onSelect: () =>
      void upload.uploadFiles(
        state.hasFolder ? state.items.map((item) => ({ file: item.file })) : state.items
      ),
  })
  return items
}

export function useFileDropMenu(
  upload: MaterialUploadController
): {
  onDragOver: (event: DragEvent) => void
  onDrop: (event: DragEvent) => void
  menu: ReactNode
} {
  const { t } = useTranslation()
  const [menu, setMenu] = useState<FileDropMenuState | null>(null)

  const isFileDrag = (event: DragEvent): boolean =>
    Array.from(event.dataTransfer.types).includes('Files')

  const onDragOver = (event: DragEvent) => {
    if (isFileDrag(event) && !event.defaultPrevented) {
      event.preventDefault()
      event.dataTransfer.dropEffect = 'copy'
    }
  }

  const onDrop = (event: DragEvent) => {
    if (event.defaultPrevented) {
      return
    }
    if (!isFileDrag(event)) {
      return
    }
    event.preventDefault()
    void collectDropFiles(event.dataTransfer).then((items) => {
      if (items.length === 0) {
        return
      }
      setMenu({
        x: event.clientX,
        y: event.clientY,
        items,
        hasFolder: items.some((item) => item.relativePath !== undefined),
      })
    })
  }

  const menuEl =
    menu === null ? null : (
      <ContextMenu
        x={menu.x}
        y={menu.y}
        items={menuItems(menu, upload, t)}
        onClose={() => setMenu(null)}
      />
    )

  return { onDragOver, onDrop, menu: menuEl }
}