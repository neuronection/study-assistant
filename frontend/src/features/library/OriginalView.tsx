import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { apiFetch, blobUrl, getMaterial } from '@/lib/api'

export function OriginalView({ materialId }: { materialId: string }) {
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
  const isPdf =
    material !== undefined &&
    (material.mime === 'application/pdf' || material.kind === 'pdf')
  const pdfSha = isPdf ? material?.blob_sha : undefined
  const [pdfUrl, setPdfUrl] = useState<string | null>(null)
  const [pdfError, setPdfError] = useState(false)

  useEffect(() => {
    if (!pdfSha) {
      setPdfUrl(null)
      setPdfError(false)
      return
    }
    let cancelled = false
    let objectUrl: string | null = null
    setPdfUrl(null)
    setPdfError(false)
    void (async () => {
      try {
        const response = await apiFetch(blobUrl(pdfSha))
        if (!response.ok) {
          throw new Error(`blob fetch failed: ${response.status}`)
        }
        const blob = await response.blob()
        if (cancelled) return
        objectUrl = URL.createObjectURL(blob)
        setPdfUrl(objectUrl)
      } catch {
        if (!cancelled) setPdfError(true)
      }
    })()
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [pdfSha])

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
  if (isPdf) {
    if (pdfError) {
      return (
        <a href={url} className="text-primary text-sm underline" target="_blank" rel="noreferrer">
          {t('library.openOriginal')}
        </a>
      )
    }
    if (!pdfUrl) {
      return <p className="text-muted-foreground text-sm">{t('library.loading')}</p>
    }
    return (
      <iframe src={pdfUrl} title={material.title} className="h-[70vh] w-full rounded-md border-none" />
    )
  }
  return (
    <a href={url} className="text-primary text-sm underline" target="_blank" rel="noreferrer">
      {t('library.openOriginal')}
    </a>
  )
}
