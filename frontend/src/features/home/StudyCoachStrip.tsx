import { useQuery } from '@tanstack/react-query'
import {
  BookOpen,
  CalendarClock,
  GraduationCap,
  PlugZap,
  Sparkles,
  X,
} from 'lucide-react'
import type { ComponentType } from 'react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from '@tanstack/react-router'

import { Button } from '@/components/ui/button'
import {
  getExamStatus,
  getOverview,
  listCourses,
  listMaterials,
  listQuizzes,
  listTasks,
  recordActivation,
} from '@/lib/api'
import { storageKeys } from '@/lib/constants'

type CoachRule = {
  id: 'materials' | 'review' | 'exam' | 'practice' | 'provider'
  icon: ComponentType<{ className?: string; 'aria-hidden'?: boolean }>
  title: string
  body: string
  cta: string
  to: '/library' | '/review' | '/courses/$courseId' | '/settings'
  search?: Record<string, string>
  params?: Record<string, string>
}

function readDismissed(): string[] {
  try {
    const raw = window.localStorage.getItem(storageKeys.coachDismissed)
    const parsed: unknown = raw === null ? [] : JSON.parse(raw)
    return Array.isArray(parsed)
      ? parsed.filter((value): value is string => typeof value === 'string')
      : []
  } catch {
    return []
  }
}

export function StudyCoachStrip() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [dismissed, setDismissed] = useState(readDismissed)
  const overview = useQuery({ queryKey: ['overview'], queryFn: getOverview })
  const courses = useQuery({ queryKey: ['courses'], queryFn: listCourses })
  const materials = useQuery({ queryKey: ['materials', null], queryFn: () => listMaterials() })
  const exams = useQuery({ queryKey: ['exam-status'], queryFn: getExamStatus })
  const quizzes = useQuery({ queryKey: ['quizzes'], queryFn: () => listQuizzes() })
  const tasks = useQuery({ queryKey: ['tasks'], queryFn: listTasks })

  const courseId =
    courses.data?.[0]?.id !== undefined ? String(courses.data[0].id) : null
  const hasMaterials = (materials.data?.length ?? 0) > 0
  const dueCards = overview.data?.due_cards ?? 0
  const nearestExam = [...(exams.data ?? [])]
    .filter((entry) => entry.days_left >= 0)
    .sort((a, b) => a.days_left - b.days_left)[0]
  const hasPractice = (quizzes.data?.length ?? 0) > 0
  const hasProvider = (tasks.data ?? []).some(
    (task) => task.model_id !== null || task.model_label !== null
  )

  if (
    overview.isLoading ||
    materials.isLoading ||
    exams.isLoading ||
    quizzes.isLoading ||
    tasks.isLoading
  ) {
    return null
  }

  const rules: CoachRule[] = []
  if (!hasMaterials) {
    rules.push({
      id: 'materials',
      icon: BookOpen,
      title: t('home.coachMaterialsTitle'),
      body: t('home.coachMaterialsBody'),
      cta: t('home.coachMaterialsCta'),
      to: '/library',
    })
  }
  if (dueCards > 0) {
    rules.push({
      id: 'review',
      icon: GraduationCap,
      title: t('home.coachReviewTitle', { count: dueCards }),
      body: t('home.coachReviewBody'),
      cta: t('home.coachReviewCta'),
      to: '/review',
    })
  }
  if (nearestExam && nearestExam.days_left <= 14 && courseId !== null) {
    rules.push({
      id: 'exam',
      icon: CalendarClock,
      title: t('home.coachExamTitle', {
        course: nearestExam.course_title,
        days: nearestExam.days_left,
      }),
      body: t('home.coachExamBody'),
      cta: t('home.coachExamCta'),
      to: '/courses/$courseId',
      params: { courseId },
      search: { tab: 'practice' },
    })
  }
  if (hasMaterials && !hasPractice && courseId !== null) {
    rules.push({
      id: 'practice',
      icon: Sparkles,
      title: t('home.coachPracticeTitle'),
      body: t('home.coachPracticeBody'),
      cta: t('home.coachPracticeCta'),
      to: '/courses/$courseId',
      params: { courseId },
      search: { tab: 'practice' },
    })
  }
  if (!hasProvider) {
    rules.push({
      id: 'provider',
      icon: PlugZap,
      title: t('home.coachProviderTitle'),
      body: t('home.coachProviderBody'),
      cta: t('home.coachProviderCta'),
      to: '/settings',
      search: { tab: 'ai' },
    })
  }

  const visible = rules.filter((rule) => !dismissed.includes(rule.id)).slice(0, 2)
  if (visible.length === 0) {
    return null
  }

  const dismiss = (id: CoachRule['id']) => {
    const next = [...new Set([...dismissed, id])]
    setDismissed(next)
    try {
      window.localStorage.setItem(storageKeys.coachDismissed, JSON.stringify(next))
    } catch {
      return
    }
    void recordActivation('tip_dismissed', { surface: 'home_coach', step: id })
  }

  const open = (rule: CoachRule) => {
    void recordActivation('feature_opened', { surface: 'home_coach', step: rule.id })
    void navigate({
      to: rule.to,
      params: rule.params ?? {},
      search: rule.search ?? {},
    })
  }

  return (
    <section aria-labelledby="study-coach-title" className="space-y-2">
      <h2 id="study-coach-title" className="text-sm font-semibold">
        {t('home.coachTitle')}
      </h2>
      <div className="grid gap-2 sm:grid-cols-2">
        {visible.map((rule) => {
          const Icon = rule.icon
          return (
            <div
              key={rule.id}
              className="border-primary/25 bg-primary/5 flex min-w-0 flex-col gap-2 rounded-lg border px-3 py-2.5"
            >
              <div className="flex items-start gap-2">
                <Icon className="text-primary mt-0.5 size-4 shrink-0" aria-hidden />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{rule.title}</p>
                  <p className="text-muted-foreground text-xs">{rule.body}</p>
                </div>
                <Button
                  size="icon"
                  variant="ghost"
                  className="size-6 shrink-0"
                  aria-label={t('home.coachDismiss', { title: rule.title })}
                  onClick={() => dismiss(rule.id)}
                >
                  <X className="size-3.5" aria-hidden />
                </Button>
              </div>
              <Button
                size="sm"
                variant="outline"
                className="self-start"
                onClick={() => open(rule)}
              >
                {rule.cta}
              </Button>
            </div>
          )
        })}
      </div>
    </section>
  )
}
