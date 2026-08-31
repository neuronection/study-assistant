import { FolderUp, Loader2, Upload } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useRef, useState, type DragEvent } from 'react'

import type { MaterialUploadController } from '@/components/materials/materialUpload'
import { pickFolder } from '@/components/materials/desktopFolder'
import { resolveDropItems } from '@/components/materials/dropFiles'
import { ContextMenu, type ContextMenuItem } from '@/components/ui/ContextMenu'
import { cn } from '@/lib/utils'

export function MaterialUploadDropzone({
  upload,
  variant = 'block',
  label,
  hint,
  className,
}: {
  upload: MaterialUploadController
  variant?: 'block' | 'row'
  label?: string
  hint?: string
  className?: string
}) {
  const { t } = useTranslation()
  const [dragging, setDragging] = useState(false)
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const folderInput = useRef<HTMLInputElement>(null)

  const onDrop = (event: DragEvent<HTMLElement>) => {
    event.preventDefault()
    setDragging(false)
    if (!upload.uploading) {
      void resolveDropItems(event.dataTransfer).then((items) => {
        if (items.length > 0) {
          void upload.uploadFiles(items)
        }
      })
    }
  }

  const dropProps = {
    onDragOver: (event: DragEvent<HTMLElement>) => {
      event.preventDefault()
      setDragging(true)
    },
    onDragLeave: () => setDragging(false),
    onDrop,
  }

  const openBannerMenu = (event: React.MouseEvent<HTMLElement>) => {
    event.preventDefault()
    setMenu({ x: event.clientX, y: event.clientY })
  }

  const uploadItems: ContextMenuItem[] = [
    {
      key: 'files',
      label: t('library.uploadFiles'),
      onSelect: () => fileInput.current?.click(),
    },
    {
      key: 'folder',
      label: t('library.uploadFolderMenu'),
      onSelect: pickFolder(upload, folderInput),
    },
  ]

  const folderInputEl = (
    <input
      ref={folderInput}
      type="file"
      multiple
      className="hidden"
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
  )

  const folderButton = (className: string, labelKey: string) => (
    <button
      type="button"
      className={className}
      title={t('library.uploadAFolder')}
      disabled={upload.uploading}
      onClick={pickFolder(upload, folderInput)}
    >
      <FolderUp className="size-3.5" aria-hidden />
      {t(labelKey)}
    </button>
  )

  const hiddenInputs = (
    <>
      <input
        ref={fileInput}
        type="file"
        multiple
        className="hidden"
        aria-label={label ?? t('library.dropOrBrowse')}
        onChange={(event) => {
          if (event.target.files) {
            void upload.uploadFiles(event.target.files)
          }
          event.target.value = ''
        }}
      />
      {folderInputEl}
    </>
  )

  const errors =
    upload.errors.length > 0 ? (
      <p className="text-danger text-xs">
        {upload.errors
          .slice(0, 3)
          .map((error) => t('library.uploadFailedName', { name: error.name }))
          .join(' · ')}
        {upload.errors.length > 3
          ? ` ${t('library.uploadFailedMore', { count: upload.errors.length - 3 })}`
          : ''}
      </p>
    ) : null

  const labelText = upload.uploading
    ? t('library.uploadingName', { name: upload.currentName })
    : (label ?? t('library.dropOrBrowse'))

  const banner = (iconSize: string, layout: string) => (
    <div
      role="button"
      tabIndex={0}
      aria-label={t('library.uploadChoose')}
      className={cn(
        'border-border hover:bg-subtle flex cursor-pointer rounded-lg border border-dashed transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
        layout,
        dragging && 'border-primary bg-primary/5',
        upload.uploading && 'pointer-events-none opacity-70'
      )}
      onClick={openBannerMenu}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          setMenu({
            x: (event.currentTarget as HTMLElement).getBoundingClientRect().left,
            y: (event.currentTarget as HTMLElement).getBoundingClientRect().bottom + 4,
          })
        }
      }}
      {...dropProps}
    >
      {upload.uploading ? (
        <Loader2 className={cn('text-muted-foreground shrink-0 animate-spin', iconSize)} aria-hidden />
      ) : (
        <Upload className={cn('text-muted-foreground shrink-0', iconSize)} aria-hidden />
      )}
      <span className={cn('truncate', layout.includes('flex-col') ? 'text-sm' : 'flex-1')}>
        {labelText}
      </span>
      {hint ? <span className="text-muted-foreground text-xs">{hint}</span> : null}
    </div>
  )

  const menuEl = menu !== null ? (
    <ContextMenu x={menu.x} y={menu.y} items={uploadItems} onClose={() => setMenu(null)} />
  ) : null

  if (variant === 'row') {
    return (
      <div className={cn('space-y-1', className)}>
        {hiddenInputs}
        <div className="flex items-center gap-2">
          {banner('size-4', 'flex-1 items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm')}
          {folderButton(
            'text-muted-foreground hover:text-foreground flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-[11px] disabled:opacity-50',
            'library.uploadFolderShort'
          )}
        </div>
        {hint ? (
          <p className="text-muted-foreground px-1 text-xs">{hint}</p>
        ) : null}
        {errors}
        {menuEl}
      </div>
    )
  }

  return (
    <div className={cn('space-y-1', className)}>
      {hiddenInputs}
      {banner('size-5', 'flex-col items-center gap-1 rounded-lg px-3 py-6 text-center')}
      <div className="flex justify-center">
        {folderButton(
          'text-muted-foreground hover:text-foreground flex items-center gap-1 rounded px-2 py-1 text-xs disabled:opacity-50',
          'library.uploadAFolder'
        )}
      </div>
      {errors}
      {menuEl}
    </div>
  )
}
