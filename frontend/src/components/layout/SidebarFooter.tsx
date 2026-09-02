import { useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import { ArrowUpRight, Heart } from 'lucide-react'
import {
  CareerMark,
  HealthMark,
  NeuronectionMark,
  NeuronectionWordmark,
  SponsorCard,
  StudyMark,
} from '@neuronection/assistant-ui'
import type { LogoProps } from '@neuronection/assistant-ui'
import packageJson from '../../../package.json'

import { Modal, ModalContent } from '@/components/ui/modal'
import { NEURONECTION_URL, SPONSOR_CHANNELS } from '@/config/funding'

const fundPillClass =
  'focus-visible:outline-ring inline-flex h-8 items-center gap-1.5 rounded-full border border-rose-500/20 bg-rose-500/10 px-4 text-[13px] font-medium text-rose-600 transition-colors hover:bg-rose-500/20 focus-visible:outline-2 focus-visible:outline-offset-2 [&_svg]:size-4 dark:text-rose-400'
const aboutPillClass =
  'focus-visible:outline-ring inline-flex h-8 items-center rounded-full px-4 text-[13px] font-medium text-muted-foreground transition-colors hover:bg-subtle hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2'

/** Family assistants listed in the footer; every row links to its site. */
const FAMILY_LINKS: {
  name: string
  Mark: React.ComponentType<LogoProps>
  href: string
  current?: boolean
}[] = [
  { name: 'Health', Mark: HealthMark, href: 'https://health-assistant.io' },
  { name: 'Career', Mark: CareerMark, href: 'https://neuronection.com/en/career/' },
  { name: 'Study', Mark: StudyMark, href: 'https://neuronection.com/en/study/', current: true },
]

/**
 * Sidebar footer project block: family branding, the three family
 * assistants, About and Fund actions plus the version. Presentational
 * glue on library primitives — copy comes from i18n, channels from
 * config (ADR-006 keeps this app-side).
 */
export function SidebarFooter() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [fundOpen, setFundOpen] = useState(false)

  return (
    <div className="flex flex-col items-center gap-2.5">
      <a
        href={NEURONECTION_URL}
        target="_blank"
        rel="noreferrer"
        className="focus-visible:outline-ring flex items-center gap-1.5 self-start text-xs text-muted-foreground transition-colors hover:text-primary focus-visible:outline-2 focus-visible:outline-offset-2"
      >
        <span>{t('footer.partOf')}</span>
        <NeuronectionMark size={16} />
        <NeuronectionWordmark height={14} />
      </a>
      <div className="bg-surface w-full rounded-md px-2 pb-1.5 pt-2">
        <p className="text-muted-foreground px-1.5 pb-1 text-[10px] font-bold uppercase tracking-wider">
          {t('footer.moreFromFamily')}
        </p>
        {FAMILY_LINKS.map(({ name, Mark, href, current }) => (
          <a
            key={href}
            href={href}
            target="_blank"
            rel="noreferrer"
            aria-label={`${name} ${t('footer.assistant')}`}
            className="focus-visible:outline-ring hover:bg-subtle group flex items-center gap-2 rounded-sm px-1.5 py-1 text-xs transition-colors focus-visible:outline-2 focus-visible:outline-offset-2"
          >
            <Mark size={16} />
            <span
              className={`w-12 text-left ${
                current ? 'text-foreground font-bold' : 'text-foreground font-medium'
              }`}
            >
              {name}
            </span>
            <span className="text-muted-foreground font-medium">{t('footer.assistant')}</span>
            <ArrowUpRight
              aria-hidden
              className="text-muted-foreground group-hover:text-primary ml-auto size-3.5 transition-colors"
            />
          </a>
        ))}
      </div>
      <div className="flex items-center gap-2">
        <button type="button" onClick={() => setFundOpen(true)} className={fundPillClass}>
          <Heart />
          {t('footer.fund')}
        </button>
        <button type="button" onClick={() => void navigate({ to: '/about' })} className={aboutPillClass}>
          {t('nav.about')}
        </button>
      </div>
      <p className="text-muted-foreground text-xs font-medium">
        {t('footer.version', { version: packageJson.version })}
      </p>

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
