import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Loader2, Pencil, Plus, RefreshCw, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Modal,
  ModalContent,
  ModalDescription,
  ModalHeader,
  ModalTitle,
} from '@neuronection/assistant-ui'
import {
  createExternalSource,
  deleteExternalSource,
  listCourses,
  listExternalSources,
  scanExternalSource,
  updateExternalSource,
  type ExternalSourceKind,
  type ExternalSourceRow,
} from '@/lib/api'

const KINDS: ExternalSourceKind[] = [
  'rss',
  'youtube_channel',
  'youtube_playlist',
  'site_search',
]

const INTERVALS: { value: number; labelKey: string }[] = [
  { value: 900, labelKey: 'webSources.interval15m' },
  { value: 3600, labelKey: 'webSources.interval1h' },
  { value: 21600, labelKey: 'webSources.interval6h' },
  { value: 86400, labelKey: 'webSources.interval24h' },
]

type EditorState = {
  id: number | null
  kind: ExternalSourceKind
  url: string
  label: string
  courseId: number | null
  interval: number
  maxItems: string
  query: string
  site: string
}

function emptyEditor(courseId: number | null): EditorState {
  return {
    id: null,
    kind: 'rss',
    url: '',
    label: '',
    courseId,
    interval: 21600,
    maxItems: '',
    query: '',
    site: '',
  }
}

function editorFromRow(row: ExternalSourceRow): EditorState {
  const options = row.options ?? {}
  return {
    id: row.id,
    kind: row.kind as ExternalSourceKind,
    url: row.url,
    label: row.label ?? '',
    courseId: row.course_id,
    interval: row.scan_interval_sec ?? 21600,
    maxItems: typeof options.max_items === 'number' ? String(options.max_items) : '',
    query: typeof options.query === 'string' ? options.query : '',
    site: typeof options.site === 'string' ? options.site : '',
  }
}

function SourceEditorDialog({
  state,
  onClose,
}: {
  state: EditorState
  onClose: () => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const courses = useQuery({ queryKey: ['courses'], queryFn: listCourses })
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState<EditorState>(state)

  const save = useMutation({
    mutationFn: () => {
      const options: Record<string, unknown> = {}
      if (draft.maxItems.trim() !== '') {
        options.max_items = Number(draft.maxItems)
      }
      if (draft.kind === 'site_search') {
        options.query = draft.query.trim()
        if (draft.site.trim() !== '') options.site = draft.site.trim()
      }
      if (draft.id !== null) {
        return updateExternalSource(draft.id, {
          label: draft.label.trim() === '' ? null : draft.label.trim(),
          scan_interval_sec: draft.interval,
          options,
        })
      }
      if (draft.courseId === null) {
        return Promise.reject(new Error(t('workspace.openCourseFirst')))
      }
      return createExternalSource({
        course_id: draft.courseId,
        kind: draft.kind,
        url: draft.url.trim(),
        label: draft.label.trim() === '' ? null : draft.label.trim(),
        options,
      })
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['external-sources'] })
      onClose()
    },
    onError: (cause: Error) => setError(cause.message),
  })

  const valid =
    draft.kind === 'site_search' ? draft.query.trim() !== '' : draft.url.trim() !== ''

  return (
    <Modal open onOpenChange={(next) => !next && onClose()}>
      <ModalContent size="md" closeLabel={t('common.close')}>
        <ModalHeader>
          <ModalTitle className="text-base">
            {draft.id !== null
              ? t('webSources.editTitle')
              : t('webSources.addTitle')}
          </ModalTitle>
          <ModalDescription>{t('webSources.dialogHint')}</ModalDescription>
        </ModalHeader>
        <form
          className="space-y-3 px-6 pb-6"
          onSubmit={(event) => {
            event.preventDefault()
            save.mutate()
          }}
        >
          {draft.id === null ? (
            <label className="block space-y-1">
              <span className="text-muted-foreground text-xs">{t('webSources.kind')}</span>
              <select
                className="bg-surface border-border w-full rounded-md border px-2 py-1.5 text-sm"
                value={draft.kind}
                onChange={(event) =>
                  setDraft({ ...draft, kind: event.target.value as ExternalSourceKind })
                }
              >
                {KINDS.map((kind) => (
                  <option key={kind} value={kind}>
                    {t(`webSources.kind_${kind}`)}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {draft.kind === 'site_search' ? (
            <>
              <label className="block space-y-1">
                <span className="text-muted-foreground text-xs">
                  {t('webSources.query')}
                </span>
                <input
                  className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
                  value={draft.query}
                  onChange={(event) =>
                    setDraft({ ...draft, query: event.target.value })
                  }
                />
              </label>
              <label className="block space-y-1">
                <span className="text-muted-foreground text-xs">
                  {t('webSources.site')}
                </span>
                <input
                  className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
                  placeholder="khanacademy.org"
                  value={draft.site}
                  onChange={(event) =>
                    setDraft({ ...draft, site: event.target.value })
                  }
                />
              </label>
            </>
          ) : (
            <label className="block space-y-1">
              <span className="text-muted-foreground text-xs">{t('webSources.url')}</span>
              <input
                type="url"
                required
                className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
                placeholder={
                  draft.kind === 'rss'
                    ? 'https://example.com/feed.xml'
                    : 'https://youtube.com/@channel'
                }
                value={draft.url}
                onChange={(event) => setDraft({ ...draft, url: event.target.value })}
              />
            </label>
          )}
          <label className="block space-y-1">
            <span className="text-muted-foreground text-xs">{t('webSources.label')}</span>
            <input
              className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
              value={draft.label}
              onChange={(event) => setDraft({ ...draft, label: event.target.value })}
            />
          </label>
          {draft.id === null ? (
            <label className="block space-y-1">
              <span className="text-muted-foreground text-xs">{t('webSources.course')}</span>
              <select
                className="bg-surface border-border w-full rounded-md border px-2 py-1.5 text-sm"
                value={draft.courseId ?? ''}
                onChange={(event) =>
                  setDraft({ ...draft, courseId: Number(event.target.value) })
                }
              >
                {(courses.data ?? []).map((course) => (
                  <option key={course.id} value={course.id}>
                    {course.title}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <div className="flex gap-3">
            <label className="block flex-1 space-y-1">
              <span className="text-muted-foreground text-xs">
                {t('webSources.interval')}
              </span>
              <select
                className="bg-surface border-border w-full rounded-md border px-2 py-1.5 text-sm"
                value={draft.interval}
                onChange={(event) =>
                  setDraft({ ...draft, interval: Number(event.target.value) })
                }
              >
                {INTERVALS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {t(option.labelKey)}
                  </option>
                ))}
              </select>
            </label>
            {draft.kind !== 'site_search' ? (
              <label className="block flex-1 space-y-1">
                <span className="text-muted-foreground text-xs">
                  {t('webSources.maxItems')}
                </span>
                <input
                  type="number"
                  min={1}
                  max={100}
                  className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
                  value={draft.maxItems}
                  onChange={(event) =>
                    setDraft({ ...draft, maxItems: event.target.value })
                  }
                />
              </label>
            ) : null}
          </div>
          {error !== null ? (
            <p className="text-destructive text-xs" role="alert">
              {error}
            </p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" size="sm" disabled={save.isPending || !valid}>
              {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
              {t('webSources.save')}
            </Button>
          </div>
        </form>
      </ModalContent>
    </Modal>
  )
}

export function WebSourcesCard() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [editor, setEditor] = useState<EditorState | null>(null)
  const [scanNotice, setScanNotice] = useState<string | null>(null)

  const sources = useQuery({
    queryKey: ['external-sources'],
    queryFn: () => listExternalSources(),
  })
  const courses = useQuery({ queryKey: ['courses'], queryFn: listCourses })

  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      updateExternalSource(id, { enabled }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['external-sources'] })
    },
  })

  const remove = useMutation({
    mutationFn: (id: number) => deleteExternalSource(id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['external-sources'] })
    },
  })

  const scanNow = useMutation({
    mutationFn: (id: number) => scanExternalSource(id),
    onSuccess: async (stats: { new: number; updated: number }) => {
      setScanNotice(t('webSources.scanDone', { count: stats.new }))
      await queryClient.invalidateQueries({ queryKey: ['external-sources'] })
      await queryClient.invalidateQueries({ queryKey: ['discovery', 'suggestions'] })
    },
    onError: (cause: Error) => setScanNotice(cause.message),
  })

  const courseTitle = (courseId: number) =>
    (courses.data ?? []).find((course) => course.id === courseId)?.title ?? ''

  return (
    <Card data-testid="web-sources-card">
      <CardHeader>
        <CardTitle className="text-sm">{t('webSources.title')}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <p className="text-muted-foreground text-xs">{t('webSources.hint')}</p>
        <div className="space-y-1" data-testid="web-sources-list">
          {(sources.data ?? []).length === 0 ? (
            <p className="text-muted-foreground text-xs">{t('webSources.empty')}</p>
          ) : null}
          {(sources.data ?? []).map((row) => (
            <div
              key={row.id}
              className="border-border flex items-center justify-between gap-2 rounded-md border px-2 py-1.5"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate text-sm">
                    {row.label || row.url}
                  </span>
                  <Badge variant="outline">{t(`webSources.kind_${row.kind}`)}</Badge>
                  {row.course_id !== null ? (
                    <span className="text-muted-foreground truncate text-[11px]">
                      {courseTitle(row.course_id)}
                    </span>
                  ) : null}
                  {!row.enabled ? (
                    <Badge variant="outline">{t('webSources.disabled')}</Badge>
                  ) : null}
                </div>
                {row.last_scan_error ? (
                  <p className="text-warning mt-0.5 flex items-center gap-1 text-[11px]">
                    <AlertTriangle className="size-3 shrink-0" aria-hidden />
                    {row.last_scan_error}
                  </p>
                ) : null}
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <label className="text-muted-foreground flex items-center gap-1 text-[11px]">
                  <input
                    type="checkbox"
                    checked={row.enabled}
                    aria-label={t('webSources.enabledLabel')}
                    onChange={(event) =>
                      toggle.mutate({ id: row.id, enabled: event.target.checked })
                    }
                  />
                  {t('webSources.enabledShort')}
                </label>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={scanNow.isPending}
                  onClick={() => scanNow.mutate(row.id)}
                  title={t('webSources.scanNow')}
                >
                  {scanNow.isPending ? (
                    <Loader2 className="animate-spin" aria-hidden />
                  ) : (
                    <RefreshCw aria-hidden />
                  )}
                  {t('webSources.scanNow')}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setEditor(editorFromRow(row))}
                  title={t('webSources.edit')}
                >
                  <Pencil aria-hidden />
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-destructive"
                  onClick={() => remove.mutate(row.id)}
                  title={t('webSources.delete')}
                >
                  <Trash2 aria-hidden />
                </Button>
              </div>
            </div>
          ))}
        </div>
        {scanNotice !== null ? (
          <p className="text-muted-foreground text-xs" role="status">
            {scanNotice}
          </p>
        ) : null}
        <Button size="sm" variant="outline" onClick={() => setEditor(emptyEditor(null))}>
          <Plus aria-hidden />
          {t('webSources.add')}
        </Button>
      </CardContent>
      {editor !== null ? (
        <SourceEditorDialog state={editor} onClose={() => setEditor(null)} />
      ) : null}
    </Card>
  )
}
