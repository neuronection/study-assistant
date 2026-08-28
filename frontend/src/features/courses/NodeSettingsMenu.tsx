import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Loader2, Save, Settings2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { ErrorBanner } from '@/components/ui/error-banner'
import { Popover } from '@/components/ui/popover'
import { updateCourse, updateNode } from '@/lib/api'
import { cn } from '@/lib/utils'

export function NodeSettingsMenu({
  courseId,
  node,
  examDate,
}: {
  courseId: string
  node: { id: number; title: string; summary: string | null; ai_hint: string | null; is_root: boolean }
  examDate?: string | null
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [title, setTitle] = useState(node.title)
  const [description, setDescription] = useState(node.summary ?? '')
  const [hint, setHint] = useState(node.ai_hint ?? '')
  const [examDraft, setExamDraft] = useState(examDate ?? '')
  const [closeSignal, setCloseSignal] = useState(0)

  useEffect(() => {
    setTitle(node.title)
    setDescription(node.summary ?? '')
    setHint(node.ai_hint ?? '')
    setExamDraft(examDate ?? '')
  }, [node.id, node.title, node.summary, node.ai_hint, examDate])

  const examChanged = node.is_root && examDraft !== (examDate ?? '')
  const changed =
    title !== node.title ||
    description !== (node.summary ?? '') ||
    hint !== (node.ai_hint ?? '') ||
    examChanged

  const save = useMutation({
    mutationFn: async () => {
      if (node.is_root) {
        if (title !== node.title || description !== (node.summary ?? '') || examChanged) {
          await updateCourse(Number(courseId), {
            ...(title !== node.title ? { title } : {}),
            ...(description !== (node.summary ?? '') ? { description } : {}),
            ...(examChanged ? { exam_date: examDraft.trim() === '' ? null : examDraft } : {}),
          })
        }
        if (hint !== (node.ai_hint ?? '')) {
          await updateNode(node.id, { ai_hint: hint })
        }
        return
      }
      const body: { title?: string; summary?: string; ai_hint?: string } = {}
      if (title !== node.title) {
        body.title = title
      }
      if (description !== (node.summary ?? '')) {
        body.summary = description
      }
      if (hint !== (node.ai_hint ?? '')) {
        body.ai_hint = hint
      }
      await updateNode(node.id, body)
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['node-workspace', String(node.id)] })
      await queryClient.invalidateQueries({ queryKey: ['tree', courseId] })
      await queryClient.invalidateQueries({ queryKey: ['courses'] })
      setCloseSignal((current) => current + 1)
    },
  })

  return (
    <Popover
      label={t('generate.nodeSettingsLabel')}
      closeSignal={closeSignal}
      panelClassName="w-[22rem] space-y-3"
      trigger={
        <span className="relative flex">
          <Settings2 className="size-4" aria-hidden />
          {node.ai_hint ? (
            <span
              className={cn(
                'bg-primary border-surface absolute -top-0.5 -right-0.5 size-1.5 rounded-full border'
              )}
              aria-label={t('generate.nodeSettingsHintBadge')}
              role="img"
            />
          ) : null}
        </span>
      }
    >
      <p className="text-muted-foreground text-xs">
        {t('generate.hintCardDescription')}
      </p>
      <label className="block space-y-1">
        <span className="text-foreground text-xs font-medium">
          {t('generate.nodeSettingsTitleLabel')}
        </span>
        <input
          className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
        />
      </label>
      <label className="block space-y-1">
        <span className="text-foreground text-xs font-medium">
          {t('generate.nodeSettingsDescriptionLabel')}
        </span>
        <textarea
          className="bg-surface border-border min-h-16 w-full rounded-md border px-3 py-2 text-sm"
          placeholder={t('generate.nodeSettingsDescriptionPlaceholder')}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
      </label>
      <label className="block space-y-1">
        <span className="text-foreground text-xs font-medium">
          {t('generate.nodeSettingsHintLabel')}
        </span>
        <textarea
          className="bg-surface border-border min-h-16 w-full rounded-md border px-3 py-2 text-sm"
          placeholder={t('generate.hintPlaceholder')}
          value={hint}
          onChange={(event) => setHint(event.target.value)}
        />
      </label>
      {node.is_root ? (
        <label className="block space-y-1">
          <span className="text-foreground text-xs font-medium">
            {t('generate.examDateLabel')}
          </span>
          <input
            type="date"
            className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
            value={examDraft}
            onChange={(event) => setExamDraft(event.target.value)}
          />
        </label>
      ) : null}
      <ErrorBanner message={save.isError ? (save.error as Error).message : null} />
      <div className="flex justify-end">
        <Button size="sm" disabled={!changed || save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Save aria-hidden />}
          {t('generate.nodeSettingsSave')}
        </Button>
      </div>
    </Popover>
  )
}
