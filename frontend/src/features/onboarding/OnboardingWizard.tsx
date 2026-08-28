import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { BookOpen, Bot, Check, FolderUp, PartyPopper, Sparkles, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { getOnboardingState } from '@/lib/api'
import { useOverlayStore } from '@/lib/ui-overlays'

import { CourseStep, type WizardCourse } from './steps/CourseStep'
import { DefaultsStep } from './steps/DefaultsStep'
import { DoneStep } from './steps/DoneStep'
import { FilesStep } from './steps/FilesStep'
import { ModelsStep } from './steps/ModelsStep'
import { ProviderStep } from './steps/ProviderStep'
import { useWizardStore } from './wizardStore'

const DONE_KEY = 'ca-onboarding-done'

const STEP_KEYS = [
  'welcome',
  'provider',
  'models',
  'defaults',
  'course',
  'files',
  'done',
] as const

const STEP_ICONS = [Sparkles, Bot, Check, Check, BookOpen, FolderUp, PartyPopper]

function readDismissed(): boolean {
  try {
    return window.localStorage.getItem(DONE_KEY) === '1'
  } catch {
    return false
  }
}

function markDismissed(): void {
  try {
    window.localStorage.setItem(DONE_KEY, '1')
  } catch {
    // persistence is best-effort; the in-memory dismissal still applies
  }
}

export function OnboardingWizard() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const open = useWizardStore((state) => state.open)
  const closeWizard = useWizardStore((state) => state.closeWizard)
  const closeFloatings = useOverlayStore((state) => state.closeFloatings)
  const [dismissed, setDismissed] = useState(readDismissed)
  const [step, setStep] = useState(0)
  const [course, setCourse] = useState<WizardCourse | null>(null)
  const state = useQuery({
    queryKey: ['onboarding-state'],
    queryFn: getOnboardingState,
    staleTime: Infinity,
    retry: false,
  })

  const fresh = state.data ? !state.data.has_provider && !state.data.has_course : false
  const visible = open || (fresh && !dismissed)

  useEffect(() => {
    if (visible) {
      closeFloatings()
    }
  }, [visible, closeFloatings])

  if (!visible) {
    return null
  }

  const lastStep = 6
  const finish = (target: 'home' | 'course') => {
    markDismissed()
    setDismissed(true)
    closeWizard()
    void queryClient.invalidateQueries({ queryKey: ['onboarding-state'] })
    if (target === 'course' && course !== null) {
      void navigate({ to: '/courses/$courseId', params: { courseId: String(course.id) } })
    }
  }
  const advance = () => setStep((current) => Math.min(current + 1, lastStep))
  const back = () => setStep((current) => Math.max(current - 1, 0))

  const StepIcon = STEP_ICONS[step]

  return (
    <div
      className="bg-surface/80 fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={t('onboarding.title')}
    >
      <div className="bg-surface border-border flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl border shadow-xl">
        <div className="border-border flex items-center gap-3 border-b px-5 py-4">
          <span className="bg-primary/10 text-primary flex size-9 shrink-0 items-center justify-center rounded-lg">
            <StepIcon className="size-5" aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold">{t('onboarding.title')}</p>
            <p className="text-muted-foreground truncate text-xs">
              {t(`onboarding.steps.${STEP_KEYS[step]}`)}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-1.5" aria-hidden>
            {Array.from({ length: lastStep + 1 }, (_, index) => (
              <span
                key={index}
                className={
                  index === step
                    ? 'bg-primary size-2 rounded-full'
                    : index < step
                      ? 'bg-primary/50 size-2 rounded-full'
                      : 'bg-border size-2 rounded-full'
                }
              />
            ))}
          </div>
          <Button
            variant="ghost"
            size="icon"
            title={t('onboarding.skipAll')}
            aria-label={t('onboarding.skipAll')}
            onClick={() => finish('home')}
          >
            <X className="size-4" aria-hidden />
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">
          <h2 className="mb-3 text-lg font-semibold">
            {t(`onboarding.${STEP_KEYS[step]}Title`)}
          </h2>
          {step === 0 ? (
            <div className="space-y-3">
              <p className="text-muted-foreground text-sm">{t('onboarding.welcomeBody')}</p>
              <ul className="space-y-2">
                {[
                  { icon: Bot, label: t('onboarding.welcomeAi') },
                  { icon: BookOpen, label: t('onboarding.welcomeCourse') },
                  { icon: FolderUp, label: t('onboarding.welcomeFiles') },
                ].map((item) => (
                  <li key={item.label} className="border-border flex items-center gap-3 rounded-md border px-3 py-2 text-sm">
                    <item.icon className="text-primary size-4 shrink-0" aria-hidden />
                    {item.label}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {step === 1 ? (
            <ProviderStep hasProvider={state.data?.has_provider === true} onDone={advance} />
          ) : null}
          {step === 2 ? <ModelsStep /> : null}
          {step === 3 ? <DefaultsStep /> : null}
          {step === 4 ? <CourseStep course={course} onCourse={setCourse} /> : null}
          {step === 5 ? <FilesStep course={course} /> : null}
          {step === 6 ? <DoneStep course={course} onFinish={finish} /> : null}
        </div>
        {step < lastStep ? (
          <div className="border-border flex items-center gap-2 border-t px-5 py-3">
            <Button variant="ghost" size="sm" disabled={step === 0} onClick={back}>
              {t('onboarding.back')}
            </Button>
            <div className="flex-1" />
            <Button variant="ghost" size="sm" onClick={() => finish('home')}>
              {t('onboarding.skip')}
            </Button>
            <Button size="sm" onClick={advance}>
              {step === 0 ? t('onboarding.getStarted') : t('onboarding.next')}
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  )
}
