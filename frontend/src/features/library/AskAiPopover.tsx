import { Sparkles } from 'lucide-react'
import { useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Popover } from '@/components/ui/popover'
import { Spinner } from '@/components/ui/spinner'
import { askMaterial, type AskMaterialTarget } from '@/features/chat/useMaterialAsk'
import { KindIcon } from './KindIcon'
import { ASK_CHIPS, type AskChipKey } from './askChips'

export function AskAiPopover({
  material,
  scopeNodeId,
  kind,
}: {
  material: AskMaterialTarget
  scopeNodeId?: number | null
  kind?: string
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [input, setInput] = useState('')
  const [chipKey, setChipKey] = useState<AskChipKey | null>(null)
  const [pending, setPending] = useState(false)
  const [failed, setFailed] = useState(false)

  const submit = async () => {
    const content = input.trim()
    if (content.length === 0 || pending) {
      return
    }
    const chip =
      chipKey === null
        ? undefined
        : ASK_CHIPS.find((entry) => entry.key === chipKey && t(entry.textKey).trim() === content)
    setPending(true)
    setFailed(false)
    try {
      await askMaterial({
        material,
        scopeNodeId,
        content,
        attachments: [{ kind: 'material', id: material.id, title: material.title }],
        mode: 'send',
        quizMe: chip?.quizMe === true,
      })
      setInput('')
      setChipKey(null)
      setOpen(false)
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
    <Popover
      label={t('library.askAiLabel')}
      align="end"
      open={open}
      onOpenChange={setOpen}
      panelClassName="w-[22rem] p-3"
      triggerClassName="border-border bg-surface text-foreground hover:bg-subtle focus-visible:outline-ring focus-visible:outline-2 focus-visible:outline-offset-1 h-8 gap-1.5 rounded-[var(--as-radius-sm)] border px-3 text-xs font-medium"
      trigger={
        <>
          <Sparkles className="size-3.5" aria-hidden />
          {t('library.askAi')}
        </>
      }
    >
      <div className="space-y-2.5">
        <span
          className="bg-subtle border-border inline-flex max-w-full items-center gap-1.5 rounded-full border py-0.5 pl-2 pr-2 text-[11px] font-medium"
          title={t('library.askAiAttached', { title: material.title })}
        >
          <KindIcon kind={kind ?? 'doc'} className="text-muted-foreground size-3 shrink-0" />
          <span className="max-w-[15rem] truncate">{material.title}</span>
        </span>
        <div className="flex flex-wrap gap-1" role="group" aria-label={t('library.askAiChips')}>
          {ASK_CHIPS.map((chip) => (
            <button
              key={chip.key}
              type="button"
              className="border-border hover:bg-subtle rounded-full border px-2.5 py-1 text-xs transition-colors"
              disabled={pending}
              onClick={() => {
                setInput(t(chip.textKey))
                setChipKey(chip.key)
              }}
            >
              {t(chip.labelKey)}
            </button>
          ))}
        </div>
        <textarea
          value={input}
          onChange={(event) => {
            setInput(event.target.value)
            setChipKey(null)
          }}
          onKeyDown={onKeyDown}
          placeholder={t('library.askAiPlaceholder')}
          aria-label={t('library.askAiLabel')}
          rows={2}
          className="bg-surface border-border focus-visible:outline-ring w-full resize-none rounded-md border p-2 text-xs focus-visible:outline-2 focus-visible:outline-offset-1"
        />
        {failed ? (
          <p className="text-danger text-xs" role="alert">
            {t('library.askAiFailed')}
          </p>
        ) : null}
        <div className="flex justify-end">
          <Button
            size="sm"
            disabled={pending || input.trim().length === 0}
            onClick={() => void submit()}
          >
            {pending ? <Spinner /> : null}
            {t('library.askAiSubmit')}
          </Button>
        </div>
      </div>
    </Popover>
  )
}
