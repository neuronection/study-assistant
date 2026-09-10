import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { FocusShell, useFocusContext } from '@/components/layout/FocusShell'
import { getMaterial } from '@/lib/api'

import { MaterialDetailBody, type DetailTab } from './MaterialDetailBody'

export function MaterialDetailDrawer({
  materialId,
  onClose,
  onTakeNotes,
}: {
  materialId: number
  onClose: () => void
  onTakeNotes?: () => void
}) {
  const { t } = useTranslation()
  const [tab, setTab] = useState<DetailTab>('extraction')
  const detail = useQuery({
    queryKey: ['material', materialId],
    queryFn: () => getMaterial(materialId),
  })
  const material = detail.data?.material
  const context = useFocusContext(material?.course_id, undefined)

  return (
    <FocusShell
      overlay
      title={material?.title ?? t('library.loading')}
      context={context}
      onClose={onClose}
    >
      <div className="flex h-full flex-col gap-3">
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
