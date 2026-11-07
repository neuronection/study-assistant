import { useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import { Heart } from 'lucide-react'
import {
  FamilyMenu,
  NeuronectionMark,
  NeuronectionWordmark,
  SponsorCard,
} from '@neuronection/assistant-ui'
import packageJson from '../../../package.json'

import { Modal, ModalContent } from '@/components/ui/modal'
import { NEURONECTION_URL, SPONSOR_CHANNELS } from '@/config/funding'
import { UpdateBadge } from './UpdateBadge'

const fundPillClass =
  'focus-visible:outline-ring inline-flex h-8 items-center gap-1.5 rounded-full border border-rose-500/20 bg-rose-500/10 px-3 text-xs font-medium text-rose-600 transition-colors hover:bg-rose-500/20 focus-visible:outline-2 focus-visible:outline-offset-2 [&_svg]:size-4 dark:text-rose-400'
const aboutPillClass =
  'focus-visible:outline-ring inline-flex h-8 items-center rounded-full px-3 text-xs font-medium text-muted-foreground transition-colors hover:bg-subtle hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2'
const fundPillCompactClass =
  'focus-visible:outline-ring inline-flex h-7 items-center gap-1 rounded-full border border-rose-500/20 bg-rose-500/10 px-2.5 text-[11px] font-medium text-rose-600 transition-colors hover:bg-rose-500/20 focus-visible:outline-2 focus-visible:outline-offset-2 [&_svg]:size-3.5 dark:text-rose-400'
const aboutPillCompactClass =
  'focus-visible:outline-ring inline-flex h-7 items-center rounded-full px-2.5 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-subtle hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2'

/**
 * Sidebar footer project block: family branding, the family switcher,
 * About and Fund actions plus the version. Copy comes from i18n and the
 * sponsor channels from config (ADR-006 keeps this app-side). `compact`
 * (short viewports) slims the pills so the nav list keeps the space.
 */
export function SidebarFooter({ compact = false }: { compact?: boolean }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [fundOpen, setFundOpen] = useState(false)

  return (
    <div className="flex flex-col items-center gap-2">
      <a
        href={NEURONECTION_URL}
        target="_blank"
        rel="noreferrer"
        aria-label={t('footer.partOfFamily', 'Part of Neuronection')}
        className="focus-visible:outline-ring flex min-w-0 max-w-full flex-wrap self-start items-center gap-x-1 gap-y-0.5 text-[11px] text-muted-foreground transition-colors hover:text-primary focus-visible:outline-2 focus-visible:outline-offset-2"
      >
        <span>{t('footer.partOf')}</span>
        <NeuronectionMark size={16} />
        <NeuronectionWordmark height={12} />
        <span className="text-muted-foreground/70">{t('footer.family')}</span>
      </a>
      <div className="flex flex-wrap items-center justify-center gap-1.5">
        <FamilyMenu
          current="study"
          label={t('footer.explore')}
          ariaLabel={t('footer.exploreProjects')}
          menuLabel={t('footer.neuronectionFamily')}
          familyLabel={t('footer.family')}
          countLabel={(count) => t('footer.appCount', { count })}
          closeLabel={t('common.close')}
          currentLabel={t('footer.current')}
          version={`v${packageJson.version}`}
          className={compact ? 'h-7 px-2 text-[11px]' : undefined}
        />
        <button
          type="button"
          onClick={() => setFundOpen(true)}
          className={compact ? fundPillCompactClass : fundPillClass}
        >
          <Heart />
          {t('footer.fund')}
        </button>
        <button
          type="button"
          onClick={() => void navigate({ to: '/about' })}
          className={compact ? aboutPillCompactClass : aboutPillClass}
        >
          {t('nav.about')}
        </button>
      </div>
      <UpdateBadge
        version={packageJson.version}
        label={t('footer.version', { version: packageJson.version })}
        className="text-[10px] font-medium"
      />

      <Modal open={fundOpen} onOpenChange={setFundOpen}>
        <ModalContent size="sm" aria-describedby={undefined}>
          <SponsorCard
            channels={SPONSOR_CHANNELS}
            title={t('sponsor.title')}
            columns={1}
            className="border-none bg-transparent shadow-none"
          />
        </ModalContent>
      </Modal>
    </div>
  )
}
