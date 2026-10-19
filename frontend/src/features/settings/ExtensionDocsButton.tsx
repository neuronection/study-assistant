import { BookOpen } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { ExtensionDocsDialog } from './ExtensionDocsDialog'

/** The per-extension docs affordance (plan 34 wave 8): a 'Docs' action on
 * the connector cards opening the kit dialog on the bundle's docs tree.
 * The backend serves only registry-known bundles; a bundle without a
 * tree answers with an honest "no documentation" page, so the affordance
 * itself never needs to gate. */
export function ExtensionDocsButton({ extensionId }: { extensionId: string }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)

  return (
    <>
      <Button
        size="sm"
        variant="ghost"
        onClick={() => setOpen(true)}
        data-testid={`extension-docs-${extensionId}`}
        title={t('extensionDocs.title', 'Documentation')}
      >
        <BookOpen aria-hidden />
        {t('extensionDocs.open', 'Docs')}
      </Button>
      {open ? (
        <ExtensionDocsDialog
          extensionId={extensionId}
          onClose={() => setOpen(false)}
        />
      ) : null}
    </>
  )
}
