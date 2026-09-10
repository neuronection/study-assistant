import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, Circle } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { getOnboardingState } from '@/lib/api'

import type { WizardCourse } from './CourseStep'

export function DoneStep({
  course,
  onFinish,
}: {
  course: WizardCourse | null
  onFinish: (target: 'home' | 'course') => void
}) {
  const { t } = useTranslation()
  const state = useQuery({
    queryKey: ['onboarding-state'],
    queryFn: getOnboardingState,
    refetchOnMount: 'always',
  })

  const rows: Array<{ label: string; done: boolean }> = [
    { label: t('onboarding.doneProvider'), done: state.data?.has_provider === true },
    { label: t('onboarding.doneModels'), done: state.data?.has_enabled_model === true },
    {
      label: t('onboarding.doneDefaults'),
      done: (state.data?.defaults_set.length ?? 0) > 0,
    },
    { label: t('onboarding.doneCourse'), done: state.data?.has_course === true },
    { label: t('onboarding.doneMaterials'), done: state.data?.has_material === true },
  ]

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground text-sm">{t('onboarding.doneHint')}</p>
      <ul className="border-border divide-border divide-y rounded-md border">
        {rows.map((row) => (
          <li key={row.label} className="flex items-center gap-2.5 px-3 py-2 text-sm">
            {row.done ? (
              <CheckCircle2 className="text-success size-4 shrink-0" aria-hidden />
            ) : (
              <Circle className="text-muted-foreground size-4 shrink-0" aria-hidden />
            )}
            <span className="min-w-0 flex-1">{row.label}</span>
            <span className={row.done ? 'text-success text-xs' : 'text-muted-foreground text-xs'}>
              {row.done ? t('onboarding.doneYes') : t('onboarding.doneNotYet')}
            </span>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap justify-end gap-2">
        {course !== null ? (
          <Button size="sm" onClick={() => onFinish('course')}>
            {t('onboarding.openCourse', { course: course.title })}
          </Button>
        ) : null}
        <Button variant="outline" size="sm" onClick={() => onFinish('home')}>
          {t('onboarding.goHome')}
        </Button>
      </div>
    </div>
  )
}
