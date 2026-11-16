import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useRef } from 'react'

import type { MaterialUploadController } from '@/components/materials/materialUpload'
import { pickFolder } from '@/components/materials/desktopFolder'
import type { ContextMenuItem } from '@/components/ui/ContextMenu'
import { useAcceptedTypes } from '@/lib/useAcceptedTypes'

export function useCreateMaterialMenu({
  upload,
  onNewText,
  onNewFolder,
  onNewUrl,
  onDiscover,
  onCaptureFiles,
  prepend = [],
  append = [],
}: {
  upload: MaterialUploadController
  onNewText: (kind: 'txt' | 'md') => void
  onNewFolder: () => void
  onNewUrl?: () => void
  onDiscover?: () => void
  onCaptureFiles?: (files: FileList) => void
  prepend?: ContextMenuItem[]
  append?: ContextMenuItem[]
}): { items: ContextMenuItem[]; inputs: ReactNode } {
  const { t } = useTranslation()
  const accept = useAcceptedTypes()
  const fileInput = useRef<HTMLInputElement>(null)
  const folderInput = useRef<HTMLInputElement>(null)
  const cameraInput = useRef<HTMLInputElement>(null)

  const items: ContextMenuItem[] = [
    ...prepend,
    ...(onDiscover
      ? [
          {
            key: 'discover',
            label: t('discovery.menuEntry'),
            onSelect: onDiscover,
          },
        ]
      : []),
    ...(onNewUrl
      ? [
          {
            key: 'new-url',
            label: t('importUrl.title'),
            onSelect: onNewUrl,
          },
        ]
      : []),
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
    ...(onCaptureFiles
      ? [
          {
            key: 'capture',
            label: t('captureInbox.menuEntry'),
            onSelect: () => cameraInput.current?.click(),
          },
        ]
      : []),
    {
      key: 'upload-folder',
      label: t('library.uploadFolderMenu'),
      onSelect: pickFolder(upload, folderInput),
    },
    ...append,
  ]

  const inputs = (
    <>
      <input
        ref={fileInput}
        type="file"
        multiple
        accept={accept}
        hidden
        aria-label={t('library.uploadFilesPlain')}
        onChange={(event) => {
          if (event.target.files) {
            void upload.uploadFiles(event.target.files)
          }
          event.target.value = ''
        }}
      />
      {onCaptureFiles ? (
        <input
          ref={cameraInput}
          type="file"
          accept="image/*"
          capture="environment"
          multiple
          hidden
          aria-label={t('captureInbox.cameraInput')}
          onChange={(event) => {
            if (event.target.files && event.target.files.length > 0) {
              onCaptureFiles(event.target.files)
            }
            event.target.value = ''
          }}
        />
      ) : null}
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
