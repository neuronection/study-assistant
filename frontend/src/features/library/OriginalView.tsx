import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { apiFetch, blobUrl, getMaterial } from '@/lib/api'

export function OriginalView({ materialId }: { materialId: number }) {
  const { t } = useTranslation()
  const { data } = useQuery({
    queryKey: ['material', materialId],
    queryFn: () => getMaterial(materialId),
  })
  const material = data?.material
  const isText =
    material !== undefined &&
    (material.mime?.startsWith('text/') ||
      material.kind === 'txt' ||
      material.kind === 'md')
  const text = useQuery({
    queryKey: ['material-text', materialId, material?.blob_sha ?? ''],
    queryFn: async () => {
      const response = await apiFetch(blobUrl(material?.blob_sha as string))
      if (!response.ok) {
        throw new Error(`blob fetch failed: ${response.status}`)
      }
      return response.text()
    },
    enabled: isText && Boolean(material?.blob_sha),
  })

  if (!material?.blob_sha) {
    return (
      <p className="text-muted-foreground text-sm">{t('library.noOriginal')}</p>
    )
  }
  const url = blobUrl(material.blob_sha)
  if (material.mime?.startsWith('image/')) {
    return <img src={url} alt={material.title} className="max-h-[70vh] w-full rounded-md object-contain" />
  }
  if (isText) {
    if (text.isLoading) {
      return <p className="text-muted-foreground text-sm">{t('library.loading')}</p>
    }
    if (text.isError) {
      return (
        <a href={url} className="text-primary text-sm underline" target="_blank" rel="noreferrer">
          {t('library.openOriginal')}
        </a>
      )
    }
    return (
      <pre className="bg-subtle border-border max-h-[70vh] overflow-auto rounded-md border p-4 font-mono text-xs whitespace-pre-wrap">
        {text.data}
      </pre>
    )
  }
  if (material.mime === 'application/pdf' || material.kind === 'pdf') {
    return (
      <iframe src={url} title={material.title} className="h-[70vh] w-full rounded-md border-none" />
    )
  }
  return (
    <a href={url} className="text-primary text-sm underline" target="_blank" rel="noreferrer">
      {t('library.openOriginal')}
    </a>
  )
}
