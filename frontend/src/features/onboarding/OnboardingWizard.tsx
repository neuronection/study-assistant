import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import {
  BookOpen,
  Bot,
  Check,
  FolderCog,
  FolderUp,
  PartyPopper,
  Sparkles,
  type LucideIcon,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Wizard, type WizardStep } from '@neuronection/assistant-ui'
import { getOnboardingState } from '@/lib/api'
import { useOverlayStore } from '@/lib/ui-overlays'

import { CourseStep, type WizardCourse } from './steps/CourseStep'
import { DefaultsStep } from './steps/DefaultsStep'
import { DoneStep } from './steps/DoneStep'
import { FilesStep } from './steps/FilesStep'
import { ModelsStep } from './steps/ModelsStep'
import { ProviderStep } from './steps/ProviderStep'
import { WorkingDirStep } from './steps/WorkingDirStep'
import { useWizardStore } from './wizardStore'
import { storageKeys } from '@/lib/constants'

const DONE_KEY = storageKeys.onboardingDone

const STEP_KEYS = [
  'welcome',
  'workingDir',
  'provider',
  'models',
  'defaults',
  'course',
  'files',
  'done',
] as const

const STEP_ICONS: LucideIcon[] = [
  Sparkles,
  FolderCog,
  Bot,
  Check,
  Check,
  BookOpen,
  FolderUp,
  PartyPopper,
]

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

  const finish = (target: 'home' | 'course') => {
    markDismissed()
    setDismissed(true)
    closeWizard()
    void queryClient.invalidateQueries({ queryKey: ['onboarding-state'] })
    if (target === 'course' && course !== null) {
      void navigate({ to: '/courses/$courseId', params: { courseId: String(course.id) } })
    }
  }

  if (!visible) {
    return null
  }

  const steps: WizardStep[] = STEP_KEYS.map((key, index) => ({
    id: key,
    icon: STEP_ICONS[index],
    subtitle: t(`onboarding.steps.${key}`),
    title: t(`onboarding.${key}Title`),
  }))

  return (
    <Wizard
      open={visible}
      onOpenChange={(next) => {
        if (!next) {
          finish('home')
        }
      }}
      title={t('onboarding.title')}
      steps={steps}
      backLabel={t('onboarding.back')}
      skipLabel={t('onboarding.skip')}
      nextLabel={t('onboarding.next')}
      getStartedLabel={t('onboarding.getStarted')}
      closeLabel={t('onboarding.skipAll')}
      renderStep={(ctx) => {
        if (ctx.id === 'welcome') {
          return (
            <div className="space-y-3">
              <p className="text-muted-foreground text-sm">{t('onboarding.welcomeBody')}</p>
              <ul className="space-y-2">
                {[
                  { icon: FolderCog, label: t('onboarding.welcomeDir') },
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
          )
        }
        if (ctx.id === 'workingDir') {
          return <WorkingDirStep />
        }
        if (ctx.id === 'provider') {
          return (
            <ProviderStep hasProvider={state.data?.has_provider === true} onDone={ctx.next} />
          )
        }
        if (ctx.id === 'models') {
          return <ModelsStep />
        }
        if (ctx.id === 'defaults') {
          return <DefaultsStep />
        }
        if (ctx.id === 'course') {
          return <CourseStep course={course} onCourse={setCourse} />
        }
        if (ctx.id === 'files') {
          return <FilesStep course={course} />
        }
        return <DoneStep course={course} onFinish={finish} />
      }}
    />
  )
}
