import type { ReactNode } from 'react'

import { InfoButton } from '@/components/ui/InfoButton'

export function FieldLabel({
  children,
  info,
  infoTitle,
}: {
  children: ReactNode
  info: ReactNode
  infoTitle?: ReactNode
}) {
  return (
    <span className="group flex items-center gap-1 text-xs">
      <span>{children}</span>
      <InfoButton title={infoTitle}>{info}</InfoButton>
    </span>
  )
}