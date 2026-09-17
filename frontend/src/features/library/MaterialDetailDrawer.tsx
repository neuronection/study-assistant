import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { FocusShell, useFocusContext } from '@/components/layout/FocusShell'
import { getMaterial } from '@/lib/api'
import { useStudySession } from '@/lib/use-study-session'

import { MaterialDetailBody, type DetailTab } from './MaterialDetailBody'

export function MaterialDetailDrawer({
  materialId,
  onClose,
  onTakeNotes,
  onExpand,
  docked = false,
}: {
  materialId: number
  onClose: () => void
  onTakeNotes?: () => void
  onExpand?: () => void
  docked?: boolean
}) {
  const { t } = useTranslation()
  const [tab, setTab] = useState<DetailTab>('extraction')
  const detail = useQuery({
    queryKey: ['material', materialId],
    queryFn: () => getMaterial(materialId),
  })
  const material = detail.data?.material
  const context = useFocusContext(material?.course_id, undefined)
  useStudySession({
    kind: 'read',
    entityRef: `material:${materialId}`,
    courseId: material?.course_id ?? null,
    nodeId: null,
    enabled: detail.isSuccess,
  })

  return (
    <FocusShell
      overlay={!docked}
      docked={docked}
      onExpand={onExpand}
      title={material?.title ?? t('library.loading')}
      context={context}
      onClose={onClose}
    >
      <div className="flex h-full min-h-0 flex-col gap-3">
        <MaterialDetailBody
          materialId={materialId}
          activeTab={tab}
          onTabChange={setTab}
          showTitle={false}
          onTakeNotes={onTakeNotes}
        />
      </div>
    </FocusShell>
  )
}
