import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { FormModal, Input } from '@neuronection/assistant-ui'
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
    const input = inputRef.current
    if (input) {
      input.focus()
      input.select()
    }
  }, [])

  const trimmed = name.trim()

  return (
    <FormModal
      open
      onOpenChange={(next) => {
        if (!next) {
          onClose()
        }
      }}
      title={title}
      submitLabel={t('common.rename')}
      cancelLabel={t('common.cancel')}
      submitDisabled={!trimmed}
      onSubmit={() => onConfirm(trimmed)}
      size="sm"
    >
      <Input
        ref={inputRef}
        aria-label={title}
        value={name}
        maxLength={300}
        onChange={(event) => setName(event.target.value)}
      />
    </FormModal>
  )
}
