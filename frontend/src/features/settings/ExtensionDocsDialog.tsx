import ReactMarkdown from 'react-markdown'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  DocsDialog,
  type IntegrationDocsNode,
} from '@/components/ui/integration-docs-dialog'
import { getExtensionDocumentation } from '@/lib/api'
import {
  asDocsTree,
  audienceOfFile,
  docsNodes,
  landingDocFile,
  type DocsTree,
} from './extensionDocsViews'

interface Props {
  extensionId: string
  onClose: () => void
}

/**
 * Bundled-extension documentation (plan 34 wave 8): the kit's DocsDialog
 * owns the tree chrome; the markdown fetch + render ride the app-owned
 * content slot (health's IntegrationDocsDialog is the family shape). The
 * tree is the extensionDocsTree form — the landing rule picks the opening
 * page and the audience tag (when present) renders as a badge.
 */
export function ExtensionDocsDialog({ extensionId, onClose }: Props) {
  const { t, i18n } = useTranslation()
  const [tree, setTree] = useState<DocsTree | null | undefined>(undefined)
  const [currentFile, setCurrentFile] = useState<string | null>(null)
  const [markdown, setMarkdown] = useState('')
  const [contentStatus, setContentStatus] = useState<
    'loading' | 'error' | 'ready'
  >('loading')
  const [errorDetail, setErrorDetail] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getExtensionDocumentation(extensionId)
      .then((data) => {
        if (cancelled) return
        setTree(asDocsTree(data.tree))
        setCurrentFile(landingDocFile(asDocsTree(data.tree)))
      })
      .catch((cause: Error) => {
        if (cancelled) return
        setContentStatus('error')
        setErrorDetail(cause.message)
      })
    return () => {
      cancelled = true
    }
  }, [extensionId])

  useEffect(() => {
    if (!currentFile || currentFile.startsWith('category:')) return
    let cancelled = false
    setContentStatus('loading')
    getExtensionDocumentation(extensionId, currentFile)
      .then((data) => {
        if (cancelled) return
        setMarkdown(data.markdown)
        setContentStatus('ready')
      })
      .catch((cause: Error) => {
        if (cancelled) return
        setContentStatus('error')
        setErrorDetail(cause.message)
      })
    return () => {
      cancelled = true
    }
  }, [extensionId, currentFile])

  const nodes: IntegrationDocsNode[] = docsNodes(asDocsTree(tree), i18n.language)
  const audience = audienceOfFile(asDocsTree(tree), currentFile)

  return (
    <DocsDialog
      open
      onOpenChange={(open) => !open && onClose()}
      docs={nodes}
      selectedId={currentFile}
      onSelect={(nodeId) => {
        if (!nodeId.startsWith('category:')) setCurrentFile(nodeId)
      }}
      status={contentStatus}
      errorDetail={errorDetail}
      renderContent={() => (
        <div className="text-sm leading-relaxed">
          {audience ? (
            <span
              data-testid="extension-docs-audience"
              className="border-border text-muted-foreground mb-3 inline-block rounded-full border px-2 py-0.5 text-[10px] font-medium tracking-wide uppercase"
            >
              {t(`extensionDocs.audience.${audience}`, audience)}
            </span>
          ) : null}
          <ReactMarkdown>{markdown}</ReactMarkdown>
        </div>
      )}
      labels={{
        title: t('extensionDocs.title', 'Documentation'),
        closeLabel: t('common.close'),
        treeLabel: t('extensionDocs.tree', 'Documentation'),
        emptyLabel: t('extensionDocs.empty', 'No documentation provided.'),
        loadingLabel: t('extensionDocs.loading', 'Loading…'),
        errorLabel: t('extensionDocs.error', 'Failed to load documentation.'),
      }}
    />
  )
}
