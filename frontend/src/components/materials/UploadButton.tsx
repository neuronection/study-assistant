import { ChevronDown, FileUp, FolderUp, Loader2, Upload } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useRef } from 'react'

import type { MaterialUploadController } from '@/components/materials/materialUpload'
import { pickFolder } from '@/components/materials/desktopFolder'
import { Button } from '@/components/ui/button'
import { PopoverMenu } from '@/components/ui/popover-menu'
import { cn } from '@/lib/utils'

export function UploadButton({
  upload,
  label,
  size = 'sm',
  variant = 'default',
  className,
}: {
  upload: MaterialUploadController
  label?: string
  size?: 'sm' | 'default'
  variant?: 'default' | 'outline'
  className?: string
}) {
  const { t } = useTranslation()
  const fileInput = useRef<HTMLInputElement>(null)
  const folderInput = useRef<HTMLInputElement>(null)
  const pending = upload.uploading

  return (
    <div className={className}>
      <input
        ref={fileInput}
        type="file"
        multiple
        className="hidden"
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
      <div className="inline-flex">
        <Button
          size={size}
          variant={variant}
          className="rounded-r-none pr-2"
          disabled={pending}
          onClick={() => fileInput.current?.click()}
        >
          {pending ? (
            <Loader2 className="animate-spin" aria-hidden />
          ) : (
            <Upload aria-hidden />
          )}
          {label ?? t('library.upload')}
        </Button>
        <PopoverMenu
          label={t('library.uploadChoose')}
          triggerClassName={cn(
            'h-8 rounded-l-none px-1.5',
            variant === 'outline' && 'border-border border-l-0'
          )}
          panelClassName="w-48"
          trigger={
            pending ? (
              <Loader2 className="size-3.5 animate-spin" aria-hidden />
            ) : (
              <ChevronDown className="size-3.5" aria-hidden />
            )
          }
          items={[
            {
              key: 'files',
              label: t('library.uploadFilesPlain'),
              icon: FileUp,
              disabled: pending,
              onSelect: () => fileInput.current?.click(),
            },
            {
              key: 'folder',
              label: t('library.uploadAFolder'),
              icon: FolderUp,
              disabled: pending,
              onSelect: pickFolder(upload, folderInput),
            },
          ]}
        />
      </div>
    </div>
  )
}
