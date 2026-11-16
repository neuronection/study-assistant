import { Lightbulb, X } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { recordActivation } from '@/lib/api'
import type { ActivationStep } from '@/lib/activation-vocab'

function tipKey(id: string): string {
  return `sa-tip.${id}`
}

function wasDismissed(id: string): boolean {
  try {
    return window.localStorage.getItem(tipKey(id)) === '1'
  } catch {
    return true
  }
}

export function OneTimeTip({
  id,
  children,
}: {
  id: ActivationStep
  children: React.ReactNode
}) {
  const { t } = useTranslation()
  const [visible, setVisible] = useState(() => !wasDismissed(id))
  if (!visible) {
    return null
  }
  const dismiss = () => {
    try {
      window.localStorage.setItem(tipKey(id), '1')
    } catch {
      return
    }
    setVisible(false)
    void recordActivation('tip_dismissed', { surface: 'one_time_tip', step: id })
  }
  return (
    <div
      role="note"
      className="border-primary/25 bg-primary/5 flex items-start gap-2 rounded-lg border px-3 py-2"
    >
      <Lightbulb className="text-primary mt-0.5 size-4 shrink-0" aria-hidden />
      <p className="min-w-0 flex-1 text-xs">{children}</p>
      <button
        type="button"
        className="text-muted-foreground hover:text-foreground shrink-0"
        aria-label={t('common.dismiss')}
        onClick={dismiss}
      >
        <X className="size-3.5" aria-hidden />
      </button>
    </div>
  )
}
