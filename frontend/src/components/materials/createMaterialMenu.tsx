import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useRef } from 'react'

import type { MaterialUploadController } from '@/components/materials/materialUpload'
import type { ContextMenuItem } from '@/components/ui/ContextMenu'

export function useCreateMaterialMenu({
  upload,
  onNewText,
  onNewFolder,
  prepend = [],
  append = [],
}: {
  upload: MaterialUploadController
  onNewText: (kind: 'txt' | 'md') => void
  onNewFolder: () => void
  prepend?: ContextMenuItem[]
  append?: ContextMenuItem[]
}): { items: ContextMenuItem[]; inputs: ReactNode } {
  const { t } = useTranslation()
  const fileInput = useRef<HTMLInputElement>(null)
  const folderInput = useRef<HTMLInputElement>(null)

  const items: ContextMenuItem[] = [
    ...prepend,
    {
      key: 'new-folder',
      label: t('library.newFolder'),
      onSelect: onNewFolder,
    },
    {
      key: 'new-text',
      label: t('library.newTextFile'),
      onSelect: () => onNewText('txt'),
    },
    {
      key: 'new-md',
      label: t('library.newMarkdownFile'),
      onSelect: () => onNewText('md'),
    },
    {
      key: 'upload',
      label: t('library.uploadFiles'),
      onSelect: () => fileInput.current?.click(),
    },
    {
      key: 'upload-folder',
      label: t('library.uploadFolderMenu'),
      onSelect: () => folderInput.current?.click(),
    },
    ...append,
  ]

  const inputs = (
    <>
      <input
        ref={fileInput}
        type="file"
        multiple
        hidden
        aria-label={t('library.uploadFilesPlain')}
        onChange={(event) => {
          if (event.target.files) {
            void upload.uploadFiles(event.target.files)
          }
          event.target.value = ''
        }}
      />
      <input
        ref={folderInput}
        type="file"
        multiple
        hidden
        // @ts-expect-error non-standard but universally supported directory picker
        webkitdirectory=""
        aria-label={t('library.uploadAFolder')}
        onChange={(event) => {
          if (event.target.files) {
            void upload.uploadFiles(event.target.files)
          }
          event.target.value = ''
        }}
      />
    </>
  )

  return { items, inputs }
}
