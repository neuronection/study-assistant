import { useNavigate } from '@tanstack/react-router'
import { Keyboard } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { CommandList, type CommandGroup } from '@/components/ui/command-list'
import {
  Modal,
  ModalBody,
  ModalContent,
  ModalDescription,
  ModalFooter,
  ModalHeader,
  ModalTitle,
} from '@/components/ui/modal'
import { ShortcutList, type ShortcutGroup } from '@/components/ui/shortcut-list'
import { useCaptureStore } from '@/lib/capture-store'
import { useImportUrlStore } from '@/lib/import-url-store'
import { useCloseFloatings } from '@/lib/ui-overlays'
import { SHORTCUT_GROUPS } from '@/lib/shortcuts'
import { useWorkspaceStore } from '@/lib/workspace-store'

type FeatureTarget =
  | { to: '/library' }
  | { to: '/courses' }
  | { to: '/solve' }
  | { to: '/review' }
  | { to: '/study/session' }
  | { to: '/scores' }
  | { to: '/studio' }
  | { to: '/jobs' }
  | { to: '/settings'; search: { tab: string; section?: string } }
  | { to: '/courses/$courseId'; params: { courseId: string }; search?: { tab: string } }

type Feature = {
  id: string
  group: 'capture' | 'read' | 'practise' | 'review' | 'organise' | 'configure'
  target?: FeatureTarget
  action?: 'capture' | 'import'
}

const FEATURE_GROUPS = [
  'capture',
  'read',
  'practise',
  'review',
  'organise',
  'configure',
] as const

export function ShortcutsDialog({ onClose }: { onClose: () => void }) {
  useCloseFloatings()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const courseId = useWorkspaceStore((state) => state.courseId)
  const openCapture = useCaptureStore((state) => state.openCapture)
  const openImport = useImportUrlStore((state) => state.openImport)
  const [query, setQuery] = useState('')
  const [restoreTarget] = useState<HTMLElement | null>(() => {
    const active = document.activeElement
    return active instanceof HTMLElement && active !== document.body ? active : null
  })

  useEffect(
    () => () => {
      restoreTarget?.focus({ preventScroll: true })
    },
    [restoreTarget],
  )

  const shortcutGroups = useMemo<ShortcutGroup[]>(
    () =>
      SHORTCUT_GROUPS.map((group) => ({
        id: group.id,
        label: t(`shortcuts.group.${group.id}`),
        entries: group.entries.map((entry) => ({
          id: entry.id,
          label: t(`shortcuts.${entry.id}`),
          keys: entry.keys,
        })),
      })),
    [t],
  )

  const features = useMemo<Feature[]>(() => {
    const course = courseId === null ? null : String(courseId)
    const practice: FeatureTarget | undefined =
      course === null
        ? undefined
        : { to: '/courses/$courseId', params: { courseId: course }, search: { tab: 'practice' } }
    const planner: FeatureTarget | undefined =
      course === null
        ? undefined
        : { to: '/courses/$courseId', params: { courseId: course }, search: { tab: 'planner' } }
    return [
      { id: 'quickCapture', group: 'capture', action: 'capture' },
      { id: 'importUrl', group: 'capture', action: 'import' },
      speechFeature(),
      { id: 'library', group: 'read', target: { to: '/library' } },
      { id: 'splitView', group: 'read', target: { to: '/library' } },
      { id: 'transcript', group: 'read', target: { to: '/library' } },
      { id: 'lectureRecording', group: 'capture', target: { to: '/courses' } },
      { id: 'practice', group: 'practise', target: practice },
      { id: 'papers', group: 'practise', target: practice },
      { id: 'solve', group: 'practise', target: { to: '/solve' } },
      { id: 'printKey', group: 'practise', target: { to: '/scores' } },
      { id: 'review', group: 'review', target: { to: '/review' } },
      { id: 'studyNow', group: 'review', target: { to: '/study/session' } },
      { id: 'studio', group: 'organise', target: { to: '/studio' } },
      { id: 'planner', group: 'review', target: planner },
      { id: 'jobs', group: 'organise', target: { to: '/jobs' } },
      { id: 'zotero', group: 'configure', target: { to: '/settings', search: { tab: 'tools', section: 'connectors' } } },
      { id: 'aiSettings', group: 'configure', target: { to: '/settings', search: { tab: 'ai' } } },
      { id: 'dataSettings', group: 'configure', target: { to: '/settings', search: { tab: 'data' } } },
    ].filter((feature): feature is Feature => feature.target !== undefined || feature.action !== undefined)
  }, [courseId])

  const featureGroups = useMemo<CommandGroup[]>(
    () =>
      FEATURE_GROUPS.map((group) => ({
        id: group,
        label: t(`shortcuts.featureGroup.${group}`),
        items: features
          .filter((feature) => feature.group === group)
          .map((feature) => ({
            id: feature.id,
            label: t(`shortcuts.feature.${feature.id}`),
          })),
      })).filter((group) => group.items.length > 0),
    [features, t],
  )

  const featuresById = useMemo(
    () => new Map(features.map((feature) => [feature.id, feature])),
    [features],
  )

  const activate = (feature: Feature) => {
    if (feature.action === 'capture') {
      onClose()
      openCapture()
      return
    }
    if (feature.action === 'import') {
      onClose()
      openImport()
      return
    }
    if (feature.target === undefined) return
    onClose()
    void navigate(feature.target)
  }

  return (
    <Modal open onOpenChange={(open) => {
      if (!open) {
        onClose()
      }
    }}>
      <ModalContent
        size="xl"
        className="sm:max-w-2xl"
        closeLabel={t('common.close')}
      >
        <ModalHeader>
          <ModalTitle className="flex items-center gap-2 text-base">
            <Keyboard className="size-4" aria-hidden />
            {t('shortcuts.title')}
          </ModalTitle>
          <ModalDescription className="text-xs">{t('shortcuts.hint')}</ModalDescription>
        </ModalHeader>
        <ModalBody className="space-y-5">
          <ShortcutList
            groups={shortcutGroups}
            className="grid gap-x-8 gap-y-5 sm:grid-cols-2"
          />

          <section aria-labelledby="feature-map-title" className="border-border border-t pt-4">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <h2 id="feature-map-title" className="text-sm font-semibold">
                {t('shortcuts.featureMapTitle')}
              </h2>
              <span className="text-muted-foreground text-[11px]">{t('shortcuts.featureMapHint')}</span>
            </div>
            <CommandList
              query={query}
              onQueryChange={setQuery}
              groups={featureGroups}
              onSelect={(item) => {
                const feature = featuresById.get(item.id)
                if (feature !== undefined) {
                  activate(feature)
                }
              }}
              labels={{
                placeholder: t('shortcuts.searchFeatures'),
                empty: t('shortcuts.noFeatures'),
                results: t('shortcuts.resultCount'),
                listLabel: t('shortcuts.searchLabel'),
              }}
              tabBehavior="focus"
              className="border-border bg-surface rounded-md border"
            />
          </section>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" size="sm" onClick={onClose}>
            {t('common.close')}
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  )
}

function speechFeature(): Feature {
  return { id: 'readAloud', group: 'read', target: { to: '/library' } }
}
