import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'

import './print.css'

export function PrintDoc({
  title,
  contextLine,
  toolbar,
  children,
}: {
  title: string
  contextLine?: string
  toolbar?: React.ReactNode
  children: React.ReactNode
}) {
  const { t } = useTranslation()
  return (
    <div className="print-root" aria-hidden={false}>
      {toolbar ? <div className="no-print mb-4">{toolbar}</div> : null}
      <div className="print-cover">
        <h1>{title}</h1>
        {contextLine ? <p>{contextLine}</p> : null}
        <p>{t('print.generatedBy')}</p>
      </div>
      {children}
    </div>
  )
}

export function useAutoPrint(enabled: boolean, delayMs = 400) {
  useEffect(() => {
    if (!enabled) return undefined
    const timer = window.setTimeout(() => window.print(), delayMs)
    return () => window.clearTimeout(timer)
  }, [enabled, delayMs])
}

export function PrintOverlay({
  title,
  contextLine,
  autoPrint = true,
  toolbar,
  children,
}: {
  title: string
  contextLine?: string
  autoPrint?: boolean
  toolbar?: React.ReactNode
  children: React.ReactNode
}) {
  useAutoPrint(autoPrint)
  return (
    <PrintDoc title={title} contextLine={contextLine} toolbar={toolbar}>
      {children}
    </PrintDoc>
  )
}
