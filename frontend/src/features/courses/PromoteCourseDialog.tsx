import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { useCloseFloatings } from '@/lib/ui-overlays'

export function PromoteCourseDialog({
  nodeTitle,
  busy,
  error,
  onConfirm,
  onCancel,
}: {
  nodeTitle: string
  busy: boolean
  error: string | null
  onConfirm: (input: {
    title: string
    subject: string | null
    level: string | null
    color: string | null
  }) => void
  onCancel: () => void
}) {
  useCloseFloatings()
  const { t } = useTranslation()
  const [title, setTitle] = useState(nodeTitle)
  const [subject, setSubject] = useState('')
  const [level, setLevel] = useState('')

  const submit = () => {
    const trimmed = title.trim()
    if (!trimmed || busy) {
      return
    }
    onConfirm({
      title: trimmed,
      subject: subject.trim() || null,
      level: level.trim() || null,
      color: null,
    })
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={t('scratchpad.promoteTitle')}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onCancel()
        }
      }}
    >
      <div className="bg-surface border-border w-full max-w-sm rounded-lg border p-4 shadow-xl">
        <h2 className="text-sm font-semibold">{t('scratchpad.promoteTitle')}</h2>
        <p className="text-muted-foreground mt-1 text-xs">
          {t('scratchpad.promoteHint')}
        </p>
        <div className="mt-3 space-y-2">
          <input
            autoFocus
            className="bg-surface border-border w-full rounded-md border px-2 py-1 text-sm"
            placeholder={t('scratchpad.courseNamePlaceholder')}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                submit()
              }
            }}
          />
          <input
            className="bg-surface border-border w-full rounded-md border px-2 py-1 text-sm"
            placeholder={t('scratchpad.subjectPlaceholder')}
            value={subject}
            onChange={(event) => setSubject(event.target.value)}
          />
          <input
            className="bg-surface border-border w-full rounded-md border px-2 py-1 text-sm"
            placeholder={t('scratchpad.levelPlaceholder')}
            value={level}
            onChange={(event) => setLevel(event.target.value)}
          />
          <p className="text-muted-foreground text-[11px]">
            {t('scratchpad.promoteCoverageNote')}
          </p>
          {error !== null ? (
            <p className="text-destructive text-xs" role="alert">
              {error}
            </p>
          ) : null}
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onCancel} disabled={busy}>
            {t('library.cancelEdit')}
          </Button>
          <Button size="sm" disabled={!title.trim() || busy} onClick={submit}>
            {t('scratchpad.promoteConfirm')}
          </Button>
        </div>
      </div>
    </div>
  )
}
