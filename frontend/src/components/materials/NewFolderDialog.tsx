import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { useCloseFloatings } from '@/lib/ui-overlays'

export function NewFolderDialog({
  title,
  namePlaceholder,
  onConfirm,
  onCancel,
}: {
  title: string
  namePlaceholder: string
  onConfirm: (name: string) => void
  onCancel: () => void
}) {
  useCloseFloatings()
  const { t } = useTranslation()
  const [name, setName] = useState('')

  const submit = () => {
    const trimmed = name.trim()
    if (!trimmed) {
      return
    }
    onConfirm(trimmed)
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onCancel()
        }
      }}
    >
      <div className="bg-surface border-border w-full max-w-sm rounded-lg border p-4 shadow-xl">
        <h2 className="text-sm font-semibold">{title}</h2>
        <input
          autoFocus
          className="bg-surface border-border mt-3 w-full rounded-md border px-2 py-1 text-sm"
          placeholder={namePlaceholder}
          value={name}
          onChange={(event) => setName(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              submit()
            }
          }}
        />
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onCancel}>
            {t('library.cancelEdit')}
          </Button>
          <Button size="sm" disabled={!name.trim()} onClick={submit}>
            {t('newTextFile.create')}
          </Button>
        </div>
      </div>
    </div>
  )
}
