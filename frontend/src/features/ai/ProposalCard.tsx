import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { AnimatePresence, motion } from 'framer-motion'
import {
  Check,
  ChevronDown,
  Dumbbell,
  FilePlus,
  Link2,
  Loader2,
  Network,
  PenLine,
  Sparkles,
  Wand2,
  X,
} from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import {
  approveChatProposal,
  dismissChatProposal,
  type ChatProposal,
} from '@/lib/api'

import { useCurrentOrigin } from '@/lib/origin'
import { cn } from '@/lib/utils'

export type GenerateRequest = {
  task: 'quiz' | 'exercise'
  params: {
    topic?: string | null
    count?: number | null
    steps?: number | null
    difficulty?: number | null
  }
}

const ACTION_CONFIG: Record<
  string,
  { icon: typeof FilePlus; labelKey: string }
> = {
  create_note: { icon: FilePlus, labelKey: 'ai.proposals.createNote' },
  assign_material: { icon: Link2, labelKey: 'ai.proposals.assignMaterial' },
  cover_concept: { icon: Network, labelKey: 'ai.proposals.coverConcept' },
  set_node_ai_hint: { icon: PenLine, labelKey: 'ai.proposals.setNodeAiHint' },
  generate_quiz: { icon: Wand2, labelKey: 'ai.proposals.generateQuiz' },
  generate_exercise: {
    icon: Dumbbell,
    labelKey: 'ai.proposals.generateExercise',
  },
}

const GENERATE_ACTIONS = new Set(['generate_quiz', 'generate_exercise'])

function StatusBadge({ status }: { status: string }) {
  const { t } = useTranslation()
  const tone =
    status === 'executed'
      ? 'text-success border-success/40 bg-success/10'
      : status === 'approved'
        ? 'text-primary border-primary/40 bg-primary/10'
        : status === 'stale'
          ? 'text-warning border-warning/40 bg-warning/10'
          : 'text-muted-foreground border-border bg-subtle'
  return (
    <span
      className={cn(
        'rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide',
        tone,
      )}
    >
      {t(`ai.proposals.status_${status}`)}
    </span>
  )
}

function proposalSubject(proposal: ChatProposal): string {
  const payload = proposal.payload ?? {}
  for (const key of ['title', 'topic', 'hint']) {
    const value = payload[key]
    if (typeof value === 'string' && value.trim()) {
      return value
    }
  }
  return ''
}

export function ProposalCard({
  proposal,
  onOpenGenerate,
}: {
  proposal: ChatProposal
  onOpenGenerate?: (request: GenerateRequest) => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const from = useCurrentOrigin()
  const [open, setOpen] = useState(false)
  const [resolved, setResolved] = useState<ChatProposal | null>(null)
  const view = resolved ?? proposal
  const config = ACTION_CONFIG[view.action]
  const Icon = config?.icon ?? Sparkles
  const actionLabel = config ? t(config.labelKey) : view.action
  const subject = proposalSubject(view)
  const isGenerate = GENERATE_ACTIONS.has(view.action)

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ['chat-messages'] })

  const approve = useMutation({
    mutationFn: () => approveChatProposal(view.id),
    onSuccess: (updated) => {
      setResolved(updated)
      invalidate()
      if (
        updated.status === 'approved' &&
        isGenerate &&
        onOpenGenerate !== undefined
      ) {
        const dialog = updated.result?.open_dialog as
          | { topic?: string; count?: number; steps?: number; difficulty?: number }
          | undefined
        onOpenGenerate({
          task: view.action === 'generate_quiz' ? 'quiz' : 'exercise',
          params: {
            topic: dialog?.topic ?? null,
            count: dialog?.count ?? null,
            steps: dialog?.steps ?? null,
            difficulty: dialog?.difficulty ?? null,
          },
        })
      }
    },
  })
  const dismiss = useMutation({
    mutationFn: () => dismissChatProposal(view.id),
    onSuccess: (updated) => {
      setResolved(updated)
      invalidate()
    },
  })

  const pending = approve.isPending || dismiss.isPending
  const noteId = proposal.result?.note_id

  return (
    <div className="border-border bg-surface my-1 w-full max-w-[92%] rounded-xl border">
      <div className="flex items-center gap-2 px-3 py-2">
        <Icon className="text-primary size-4 shrink-0" aria-hidden />
        <p className="min-w-0 flex-1 truncate text-xs font-medium">
          {actionLabel}
          {subject ? <span className="text-muted-foreground"> · {subject}</span> : null}
        </p>
        <StatusBadge status={view.status} />
        <Button
          variant="ghost"
          size="icon"
          className="size-6"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          aria-label={t('ai.proposals.togglePreview')}
        >
          <ChevronDown
            className={cn('size-3.5 transition-transform', open && 'rotate-180')}
            aria-hidden
          />
        </Button>
      </div>
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden"
          >
            <pre className="bg-subtle mx-3 mb-2 max-h-48 overflow-auto rounded-md p-2 text-[11px] whitespace-pre-wrap">
              {JSON.stringify(view.payload, null, 2)}
            </pre>
          </motion.div>
        ) : null}
      </AnimatePresence>
      {view.status === 'proposed' ? (
        <div className="border-border flex items-center gap-2 border-t px-3 py-2">
          <Button size="sm" disabled={pending} onClick={() => approve.mutate()}>
            {approve.isPending ? (
              <Loader2 className="animate-spin" aria-hidden />
            ) : (
              <Check className="size-3.5" aria-hidden />
            )}
            {t('ai.proposals.approve')}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            disabled={pending}
            onClick={() => dismiss.mutate()}
          >
            {dismiss.isPending ? (
              <Loader2 className="animate-spin" aria-hidden />
            ) : (
              <X className="size-3.5" aria-hidden />
            )}
            {t('ai.proposals.dismiss')}
          </Button>
        </div>
      ) : null}
      {view.status === 'approved' && isGenerate ? (
        <div className="border-border border-t px-3 py-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              onOpenGenerate?.({
                task: view.action === 'generate_quiz' ? 'quiz' : 'exercise',
                params: {
                  topic: (view.payload?.topic as string | undefined) ?? null,
                  count: (view.payload?.count as number | undefined) ?? null,
                  steps: (view.payload?.steps as number | undefined) ?? null,
                  difficulty: (view.payload?.difficulty as number | undefined) ?? null,
                },
              })
            }
          >
            <Wand2 className="size-3.5" aria-hidden />
            {t('ai.proposals.openGenerator')}
          </Button>
        </div>
      ) : null}
      {view.status === 'executed' && noteId ? (
        <div className="border-border border-t px-3 py-2">
          <Link
            to="/note/$noteId"
            params={{ noteId: String(noteId) }}
            search={{ from }}
            className="text-primary inline-flex items-center gap-1 text-xs font-medium hover:underline"
          >
            {t('ai.proposals.openNote')}
          </Link>
        </div>
      ) : null}
      {view.status === 'stale' && view.result?.error ? (
        <div className="border-border text-muted-foreground border-t px-3 py-2 text-[11px] italic">
          {String(view.result.error)}
        </div>
      ) : null}
    </div>
  )
}
