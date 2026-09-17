import { HelpCircle, Sparkles, X } from 'lucide-react'
import { useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { askMaterials } from '@/features/chat/useMaterialAsk'
import type { Material } from '@/lib/api'
import { useCloseFloatings } from '@/lib/ui-overlays'

import { KindIcon } from './KindIcon'
import { ASK_CHIPS, type AskChipKey } from './askChips'

const MAX_ATTACHMENTS = 10

export function AskMaterialsDialog({
  materials,
  onClose,
}: {
  materials: Material[]
  onClose: () => void
}) {
  useCloseFloatings()
  const { t } = useTranslation()
  const [input, setInput] = useState('')
  const [chipKey, setChipKey] = useState<AskChipKey | null>(null)
  const [pending, setPending] = useState(false)
  const [failed, setFailed] = useState(false)

  const multi = materials.length > 1
  const tooMany = materials.length > MAX_ATTACHMENTS
  const content = input.trim()
  const chip =
    chipKey === null
      ? undefined
      : ASK_CHIPS.find(
          (entry) =>
            entry.key === chipKey &&
            t(multi ? (entry.textKeyMulti ?? entry.textKey) : entry.textKey).trim() === content,
        )

  const submit = async () => {
    if (content.length === 0 || pending || tooMany) {
      return
    }
    setPending(true)
    setFailed(false)
    try {
      await askMaterials({
        materials: materials.map(({ id, course_id, title }) => ({ id, course_id, title })),
        title:
          materials.length === 1
            ? (materials[0]!.title)
            : t('library.askAiManyTitle', { count: materials.length }),
        content,
        quizMe: chip?.quizMe === true,
      })
      onClose()
    } catch {
      setFailed(true)
    } finally {
      setPending(false)
    }
  }

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void submit()
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={t('library.askAiDialogTitle')}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose()
        }
      }}
    >
      <div className="bg-surface border-border flex w-full max-w-lg flex-col rounded-lg border shadow-[var(--as-shadow-3)]">
        <header className="border-border flex items-center justify-between border-b px-4 py-2">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <Sparkles className="text-primary size-4" aria-hidden />
            {t('library.askAiDialogTitle')}
          </h2>
          <button
            type="button"
            aria-label={t('chat.close')}
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground rounded p-1"
          >
            <X className="size-4" aria-hidden />
          </button>
        </header>
        <div className="flex flex-col gap-3 p-4">
          <div>
            <p className="text-muted-foreground mb-1.5 text-xs">
              {t('library.askAiAttachedCount', { count: materials.length })}
            </p>
            <div className="border-border flex max-h-24 flex-wrap gap-1 overflow-y-auto border-b pb-2">
              {materials.map((material) => (
                <span
                  key={material.id}
                  className="border-border bg-subtle inline-flex max-w-full items-center gap-1 rounded-full border py-0.5 pl-2 pr-2 text-[11px] font-medium"
                  title={material.title}
                >
                  <KindIcon kind={material.kind} className="text-muted-foreground size-3 shrink-0" />
                  <span className="max-w-[11rem] truncate">{material.title}</span>
                </span>
              ))}
            </div>
          </div>
          {tooMany ? (
            <p className="text-warning text-xs" role="alert">
              {t('library.askAiTooMany', { count: materials.length, max: MAX_ATTACHMENTS })}
            </p>
          ) : null}
          <div className="flex flex-wrap gap-1" role="group" aria-label={t('library.askAiChips')}>
            {ASK_CHIPS.map((entry) => (
              <button
                key={entry.key}
                type="button"
                className={`rounded-full border px-3 py-1.5 text-xs transition-colors ${
                  chipKey === entry.key
                    ? 'border-primary text-primary bg-primary/10'
                    : 'border-border hover:bg-subtle'
                }`}
                onClick={() => {
                  setChipKey(entry.key)
                  setInput(
                    t(multi ? (entry.textKeyMulti ?? entry.textKey) : entry.textKey).trim(),
                  )
                }}
              >
                {t(entry.labelKey)}
              </button>
            ))}
          </div>
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder={t(
              multi ? 'library.askAiPlaceholderMulti' : 'library.askAiPlaceholder',
            )}
            aria-label={t('library.askAiQuestionLabel')}
            rows={3}
            className="border-border bg-surface focus-visible:outline-ring w-full resize-none rounded-md border px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-offset-1"
          />
          {chip?.quizMe === true ? (
            <p className="text-muted-foreground flex items-center gap-1 text-[11px]">
              <HelpCircle className="size-3" aria-hidden />
              {t('library.askAiQuizMeHint')}
            </p>
          ) : null}
          {failed ? (
            <p className="text-danger text-xs" role="alert">
              {t('library.askAiFailed')}
            </p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={() => void submit()}
              disabled={content.length === 0 || pending || tooMany}
            >
              {t('library.askAiSubmit')}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
