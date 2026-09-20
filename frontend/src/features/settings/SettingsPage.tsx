import { useNavigate, useSearch } from '@tanstack/react-router'
import {
  Database,
  Globe,
  Settings,
  SlidersHorizontal,
  Sparkles,
  Terminal,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { SegmentedTabs } from '@/components/ui/segmented-tabs'
import { SettingsShell } from '@/components/ui/settings-shell'
import { DataTab } from './DataTab'
import { DeveloperTab } from './DeveloperTab'
import { GeneralTab } from './GeneralTab'
import { McpTab } from './McpTab'
import { ModelsTab } from './ModelsTab'
import { ProvidersTab } from './ProvidersTab'
import { SearchTab } from './SearchTab'
import { SkillsTab } from './SkillsTab'
import { TasksTab } from './TasksTab'

const TABS = ['general', 'ai', 'search', 'data', 'developer'] as const
type Tab = (typeof TABS)[number]

const AI_SECTIONS = ['providers', 'models', 'tasks', 'skills', 'mcp'] as const
type AiSection = (typeof AI_SECTIONS)[number]

const TAB_ICONS = {
  general: SlidersHorizontal,
  ai: Sparkles,
  search: Globe,
  data: Database,
  developer: Terminal,
} as const satisfies Record<Tab, typeof SlidersHorizontal>

export function SettingsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const search = useSearch({ strict: false }) as {
    tab?: string
    section?: string
  }
  const tab: Tab = (TABS as readonly string[]).includes(search.tab ?? '')
    ? (search.tab as Tab)
    : 'general'
  const section: AiSection = (AI_SECTIONS as readonly string[]).includes(
    search.section ?? '',
  )
    ? (search.section as AiSection)
    : 'providers'

  const open = (next: Tab, nextSection?: AiSection) =>
    void navigate({
      to: '/settings',
      search: nextSection
        ? { tab: next, section: nextSection }
        : { tab: next },
    })

  const nav = TABS.map((key) => ({
    id: key,
    icon: TAB_ICONS[key],
    label: t(`settings.tabs.${key}`),
    description: t(`settings.nav.${key}Desc`),
  }))

  const sectionTabs = AI_SECTIONS.map((key) => ({
    value: key,
    label: t(`settings.tabs.${key}`),
  }))

  return (
    <div className="mx-auto max-w-6xl p-8">
      <SettingsShell
        nav={nav}
        active={tab}
        onNavigate={(id) => open(id as Tab)}
        header={{ icon: Settings, title: t('settings.title') }}
        navClassName="lg:top-0 lg:max-h-[calc(100vh-3.5rem)] lg:overflow-y-auto"
      >
        <div className="space-y-4">
          <div>
            <h2 className="text-lg font-semibold">{t(`settings.tabs.${tab}`)}</h2>
            <p className="text-muted-foreground text-sm">
              {t(`settings.nav.${tab}Desc`)}
            </p>
          </div>
          {tab === 'ai' ? (
            <SegmentedTabs
              ariaLabel={t('settings.aiSectionsAria')}
              items={sectionTabs}
              value={section}
              onValueChange={(next) => open('ai', next as AiSection)}
            />
          ) : null}
          {tab === 'general' ? <GeneralTab /> : null}
          {tab === 'ai' && section === 'providers' ? <ProvidersTab /> : null}
          {tab === 'ai' && section === 'models' ? <ModelsTab /> : null}
          {tab === 'ai' && section === 'tasks' ? <TasksTab /> : null}
          {tab === 'ai' && section === 'skills' ? <SkillsTab /> : null}
          {tab === 'ai' && section === 'mcp' ? <McpTab /> : null}
          {tab === 'search' ? <SearchTab /> : null}
          {tab === 'data' ? <DataTab /> : null}
          {tab === 'developer' ? <DeveloperTab /> : null}
        </div>
      </SettingsShell>
    </div>
  )
}
