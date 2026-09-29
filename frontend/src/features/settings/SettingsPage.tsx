import { useNavigate, useSearch } from '@tanstack/react-router'
import {
  Database,
  Globe,
  Settings,
  SlidersHorizontal,
  Sparkles,
  Terminal,
  Users as UsersIcon,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { SegmentedTabs } from '@/components/ui/segmented-tabs'
import { SettingsShell } from '@/components/ui/settings-shell'
import { getCurrentUser } from '@/lib/auth-session'
import { DataTab } from './DataTab'
import { DeveloperTab } from './DeveloperTab'
import { GeneralTab } from './GeneralTab'
import { McpTab } from './McpTab'
import { ModelsTab } from './ModelsTab'
import { ProvidersTab } from './ProvidersTab'
import { SearchTab } from './SearchTab'
import { SkillsTab } from './SkillsTab'
import { TasksTab } from './TasksTab'
import { UsersTab } from './UsersTab'

const TABS = ['general', 'ai', 'search', 'data', 'users', 'developer'] as const
type Tab = (typeof TABS)[number]

const AI_SECTIONS = ['providers', 'models', 'tasks', 'skills', 'mcp'] as const
type AiSection = (typeof AI_SECTIONS)[number]

const TAB_ICONS = {
  general: SlidersHorizontal,
  ai: Sparkles,
  search: Globe,
  data: Database,
  users: UsersIcon,
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

  // The Users tab is admin-only (identity-auth §12): hidden — and
  // unreachable via `?tab=users` — for everyone else.
  const allowedTabs: Tab[] = getCurrentUser()?.is_admin
    ? [...TABS]
    : TABS.filter((key) => key !== 'users')
  const activeTab: Tab = allowedTabs.includes(tab) ? tab : 'general'

  const open = (next: Tab, nextSection?: AiSection) =>
    void navigate({
      to: '/settings',
      search: nextSection
        ? { tab: next, section: nextSection }
        : { tab: next },
    })

  const nav = allowedTabs.map((key) => ({
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
            <h2 className="text-lg font-semibold">{t(`settings.tabs.${activeTab}`)}</h2>
            <p className="text-muted-foreground text-sm">
              {t(`settings.nav.${activeTab}Desc`)}
            </p>
          </div>
          {activeTab === 'ai' ? (
            <SegmentedTabs
              ariaLabel={t('settings.aiSectionsAria')}
              items={sectionTabs}
              value={section}
              onValueChange={(next) => open('ai', next as AiSection)}
            />
          ) : null}
          {activeTab === 'general' ? <GeneralTab /> : null}
          {activeTab === 'ai' && section === 'providers' ? <ProvidersTab /> : null}
          {activeTab === 'ai' && section === 'models' ? <ModelsTab /> : null}
          {activeTab === 'ai' && section === 'tasks' ? <TasksTab /> : null}
          {activeTab === 'ai' && section === 'skills' ? <SkillsTab /> : null}
          {activeTab === 'ai' && section === 'mcp' ? <McpTab /> : null}
          {activeTab === 'search' ? <SearchTab /> : null}
          {activeTab === 'data' ? <DataTab /> : null}
          {activeTab === 'users' ? <UsersTab /> : null}
          {activeTab === 'developer' ? <DeveloperTab /> : null}
        </div>
      </SettingsShell>
    </div>
  )
}
