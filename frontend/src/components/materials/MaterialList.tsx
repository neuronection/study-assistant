import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

export function MaterialList({
  layout,
  children,
  className,
}: {
  layout: 'grid' | 'list'
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        layout === 'grid'
          ? 'grid grid-cols-[repeat(auto-fill,minmax(140px,1fr))] gap-4 p-2'
          : 'flex flex-col gap-2 p-2',
        className
      )}
    >
      {children}
    </div>
  )
}
