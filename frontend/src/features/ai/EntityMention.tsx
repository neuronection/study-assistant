import { Link } from '@tanstack/react-router'
import {
  Dumbbell,
  FileText,
  ListChecks,
  Network,
  StickyNote,
  TreeDeciduous,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { useCurrentOrigin } from '@/lib/origin'

import type { MentionRef } from '@/lib/api'
import { cn } from '@/lib/utils'

const KIND_CONFIG: Record<
  MentionRef['kind'],
  { icon: typeof FileText; labelKey: string; className: string }
> = {
  material: {
    icon: FileText,
    labelKey: 'ai.mentions.material',
    className: 'text-sky-600 dark:text-sky-400',
  },
  note: {
    icon: StickyNote,
    labelKey: 'ai.mentions.note',
    className: 'text-amber-600 dark:text-amber-400',
  },
  concept: {
    icon: Network,
    labelKey: 'ai.mentions.concept',
    className: 'text-violet-600 dark:text-violet-400',
  },
  node: {
    icon: TreeDeciduous,
    labelKey: 'ai.mentions.node',
    className: 'text-emerald-600 dark:text-emerald-400',
  },
  quiz: {
    icon: ListChecks,
    labelKey: 'ai.mentions.quiz',
    className: 'text-rose-600 dark:text-rose-400',
  },
  exercise: {
    icon: Dumbbell,
    labelKey: 'ai.mentions.exercise',
    className: 'text-teal-600 dark:text-teal-400',
  },
}

function MentionLinkWrap({
  mention,
  ariaLabel,
  children,
}: {
  mention: MentionRef
  ariaLabel: string
  children: ReactNode
}) {
  const id = String(mention.id)
  const from = useCurrentOrigin()
  const linkClass =
    'inline-flex cursor-pointer rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring'
  switch (mention.kind) {
    case 'material':
      return (
        <Link
          to="/library/$materialId"
          params={{ materialId: id }}
          className={linkClass}
          aria-label={ariaLabel}
        >
          {children}
        </Link>
      )
    case 'note':
      return (
        <Link
          to="/note/$noteId"
          params={{ noteId: id }}
          search={{ from }}
          className={linkClass}
          aria-label={ariaLabel}
        >
          {children}
        </Link>
      )
    case 'node':
      if (mention.course_id === null || mention.course_id === undefined) {
        return <>{children}</>
      }
      return (
        <Link
          to="/courses/$courseId/n/$nodeId"
          params={{ courseId: String(mention.course_id), nodeId: id }}
          className={linkClass}
          aria-label={ariaLabel}
        >
          {children}
        </Link>
      )
    case 'concept':
      if (mention.course_id === null || mention.course_id === undefined) {
        return <>{children}</>
      }
      return (
        <Link
          to="/courses/$courseId"
          params={{ courseId: String(mention.course_id) }}
          search={{ tab: 'concepts' }}
          className={linkClass}
          aria-label={ariaLabel}
        >
          {children}
        </Link>
      )
    case 'quiz':
      return (
        <Link
          to="/quiz/$activityId"
          params={{ activityId: id }}
          search={{ from }}
          className={linkClass}
          aria-label={ariaLabel}
        >
          {children}
        </Link>
      )
    case 'exercise':
      return (
        <Link
          to="/exercises/$exerciseId"
          params={{ exerciseId: id }}
          search={{ from }}
          className={linkClass}
          aria-label={ariaLabel}
        >
          {children}
        </Link>
      )
    default:
      return <>{children}</>
  }
}

export function EntityMention({
  mention,
  className,
}: {
  mention: MentionRef
  className?: string
}) {
  const { t } = useTranslation()
  const config = KIND_CONFIG[mention.kind]
  const Icon = config?.icon ?? FileText
  const label = config ? t(config.labelKey) : mention.kind
  const ariaLabel = t('ai.mentions.goTo', { kind: label, title: mention.title })
  return (
    <MentionLinkWrap mention={mention} ariaLabel={ariaLabel}>
      <span
        className={cn(
          'border-border bg-subtle inline-flex max-w-[16rem] items-center gap-1 rounded-full border px-2 py-0.5 align-baseline text-[11px] font-medium transition-colors',
          config?.className,
          'hover:border-current',
          className,
        )}
        title={ariaLabel}
      >
        <Icon className="size-3 shrink-0" aria-hidden />
        <span className="truncate">{mention.title}</span>
      </span>
    </MentionLinkWrap>
  )
}
