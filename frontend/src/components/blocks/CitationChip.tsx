import { useQuery } from '@tanstack/react-query'
import { BookMarked } from 'lucide-react'
import { useNavigate } from '@tanstack/react-router'

import { getMaterial } from '@/lib/api'
import { cn } from '@/lib/utils'

export function CitationChip({
  materialId,
  className,
}: {
  materialId: string
  className?: string
}) {
  const navigate = useNavigate()
  const material = useQuery({
    queryKey: ['material', materialId],
    queryFn: () => getMaterial(materialId),
    retry: false,
  })
  const citation = material.data?.material
  const label = citation?.citation_text ?? citation?.title ?? materialId

  return (
    <button
      type="button"
      data-testid="citation-chip"
      className={cn(
        'border-border bg-subtle text-foreground hover:border-primary inline-flex max-w-full items-center gap-1 rounded-full border px-2 py-0.5 align-baseline text-[11px]',
        className
      )}
      title={label}
      onClick={() => {
        void navigate({
          to: '/library/$materialId',
          params: { materialId: String(materialId) },
        })
      }}
    >
      <BookMarked className="h-3 w-3 shrink-0" aria-hidden />
      <span className="truncate">{label}</span>
    </button>
  )
}
