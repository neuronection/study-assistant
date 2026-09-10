import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Loader2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { createCourse, createSampleCourse, listCourses } from '@/lib/api'

export interface WizardCourse {
  id: number
  title: string
}

export function CourseStep({
  course,
  onCourse,
}: {
  course: WizardCourse | null
  onCourse: (course: WizardCourse) => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [title, setTitle] = useState('')
  const [subject, setSubject] = useState('')
  const [error, setError] = useState<string | null>(null)

  const adopt = async (courseId: number) => {
    await queryClient.invalidateQueries({ queryKey: ['courses'] })
    await queryClient.invalidateQueries({ queryKey: ['onboarding-state'] })
    const courses = await queryClient.fetchQuery({
      queryKey: ['courses'],
      queryFn: listCourses,
    })
    onCourse({
      id: courseId,
      title: courses.find((entry) => entry.id === courseId)?.title ?? '',
    })
  }

  const create = useMutation({
    mutationFn: () =>
      createCourse({ title: title.trim(), subject: subject.trim() || null }),
    onSuccess: (created) => void adopt(created.id),
    onError: (err: Error) => setError(err.message),
  })
  const sample = useMutation({
    mutationFn: () => createSampleCourse(),
    onSuccess: (result) => void adopt(result.course_id),
    onError: (err: Error) => setError(err.message),
  })

  if (course !== null) {
    return (
      <div className="space-y-3">
        <p className="border-success/30 bg-success/10 text-foreground flex items-center gap-2 rounded-md border px-3 py-2 text-sm">
          <CheckCircle2 className="text-success size-4 shrink-0" aria-hidden />
          {t('onboarding.courseCreated', { title: course.title })}
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <p className="text-muted-foreground text-sm">{t('onboarding.courseHint')}</p>
      <label className="block space-y-1 text-sm">
        <span className="text-muted-foreground">{t('onboarding.courseNameLabel')}</span>
        <input
          className="bg-surface border-border w-full rounded-md border px-3 py-2"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder={t('courses.titlePlaceholder')}
        />
      </label>
      <label className="block space-y-1 text-sm">
        <span className="text-muted-foreground">{t('onboarding.courseSubjectLabel')}</span>
        <input
          className="bg-surface border-border w-full rounded-md border px-3 py-2"
          value={subject}
          onChange={(event) => setSubject(event.target.value)}
          placeholder={t('courses.subjectPlaceholder')}
        />
      </label>
      {error ? <p className="text-danger text-xs">{error}</p> : null}
      <div className="flex flex-wrap items-center justify-end gap-2">
        <Button
          variant="ghost"
          size="sm"
          disabled={sample.isPending || create.isPending}
          onClick={() => sample.mutate()}
        >
          {sample.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
          {t('onboarding.loadSample')}
        </Button>
        <Button
          size="sm"
          disabled={title.trim().length === 0 || create.isPending || sample.isPending}
          onClick={() => create.mutate()}
        >
          {create.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
          {t('onboarding.createCourse')}
        </Button>
      </div>
    </div>
  )
}
