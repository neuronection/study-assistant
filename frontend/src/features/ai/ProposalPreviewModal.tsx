import { useTranslation } from 'react-i18next'

import { MarkdownSurface } from '@/components/ui/chat-markdown'
import { PanelModal } from '@/components/ui/modal'
import type { ChatProposal } from '@/lib/api'

import { proposalPreview } from './proposalPreview'

export function ProposalPreviewModal({
  proposal,
  open,
  onOpenChange,
}: {
  proposal: ChatProposal
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { t } = useTranslation()
  const content = open ? proposalPreview(proposal) : null
  return (
    <PanelModal
      open={open}
      onOpenChange={onOpenChange}
      size="xl"
      title={t('ai.proposals.previewTitle')}
      bodyClassName="p-4"
    >
      {content ? (
        <div data-testid="proposal-preview-body">
          {content.title ? (
            <h2 className="mb-3 text-sm font-semibold">{content.title}</h2>
          ) : null}
          <MarkdownSurface value={content.markdown} className="text-sm" />
        </div>
      ) : null}
    </PanelModal>
  )
}
