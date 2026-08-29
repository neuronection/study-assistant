import { useCallback, useState } from 'react'

import { ConfirmationModal } from '@neuronection/assistant-ui'

export interface ConfirmOptions {
  title: string
  description?: string
  confirmLabel?: string
  cancelLabel?: string
  destructive?: boolean
}

type Pending = { options: ConfirmOptions; resolve: (ok: boolean) => void } | null

export function useConfirm() {
  const [pending, setPending] = useState<Pending>(null)

  const confirm = useCallback(
    (options: ConfirmOptions) =>
      new Promise<boolean>((resolve) => setPending({ options, resolve })),
    [],
  )

  const settle = (ok: boolean) => {
    if (pending) {
      pending.resolve(ok)
      setPending(null)
    }
  }

  const element =
    pending === null ? null : (
      <ConfirmationModal
        open
        onOpenChange={(open) => {
          if (!open) settle(false)
        }}
        onConfirm={() => settle(true)}
        title={pending.options.title}
        description={pending.options.description}
        confirmLabel={pending.options.confirmLabel ?? pending.options.title}
        cancelLabel={pending.options.cancelLabel ?? 'Cancel'}
        destructive={pending.options.destructive ?? true}
        size="sm"
      />
    )

  return [confirm, element] as const
}
