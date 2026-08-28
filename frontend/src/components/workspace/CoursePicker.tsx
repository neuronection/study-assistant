import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { listCourses, type Course } from '@/lib/api'
import { useWorkspaceStore } from '@/lib/workspace-store'

export interface RequiredCourseState {
  courseId: number | null
  courses: Course[]
  needsPicker: boolean
  blocked: boolean
}

export function useRequiredCourse(): RequiredCourseState {
  const workspaceCourseId = useWorkspaceStore((state) => state.courseId)
  const courses = useQuery({ queryKey: ['courses'], queryFn: listCourses })
  const list = courses.data ?? []
  if (workspaceCourseId !== null) {
    return { courseId: workspaceCourseId, courses: list, needsPicker: false, blocked: false }
  }
  if (list.length === 1 && list[0] !== undefined) {
    return { courseId: list[0].id, courses: list, needsPicker: false, blocked: false }
  }
  return { courseId: null, courses: list, needsPicker: list.length > 1, blocked: true }
}

export function CourseSelectField({
  value,
  onChange,
}: {
  value: number | null
  onChange: (courseId: number) => void
}) {
  const { t } = useTranslation()
  const courses = useQuery({ queryKey: ['courses'], queryFn: listCourses })
  const list = courses.data ?? []
  return (
    <label className="flex flex-col gap-1 text-xs">
      {t('workspace.courseLabel')}
      <select
        className="bg-surface border-border rounded-md border px-2 py-1.5 text-xs"
        value={value ?? ''}
        onChange={(event) => {
          const next = Number(event.target.value)
          if (next) {
            onChange(next)
          }
        }}
      >
        <option value="">{t('workspace.coursePick')}</option>
        {list.map((course) => (
          <option key={course.id} value={course.id}>
            {course.title}
          </option>
        ))}
      </select>
    </label>
  )
}
