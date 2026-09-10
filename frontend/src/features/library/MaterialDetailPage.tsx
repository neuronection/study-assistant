import { useNavigate, useParams, useSearch } from '@tanstack/react-router'
import { ArrowLeft } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import {
  DETAIL_TABS,
  MaterialDetailBody,
  type DetailTab,
} from './MaterialDetailBody'
import { LibraryBreadcrumbs } from './LibraryBreadcrumbs'
import { getMaterial } from '@/lib/api'
import { useQuery } from '@tanstack/react-query'
import { listCourses } from '@/lib/api'
import { useOriginBack } from '@/lib/origin'

export function MaterialDetailPage() {
  const { t } = useTranslation()
  const { materialId } = useParams({ from: '/library/$materialId' })
  const { tab, from } = useSearch({ from: '/library/$materialId' })
  const navigate = useNavigate()
  const activeTab = DETAIL_TABS.includes(tab as DetailTab) ? (tab as DetailTab) : 'extraction'

  const detail = useQuery({
    queryKey: ['material', Number(materialId)],
    queryFn: () => getMaterial(Number(materialId)),
  })
  const courses = useQuery({ queryKey: ['courses'], queryFn: listCourses })
  const material = detail.data?.material
  const course = (courses.data ?? []).find((entry) => entry.id === material?.course_id)

  const goBack = useOriginBack(from, '/library')

  const crumbs = [
    { key: 'library', label: t('library.title'), onClick: goBack },
    ...(course
      ? [
          {
            key: 'course',
            label: course.title,
            onClick: () =>
              void navigate({ to: '/library', search: { course: course.id, folder: undefined } }),
          },
        ]
      : []),
    { key: 'material', label: material?.title ?? '' },
  ]

  return (
    <div className="mx-auto flex h-full max-w-5xl flex-col gap-3 p-6">
      <div className="flex items-center gap-3">
        <button
          type="button"
          className="text-muted-foreground hover:text-foreground"
          title={t('library.backToLibrary')}
          onClick={goBack}
        >
          <ArrowLeft className="size-5" aria-hidden />
        </button>
        <LibraryBreadcrumbs items={crumbs} />
      </div>

      <MaterialDetailBody
        materialId={Number(materialId)}
        activeTab={activeTab}
        onTabChange={(entry) =>
          void navigate({
            to: '/library/$materialId',
            params: { materialId },
            search: {
              tab: entry === 'extraction' ? undefined : entry,
              from: typeof from === 'string' ? from : undefined,
            },
          })
        }
        onTakeNotes={
          material?.course_id !== undefined && material?.course_id !== null
            ? () =>
                void navigate({
                  to: '/courses/$courseId',
                  params: { courseId: String(material.course_id) },
                  search: {
                    material: Number(materialId),
                    study: 'new' as const,
                  },
                })
            : undefined
        }
      />
    </div>
  )
}
