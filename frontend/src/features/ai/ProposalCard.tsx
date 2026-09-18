import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { AnimatePresence, motion } from 'framer-motion'
import { useMotionPresets } from '@/lib/motion'
import { SuccessBurst } from '@/components/motion/SuccessBurst'
import {
  CalendarDays,
  CalendarPlus,
  Check,
  ChevronDown,
  Dumbbell,
  FilePen,
  FilePlus,
  FilePlus2,
  FileText,
  FolderInput,
  Layers,
  Link2,
  ListChecks,
  Loader2,
  Network,
  PenLine,
  Sparkles,
  StickyNote,
  Tag,
  Wand2,
  X,
} from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { MarkdownSurface } from '@/components/ui/chat-markdown'
import { MarkdownDiffView } from '@/components/ui/markdown-diff-view'
import { TextDiffView } from '@/components/ui/text-diff-view'
import {
  approveChatProposal,
  dismissChatProposal,
  type ChatProposal,
} from '@/lib/api'

import { useCurrentOrigin } from '@/lib/origin'
import { cn } from '@/lib/utils'

export type GenerateRequest = {
  task: 'quiz' | 'exercise' | 'flashcards'
  params: {
    topic?: string | null
    count?: number | null
    steps?: number | null
    difficulty?: number | null
    materialIds?: number[]
    noteIds?: number[]
    instructions?: string | null
    questionTypes?: string[]
    shuffle?: boolean
    flashcards?: {
      source: 'note' | 'material'
      noteId?: number | null
      materialId?: number | null
    }
  }
}

const ACTION_CONFIG: Record<
  string,
  { icon: typeof FilePlus; labelKey: string }
> = {
  create_note: { icon: FilePlus, labelKey: 'ai.proposals.createNote' },
  edit_note: { icon: PenLine, labelKey: 'ai.proposals.editNote' },
  append_note: { icon: FilePlus2, labelKey: 'ai.proposals.appendNote' },
  edit_material: { icon: FilePen, labelKey: 'ai.proposals.editMaterial' },
  append_material: { icon: FilePlus2, labelKey: 'ai.proposals.appendMaterial' },
  create_material: { icon: FilePlus, labelKey: 'ai.proposals.createMaterial' },
  create_concept: { icon: Network, labelKey: 'ai.proposals.createConcept' },
  assign_material: { icon: Link2, labelKey: 'ai.proposals.assignMaterial' },
  cover_concept: { icon: Network, labelKey: 'ai.proposals.coverConcept' },
  set_node_ai_hint: { icon: PenLine, labelKey: 'ai.proposals.setNodeAiHint' },
  generate_quiz: { icon: Wand2, labelKey: 'ai.proposals.generateQuiz' },
  generate_exercise: {
    icon: Dumbbell,
    labelKey: 'ai.proposals.generateExercise',
  },
  generate_flashcards: {
    icon: Layers,
    labelKey: 'ai.proposals.generateFlashcards',
  },
  move_to_node: { icon: FolderInput, labelKey: 'ai.proposals.moveToNode' },
  tag_note: { icon: Tag, labelKey: 'ai.proposals.tagNote' },
  set_exam_date: { icon: CalendarDays, labelKey: 'ai.proposals.setExamDate' },
  generate_plan: { icon: ListChecks, labelKey: 'ai.proposals.generatePlan' },
  add_plan_items: { icon: CalendarPlus, labelKey: 'ai.proposals.addPlanItems' },
}

const GENERATE_ACTIONS = new Set([
  'generate_quiz',
  'generate_exercise',
  'generate_flashcards',
])

function generateTask(action: string): GenerateRequest['task'] {
  if (action === 'generate_quiz') return 'quiz'
  if (action === 'generate_flashcards') return 'flashcards'
  return 'exercise'
}

const DIFF_ACTIONS = new Set([
  'edit_note',
  'append_note',
  'edit_material',
  'append_material',
])

function appendPreview(
  original: string,
  heading: string | undefined,
  markdown: string,
): string {
  const addition = heading ? `## ${heading}\n\n${markdown}` : markdown
  return original.trim()
    ? `${original.trimEnd()}\n\n${addition.trim()}`
    : addition
}

function proposalDiff(
  proposal: ChatProposal,
): { original: string; suggested: string } | null {
  if (!DIFF_ACTIONS.has(proposal.action)) return null
  const payload = (proposal.payload ?? {}) as Record<string, unknown>
  const original = payload.original_md
  if (typeof original !== 'string' || !original) return null
  if (proposal.action === 'edit_note') {
    const suggested = payload.new_body_md
    if (typeof suggested !== 'string') return null
    return { original, suggested }
  }
  if (proposal.action === 'edit_material') {
    const suggested = payload.new_markdown
    if (typeof suggested !== 'string') return null
    return { original, suggested }
  }
  const markdown = payload.markdown
  if (typeof markdown !== 'string') return null
  const heading =
    typeof payload.heading === 'string' ? payload.heading : undefined
  return { original, suggested: appendPreview(original, heading, markdown) }
}

interface ProposalTarget {
  kind: 'note' | 'material' | 'concept'
  name: string
  nodePath?: string[]
}

function proposalTarget(proposal: ChatProposal): ProposalTarget | null {
  const payload = (proposal.payload ?? {}) as Record<string, unknown>
  if (
    payload.target_kind !== 'note' &&
    payload.target_kind !== 'material' &&
    payload.target_kind !== 'concept'
  ) {
    return null
  }
  const name = payload.target_name
  if (typeof name !== 'string' || !name) return null
  const rawPath = payload.target_node_path
  const nodePath = Array.isArray(rawPath)
    ? rawPath.filter((part): part is string => typeof part === 'string')
    : undefined
  return {
    kind: payload.target_kind,
    name,
    nodePath: nodePath && nodePath.length > 0 ? nodePath : undefined,
  }
}

const TARGET_ICONS = {
  note: StickyNote,
  material: FileText,
  concept: Network,
} as const

interface AnchoredEdit {
  op: 'replace' | 'append' | 'prepend'
  find?: string
  text?: string
}

function anchoredEdits(proposal: ChatProposal): AnchoredEdit[] {
  const payload = (proposal.payload ?? {}) as Record<string, unknown>
  const raw = payload.text_edits
  if (!Array.isArray(raw)) return []
  const ops: AnchoredEdit[] = []
  for (const entry of raw) {
    if (typeof entry !== 'object' || entry === null) continue
    const record = entry as Record<string, unknown>
    if (
      record.op !== 'replace' &&
      record.op !== 'append' &&
      record.op !== 'prepend'
    ) {
      continue
    }
    ops.push({
      op: record.op,
      find: typeof record.find === 'string' ? record.find : undefined,
      text: typeof record.text === 'string' ? record.text : undefined,
    })
  }
  return ops
}

function truncate(value: string | undefined, cap = 60): string {
  const text = (value ?? '').trim()
  if (!text) return ''
  return text.length <= cap ? text : `${text.slice(0, cap - 1)}…`
}

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
  const presets = useMotionPresets()
  const queryClient = useQueryClient()
  const from = useCurrentOrigin()
  const [open, setOpen] = useState(false)
  const [resolved, setResolved] = useState<ChatProposal | null>(null)
  const [diffMode, setDiffMode] = useState<'formatted' | 'raw'>('formatted')
  const view = resolved ?? proposal
  const config = ACTION_CONFIG[view.action]
  const Icon = config?.icon ?? Sparkles
  const actionLabel = config ? t(config.labelKey) : view.action
  const subject = proposalSubject(view)
  const isGenerate = GENERATE_ACTIONS.has(view.action)
  const target = proposalTarget(view)
  const TargetIcon = target ? TARGET_ICONS[target.kind] : null

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
          | {
              topic?: string
              count?: number
              steps?: number
              difficulty?: number
              material_ids?: number[]
              note_ids?: number[]
              instructions?: string
              question_types?: string[]
              shuffle?: boolean
              material_id?: number
              note_id?: number
            }
          | undefined
        const flashcards =
          view.action === 'generate_flashcards' &&
          (dialog?.material_id != null || dialog?.note_id != null)
            ? {
                source: (dialog?.material_id != null
                  ? 'material'
                  : 'note') as 'material' | 'note',
                materialId: dialog?.material_id ?? null,
                noteId: dialog?.note_id ?? null,
              }
            : undefined
        onOpenGenerate({
          task: generateTask(view.action),
          params: {
            topic: dialog?.topic ?? null,
            count: dialog?.count ?? null,
            steps: dialog?.steps ?? null,
            difficulty: dialog?.difficulty ?? null,
            materialIds: dialog?.material_ids,
            noteIds: dialog?.note_ids,
            instructions: dialog?.instructions ?? null,
            questionTypes: dialog?.question_types,
            shuffle: dialog?.shuffle,
            flashcards,
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
  const materialId = proposal.result?.material_id
  const diff = proposalDiff(view)
  const edits = anchoredEdits(view)

  return (
    <div className="border-border bg-surface my-1 w-full max-w-[92%] rounded-xl border">
      <div className="flex items-center gap-2 px-3 py-2">
        <Icon className="text-primary size-4 shrink-0" aria-hidden />
        <p className="min-w-0 flex-1 truncate text-xs font-medium">
          {actionLabel}
          {subject ? <span className="text-muted-foreground"> · {subject}</span> : null}
        </p>
        {view.status === 'approved' || view.status === 'executed' ? (
          <SuccessBurst />
        ) : null}
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
      {target && TargetIcon ? (
        <div className="border-border text-muted-foreground flex items-center gap-1.5 border-t px-3 py-1.5 text-[11px]">
          <TargetIcon className="size-3 shrink-0" aria-hidden />
          <span className="shrink-0 font-semibold uppercase tracking-wide">
            {t(`ai.proposals.target_${target.kind}`)}
          </span>
          <span className="text-foreground min-w-0 truncate font-medium">
            {target.name}
          </span>
          {target.nodePath ? (
            <span
              className="min-w-0 truncate"
              title={target.nodePath.join(' › ')}
            >
              · {target.nodePath.join(' › ')}
            </span>
          ) : null}
        </div>
      ) : null}
      {edits.length > 0 ? (
        <div className="border-border text-muted-foreground space-y-0.5 border-t px-3 py-1.5 text-[11px]">
          <p className="text-foreground/70 font-semibold uppercase tracking-wide">
            {t('ai.proposals.editsTitle')}
          </p>
          {edits.map((edit, index) => (
            <p key={index} className="min-w-0 truncate">
              {edit.op === 'replace' ? (
                <>
                  {t('ai.proposals.editReplace', {
                    find: truncate(edit.find),
                    text: truncate(edit.text),
                  })}
                </>
              ) : edit.op === 'append' ? (
                t('ai.proposals.editAppend', { text: truncate(edit.text) })
              ) : (
                t('ai.proposals.editPrepend', { text: truncate(edit.text) })
              )}
            </p>
          ))}
        </div>
      ) : null}
      {diff ? (
        <div className="mx-3 mb-2 mt-2">
          <div className="mb-1 flex items-center justify-end gap-2">
            <div className="border-border bg-subtle inline-flex overflow-hidden rounded-md border text-[10px] font-medium">
              <button
                type="button"
                aria-pressed={diffMode === 'formatted'}
                onClick={() => setDiffMode('formatted')}
                className={cn(
                  'text-muted-foreground px-2 py-0.5',
                  diffMode === 'formatted' && 'bg-surface text-foreground',
                )}
              >
                {t('diff.formatted')}
              </button>
              <button
                type="button"
                aria-pressed={diffMode === 'raw'}
                onClick={() => setDiffMode('raw')}
                className={cn(
                  'text-muted-foreground px-2 py-0.5',
                  diffMode === 'raw' && 'bg-surface text-foreground',
                )}
              >
                {t('diff.raw')}
              </button>
            </div>
          </div>
          <div className="border-border bg-surface max-h-56 overflow-y-auto rounded-md border p-2">
            {diffMode === 'formatted' ? (
              <MarkdownDiffView
                original={diff.original}
                suggested={diff.suggested}
                className="w-full text-xs"
                labels={{
                  original: t('diff.original'),
                  suggested: t('diff.suggested'),
                  unchangedBlocks: (count) =>
                    t('diff.unchangedBlocks', { count }),
                  showLess: t('diff.showLess'),
                  prevChange: t('diff.prevChange'),
                  nextChange: t('diff.nextChange'),
                  changePosition: (index, total) =>
                    t('diff.changePosition', { index, total }),
                  noChanges: t('diff.noChanges'),
                }}
              />
            ) : (
              <TextDiffView
                original={diff.original}
                suggested={diff.suggested}
                className="w-full"
                labels={{
                  original: t('diff.original'),
                  suggested: t('diff.suggested'),
                  unchangedLines: (count) => t('diff.unchangedLines', { count }),
                  showLess: t('diff.showLess'),
                  prevChange: t('diff.prevChange'),
                  nextChange: t('diff.nextChange'),
                  changePosition: (index, total) =>
                    t('diff.changePosition', { index, total }),
                }}
              />
            )}
          </div>
        </div>
      ) : null}
      {view.action === 'create_material' &&
      typeof (view.payload as Record<string, unknown> | undefined)?.body_md ===
        'string' ? (
        <div className="border-border bg-surface mx-3 mb-2 max-h-48 overflow-y-auto rounded-md border p-2 text-xs">
          <MarkdownSurface
            value={
              (view.payload as Record<string, unknown>).body_md as string
            }
          />
        </div>
      ) : null}
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div {...presets.collapse} className="overflow-hidden">
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
                task: generateTask(view.action),
                params: {
                  topic: (view.payload?.topic as string | undefined) ?? null,
                  count: (view.payload?.count as number | undefined) ?? null,
                  steps: (view.payload?.steps as number | undefined) ?? null,
                  difficulty:
                    (view.payload?.difficulty as number | undefined) ?? null,
                  materialIds: view.payload?.material_ids as number[] | undefined,
                  noteIds: view.payload?.note_ids as number[] | undefined,
                  instructions:
                    (view.payload?.instructions as string | undefined) ?? null,
                  questionTypes: view.payload?.question_types as
                    | string[]
                    | undefined,
                  shuffle: view.payload?.shuffle as boolean | undefined,
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
      {view.status === 'executed' && materialId && !noteId ? (
        <div className="border-border border-t px-3 py-2">
          <Link
            to="/library/$materialId"
            params={{ materialId: String(materialId) }}
            search={{ from }}
            className="text-primary inline-flex items-center gap-1 text-xs font-medium hover:underline"
          >
            {t('ai.proposals.openMaterial')}
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
