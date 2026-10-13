import { useNavigate, useSearch } from '@tanstack/react-router'
import {
  Database,
  Settings,
  SlidersHorizontal,
  Sparkles,
  Terminal,
  Users as UsersIcon,
  Wrench,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { SegmentedTabs } from '@/components/ui/segmented-tabs'
import { SettingsShell } from '@/components/ui/settings-shell'
import { getCurrentUser } from '@/lib/auth-session'
import { ConnectorsSection } from './ConnectorsSection'
import { DataTab } from './DataTab'
import { DeveloperTab } from './DeveloperTab'
import { DiscoveryCard } from './DiscoveryCard'
import { GeneralTab } from './GeneralTab'
import { IndexingSection } from './IndexingSection'
import { ModelsTab } from './ModelsTab'
import { ProvidersTab } from './ProvidersTab'
import { WebSearchSection } from './WebSearchSection'
import { SkillsTab } from './SkillsTab'
import { TasksTab } from './TasksTab'
import { UsersTab } from './UsersTab'
import { WebSourcesCard } from './WebSourcesCard'

// Settings structure follows the family contract (contracts/settings-map.json,
// ADR-0033): the AI tab hosts exactly ai.* domains; web search, discovery,
// web sources, connectors, indexing and skills are tools.* and live in the
// tools tab. The arrays are exported for the settings-map conformance test.
export const SETTINGS_TABS = [
  'general',
  'ai',
  'tools',
  'data',
  'users',
  'developer',
] as const
type Tab = (typeof SETTINGS_TABS)[number]

export const AI_TAB_SECTIONS = ['providers', 'models', 'tasks'] as const
type AiSection = (typeof AI_TAB_SECTIONS)[number]

export const TOOLS_TAB_SECTIONS = [
  'web-search',
  'discovery',
  'web-sources',
  'connectors',
  'indexing',
  'skills',
] as const
type ToolsSection = (typeof TOOLS_TAB_SECTIONS)[number]

type Section = AiSection | ToolsSection

// Legacy deep links keep working (INV-6): the former top-level `search` tab
// (embeddings + OCR) folded into tools → indexing, and the AI tab's former
// skills / mcp sections moved to tools (plan 27 Phase 2).
const LEGACY_TAB_REDIRECTS: Record<string, { tab: Tab; section?: Section }> = {
  search: { tab: 'tools', section: 'indexing' },
}

const LEGACY_SECTION_REDIRECTS: Record<string, { tab: Tab; section: Section }> = {
  'ai:skills': { tab: 'tools', section: 'skills' },
  'ai:mcp': { tab: 'tools', section: 'connectors' },
}

const TAB_ICONS = {
  general: SlidersHorizontal,
  ai: Sparkles,
  tools: Wrench,
  data: Database,
  users: UsersIcon,
  developer: Terminal,
} as const satisfies Record<Tab, typeof SlidersHorizontal>

const SECTIONS_PER_TAB: Record<Tab, readonly string[]> = {
  general: [],
  ai: AI_TAB_SECTIONS,
  tools: TOOLS_TAB_SECTIONS,
  data: [],
  users: [],
  developer: [],
}

export function SettingsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const search = useSearch({ strict: false }) as {
    tab?: string
    section?: string
  }

  // Users tab is admin-only (identity-auth §12): hidden — and
  // unreachable via `?tab=users` — for everyone else.
  const allowedTabs: Tab[] = getCurrentUser()?.is_admin
    ? [...SETTINGS_TABS]
    : SETTINGS_TABS.filter((key) => key !== 'users')

  const redirect = LEGACY_TAB_REDIRECTS[search.tab ?? '']
  const sectionRedirect =
    !redirect && search.section ? LEGACY_SECTION_REDIRECTS[`${search.tab}:${search.section}`] : undefined
  const requestedTab: Tab = redirect || sectionRedirect
    ? (redirect ?? sectionRedirect!).tab
    : (SETTINGS_TABS as readonly string[]).includes(search.tab ?? '')
      ? (search.tab as Tab)
      : 'general'
  const activeTab: Tab = allowedTabs.includes(requestedTab) ? requestedTab : 'general'

  const sections = SECTIONS_PER_TAB[activeTab]
  const requestedSection = redirect?.section ?? sectionRedirect?.section ?? search.section ?? ''
  const activeSection: string = sections.includes(requestedSection)
    ? requestedSection
    : sections[0]

  const open = (next: Tab, nextSection?: Section) =>
    void navigate({
      to: '/settings',
      search: nextSection ? { tab: next, section: nextSection } : { tab: next },
    })

  const nav = allowedTabs.map((key) => ({
    id: key,
    icon: TAB_ICONS[key],
    label: t(`settings.tabs.${key}`),
    description: t(`settings.nav.${key}Desc`),
  }))

  const sectionTabs = sections.map((key) => ({
    value: key,
    label: t(`settings.tabs.${key}`),
  }))

  return (
    <div className="mx-auto max-w-6xl p-8">
      <SettingsShell
        nav={nav}
        active={activeTab}
        onNavigate={(id) => open(id as Tab)}
        header={{ icon: Settings, title: t('settings.title') }}
        navClassName="lg:top-0 lg:max-h-[calc(100vh-3.5rem)] lg:overflow-y-auto"
      >
        <div className="space-y-4">
          <div>
            <h2 className="text-lg font-semibold">{t(`settings.tabs.${activeTab}`)}</h2>
            <p className="text-muted-foreground text-sm">
              {t(`settings.nav.${activeTab}Desc`)}
            </p>
          </div>
          {sections.length > 0 ? (
            <SegmentedTabs
              ariaLabel={t(`settings.${activeTab}SectionsAria`)}
              items={sectionTabs}
              value={activeSection}
              onValueChange={(next) => open(activeTab, next as Section)}
            />
          ) : null}
          {activeTab === 'general' ? <GeneralTab /> : null}
          {activeTab === 'ai' && activeSection === 'providers' ? <ProvidersTab /> : null}
          {activeTab === 'ai' && activeSection === 'models' ? <ModelsTab /> : null}
          {activeTab === 'ai' && activeSection === 'tasks' ? <TasksTab /> : null}
          {activeTab === 'tools' && activeSection === 'web-search' ? (
            <WebSearchSection />
          ) : null}
          {activeTab === 'tools' && activeSection === 'discovery' ? <DiscoveryCard /> : null}
          {activeTab === 'tools' && activeSection === 'web-sources' ? <WebSourcesCard /> : null}
          {activeTab === 'tools' && activeSection === 'connectors' ? (
            <ConnectorsSection />
          ) : null}
          {activeTab === 'tools' && activeSection === 'indexing' ? <IndexingSection /> : null}
          {activeTab === 'tools' && activeSection === 'skills' ? <SkillsTab /> : null}
          {activeTab === 'data' ? <DataTab /> : null}
          {activeTab === 'users' ? <UsersTab /> : null}
          {activeTab === 'developer' ? <DeveloperTab /> : null}
        </div>
      </SettingsShell>
    </div>
  )
}
