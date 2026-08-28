import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { useCloseFloatings } from '@/lib/ui-overlays'

export function RenameDialog({
  title,
  initialName,
  onConfirm,
  onClose,
}: {
  title: string
  initialName: string
  onConfirm: (name: string) => void
  onClose: () => void
}) {
  useCloseFloatings()
  const { t } = useTranslation()
  const [name, setName] = useState(initialName)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
    inputRef.current?.select()
  }, [])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const trimmed = name.trim()

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose()
        }
      }}
    >
      <form
        className="bg-surface border-border w-full max-w-sm rounded-xl border p-4 shadow-lg"
        onSubmit={(event) => {
          event.preventDefault()
          if (trimmed) {
            onConfirm(trimmed)
          }
        }}
      >
        <h2 className="mb-3 text-sm font-semibold">{title}</h2>
        <input
          ref={inputRef}
          className="bg-surface border-border focus:border-ring w-full rounded-md border px-3 py-2 text-sm outline-none"
          value={name}
          maxLength={300}
          onChange={(event) => setName(event.target.value)}
          aria-label={title}
        />
        <div className="mt-3 flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" size="sm" disabled={!trimmed}>
            {t('common.rename')}
          </Button>
        </div>
      </form>
    </div>
  )
}
