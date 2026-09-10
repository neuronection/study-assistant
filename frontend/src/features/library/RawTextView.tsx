import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { getMaterial } from '@/lib/api'

export function RawTextView({ materialId }: { materialId: number }) {
  const { t } = useTranslation()
  const { data, isLoading } = useQuery({
    queryKey: ['material', materialId],
    queryFn: () => getMaterial(materialId),
  })
  if (isLoading) {
    return <p className="text-muted-foreground p-4 text-sm">{t('library.loading')}</p>
  }
  if (!data?.extraction) {
    return (
      <p className="text-muted-foreground text-sm">
        {t('library.noExtraction', { status: data?.material.status ?? '' })}
      </p>
    )
  }
  return (
    <pre className="bg-subtle border-border max-h-[70vh] overflow-auto rounded-md border p-4 font-mono text-xs whitespace-pre-wrap">
      {data.extraction.markdown}
    </pre>
  )
}
