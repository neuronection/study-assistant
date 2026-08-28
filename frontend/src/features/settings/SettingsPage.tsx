import { useNavigate, useSearch } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'
import { DataTab } from './DataTab'
import { DeveloperTab } from './DeveloperTab'
import { McpTab } from './McpTab'
import { ModelsTab } from './ModelsTab'
import { ProvidersTab } from './ProvidersTab'
import { SearchTab } from './SearchTab'
import { SkillsTab } from './SkillsTab'
import { TasksTab } from './TasksTab'

const TABS = ['providers', 'models', 'tasks', 'skills', 'data', 'developer', 'search', 'mcp'] as const
type Tab = (typeof TABS)[number]

export function SettingsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const search = useSearch({ strict: false }) as { tab?: string }
  const raw = search.tab
  const tab: Tab = (TABS as readonly string[]).includes(raw ?? '')
    ? (raw as Tab)
    : 'providers'

  const tabs: { key: Tab; label: string }[] = [
    { key: 'providers', label: t('settings.tabs.providers') },
    { key: 'models', label: t('settings.tabs.models') },
    { key: 'tasks', label: t('settings.tabs.tasks') },
    { key: 'skills', label: t('settings.tabs.skills') },
    { key: 'data', label: t('settings.tabs.data') },
    { key: 'developer', label: t('settings.tabs.developer') },
    { key: 'search', label: t('settings.tabs.search') },
    { key: 'mcp', label: t('settings.tabs.mcp') },
  ]

  return (
    <div className="mx-auto max-w-3xl p-8">
      <h1 className="mb-4 text-2xl font-semibold">{t('settings.title')}</h1>
      <div className="mb-6 flex gap-1">
        {tabs.map((item) => (
          <button
            key={item.key}
            type="button"
            aria-current={tab === item.key ? 'page' : undefined}
            onClick={() => void navigate({ to: '/settings', search: { tab: item.key } })}
            className={cn(
              'rounded-md px-3 py-1.5 text-sm transition-colors',
              tab === item.key
                ? 'bg-subtle font-medium'
                : 'text-muted-foreground hover:text-foreground'
            )}
          >
            {item.label}
          </button>
        ))}
      </div>
      {tab === 'providers' ? <ProvidersTab /> : null}
      {tab === 'models' ? <ModelsTab /> : null}
      {tab === 'tasks' ? <TasksTab /> : null}
      {tab === 'skills' ? <SkillsTab /> : null}
      {tab === 'data' ? <DataTab /> : null}
      {tab === 'developer' ? <DeveloperTab /> : null}
      {tab === 'search' ? <SearchTab /> : null}
      {tab === 'mcp' ? <McpTab /> : null}
    </div>
  )
}
