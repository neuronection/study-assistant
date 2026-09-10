import { useTranslation } from 'react-i18next'
import { Link2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import type { Folder, FolderDeleteInfo } from '@/lib/api'
import { useCloseFloatings } from '@/lib/ui-overlays'

function countLabel(t: (key: string, options?: Record<string, unknown>) => string, key: string, count: number): string | null {
  if (count === 0) {
    return null
  }
  return t(key, { count })
}

export function FolderDeleteDialog({
  folder,
  info,
  onConfirm,
  onCancel,
}: {
  folder: Folder
  info: FolderDeleteInfo
  onConfirm: () => void
  onCancel: () => void
}) {
  useCloseFloatings()
  const { t } = useTranslation()
  const pathOf = (link: FolderDeleteInfo['node_links'][number]) =>
    link.breadcrumb.map((entry) => entry.title).join(' / ')

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={t('library.deleteFolder')}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onCancel()
        }
      }}
    >
      <div className="bg-surface border-border flex max-h-[80vh] w-full max-w-md flex-col rounded-lg border shadow-xl">
        <header className="border-border border-b px-4 py-2">
          <h2 className="text-sm font-semibold">{t('library.deleteFolder')}</h2>
        </header>
        <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-4">
          <p className="text-muted-foreground text-xs">
            {t('library.folderDeleteMessage', {
              name: folder.name,
              folders: t('library.folderCount', { count: info.subfolders }),
              files: t('library.fileCount', { count: info.materials }),
            })}
          </p>
          {info.node_links.length > 0 ? (
            <>
              <p className="text-muted-foreground text-xs">
                {t('library.folderDeleteLinksTitle')}
              </p>
              <ul className="flex flex-col gap-1">
                {info.node_links.map((link) => {
                  const counts = [
                    countLabel(t, 'library.nodeFolderCount', link.folder_count),
                    countLabel(t, 'library.fileCount', link.material_count),
                  ].filter((entry): entry is string => entry !== null)
                  return (
                    <li
                      key={link.node_id}
                      className="bg-subtle flex items-center gap-2 rounded-md px-2 py-1.5"
                    >
                      <Link2 className="text-muted-foreground size-3.5 shrink-0" />
                      <span className="text-xs">{pathOf(link)}</span>
                      {counts.length > 0 ? (
                        <span className="text-muted-foreground ml-auto shrink-0 text-[10px]">
                          {counts.join(', ')}
                        </span>
                      ) : null}
                    </li>
                  )
                })}
              </ul>
            </>
          ) : null}
        </div>
        <footer className="border-border flex justify-end gap-2 border-t px-4 py-2">
          <Button variant="ghost" size="sm" onClick={onCancel}>
            {t('library.cancelEdit')}
          </Button>
          <Button variant="destructive" size="sm" onClick={onConfirm}>
            {t('library.deleteFolderAndContents')}
          </Button>
        </footer>
      </div>
    </div>
  )
}