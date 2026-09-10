import { useMutation } from '@tanstack/react-query'
import { Loader2, StickyNote } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorBanner } from '@/components/ErrorBanner'
import { composeNote, type GenerateScope } from '@/lib/api'
import { useCloseFloatings } from '@/lib/ui-overlays'

export function NoteComposeDialog({
  courseId,
  nodeId,
  rootNodeId,
  initialFocus,
  initialHint,
  onClose,
  onSuccess,
}: {
  courseId: number
  nodeId: number
  rootNodeId?: number
  initialFocus?: string
  initialHint?: string
  onClose: () => void
  onSuccess: (noteId: number) => void
}) {
  useCloseFloatings()
  const { t } = useTranslation()
  const atRoot = rootNodeId !== undefined && nodeId === rootNodeId
  const [scope, setScope] = useState<GenerateScope>(atRoot ? 'course' : 'subtree')
  const [title, setTitle] = useState('')
  const [focus, setFocus] = useState(initialFocus ?? '')
  const [hint, setHint] = useState(initialHint ?? '')
  const [error, setError] = useState<string | null>(null)

  const compose = useMutation({
    mutationFn: () =>
      composeNote({
        course_id: courseId,
        node_id: scope === 'course' ? (rootNodeId ?? nodeId) : nodeId,
        scope,
        title: title.trim() || null,
        instructions: focus.trim() || null,
        context_hint: hint.trim() || null,
      }),
    onSuccess: (note) => {
      setError(null)
      onSuccess(note.id)
    },
    onError: (err: Error) => setError(err.message),
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <Card className="max-h-[85vh] w-full max-w-lg overflow-y-auto">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <StickyNote className="size-4" aria-hidden />
            {t('launcher.note')}
          </CardTitle>
          <CardDescription>{t('launcher.noteHint')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {!atRoot ? (
            <label className="flex flex-col gap-1 text-xs">
              {t('workspace.scopeLabel')}
              <select
                className="bg-surface border-border rounded-md border px-2 py-1.5 text-xs"
                value={scope}
                onChange={(event) => setScope(event.target.value as GenerateScope)}
              >
                <option value="node">{t('generate.scopeNode')}</option>
                <option value="subtree">{t('generate.scopeSubtree')}</option>
                <option value="course">{t('workspace.scopeCourse')}</option>
              </select>
            </label>
          ) : null}
          <label className="flex flex-col gap-1 text-xs">
            {t('launcher.noteTitle')}
            <input
              className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder={t('generate.titlePlaceholder')}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            {t('launcher.noteFocus')}
            <textarea
              className="bg-surface border-border min-h-16 w-full rounded-md border px-2 py-1.5 text-xs"
              value={focus}
              onChange={(event) => setFocus(event.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            {t('generate.hintLabel')}
            <textarea
              className="bg-surface border-border min-h-12 w-full rounded-md border px-2 py-1.5 text-xs"
              placeholder={t('generate.hintPlaceholder')}
              value={hint}
              onChange={(event) => setHint(event.target.value)}
            />
          </label>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={onClose}>
              {t('settings.cancel')}
            </Button>
            <Button size="sm" disabled={compose.isPending} onClick={() => compose.mutate()}>
              {compose.isPending ? (
                <Loader2 className="animate-spin" aria-hidden />
              ) : (
                <StickyNote aria-hidden />
              )}
              {t('launcher.createNote')}
            </Button>
          </div>
          <ErrorBanner message={error} />
        </CardContent>
      </Card>
    </div>
  )
}
