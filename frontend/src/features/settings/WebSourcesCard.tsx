import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArchiveRestore,
  CloudUpload,
  Link2,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
  Unlink,
} from 'lucide-react'
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
  connectExternalSource,
  createExternalSource,
  deleteExternalSource,
  disconnectExternalSource,
  listCourses,
  listExternalBackups,
  listExternalSources,
  listSourceProviders,
  restoreExternalBackup,
  scanExternalSource,
  setExternalSourceSecret,
  updateExternalSource,
  uploadExternalBackup,
  type ExternalSourceKind,
  type ExternalSourceRow,
  type SourceProvider,
} from '@/lib/api'
import { ExtensionDocsButton } from './ExtensionDocsButton'

const INTERVALS: { value: number; labelKey: string }[] = [
  { value: 900, labelKey: 'webSources.interval15m' },
  { value: 3600, labelKey: 'webSources.interval1h' },
  { value: 21600, labelKey: 'webSources.interval6h' },
  { value: 86400, labelKey: 'webSources.interval24h' },
]

type EditorState = {
  id: string | null
  provider: string
  kind: ExternalSourceKind
  url: string
  label: string
  courseId: string | null
  interval: number
  maxItems: string
  query: string
  site: string
  username: string
  folderId: string
  folderPath: string
  collection: string
  decks: string
  secret: string
}

const DEFAULT_PROVIDER = 'rss'

function emptyEditor(courseId: string | null): EditorState {
  return {
    id: null,
    provider: DEFAULT_PROVIDER,
    kind: 'rss',
    url: '',
    label: '',
    courseId,
    interval: 21600,
    maxItems: '',
    query: '',
    site: '',
    username: '',
    folderId: '',
    folderPath: '',
    collection: '',
    decks: '',
    secret: '',
  }
}

function editorFromRow(row: ExternalSourceRow): EditorState {
  const options = row.options ?? {}
  return {
    id: row.id,
    provider: row.provider,
    kind: row.kind as ExternalSourceKind,
    url: row.url,
    label: row.label ?? '',
    courseId: row.course_id,
    interval: row.scan_interval_sec ?? 21600,
    maxItems: typeof options.max_items === 'number' ? String(options.max_items) : '',
    query: typeof options.query === 'string' ? options.query : '',
    site: typeof options.site === 'string' ? options.site : '',
    username: typeof options.username === 'string' ? options.username : '',
    folderId: typeof options.folder_id === 'string' ? options.folder_id : '',
    folderPath: typeof options.folder_path === 'string' ? options.folder_path : '',
    collection: typeof options.collection === 'string' ? options.collection : '',
    decks: Array.isArray(options.decks) ? options.decks.join(', ') : '',
    secret: '',
  }
}

function buildOptions(draft: EditorState): Record<string, unknown> {
  const options: Record<string, unknown> = {}
  if (draft.maxItems.trim() !== '') options.max_items = Number(draft.maxItems)
  if (draft.provider === 'site-search') {
    options.query = draft.query.trim()
    if (draft.site.trim() !== '') options.site = draft.site.trim()
  }
  if (draft.username.trim() !== '') options.username = draft.username.trim()
  if (draft.folderId.trim() !== '') options.folder_id = draft.folderId.trim()
  if (draft.folderPath.trim() !== '') options.folder_path = draft.folderPath.trim()
  if (draft.collection.trim() !== '') options.collection = draft.collection.trim()
  if (draft.decks.trim() !== '') {
    options.decks = draft.decks
      .split(',')
      .map((deck) => deck.trim())
      .filter(Boolean)
  }
  return options
}

function providerFor(
  providers: SourceProvider[],
  providerId: string
): SourceProvider | undefined {
  return providers.find((row) => row.id === providerId)
}

function SourceEditorDialog({
  state,
  providers,
  disclosure,
  onClose,
}: {
  state: EditorState
  providers: SourceProvider[]
  disclosure: string
  onClose: () => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const courses = useQuery({ queryKey: ['courses'], queryFn: listCourses })
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState<EditorState>(state)
  const provider = providerFor(providers, draft.provider)

  const save = useMutation({
    mutationFn: async () => {
      if (draft.id !== null) {
        return updateExternalSource(draft.id, {
          label: draft.label.trim() === '' ? null : draft.label.trim(),
          scan_interval_sec: draft.interval,
          options: buildOptions(draft),
        })
      }
      if (draft.courseId === null) {
        throw new Error(t('workspace.openCourseFirst'))
      }
      const created = await createExternalSource({
        course_id: draft.courseId,
        provider: draft.provider,
        kind: draft.kind,
        url: draft.url.trim(),
        label: draft.label.trim() === '' ? null : draft.label.trim(),
        options: buildOptions(draft),
      })
      if (draft.secret.trim() !== '' && provider !== undefined && provider.secret_slots[0]) {
        await setExternalSourceSecret(
          created.id,
          provider.secret_slots[0].name,
          draft.secret.trim()
        )
      }
      return created
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['external-sources'] })
      onClose()
    },
    onError: (cause: Error) => setError(cause.message),
  })

  const valid =
    provider === undefined
      ? false
      : draft.provider === 'site-search'
        ? draft.query.trim() !== ''
        : provider.url_required
          ? draft.url.trim() !== ''
          : true

  return (
    <Modal open onOpenChange={(next) => !next && onClose()}>
      <ModalContent size="md" closeLabel={t('common.close')}>
        <ModalHeader>
          <ModalTitle className="text-base">
            {draft.id !== null ? t('webSources.editTitle') : t('webSources.addTitle')}
          </ModalTitle>
          <ModalDescription>{t('webSources.dialogHint')}</ModalDescription>
        </ModalHeader>
        <form
          className="max-h-[70vh] space-y-3 overflow-y-auto px-6 pb-6"
          onSubmit={(event) => {
            event.preventDefault()
            save.mutate()
          }}
        >
          {draft.id === null ? (
            <label className="block space-y-1">
              <span className="text-muted-foreground text-xs">
                {t('webSources.provider')}
              </span>
              <select
                className="bg-surface border-border w-full rounded-md border px-2 py-1.5 text-sm"
                value={draft.provider}
                onChange={(event) => {
                  const nextProvider = providerFor(providers, event.target.value)
                  setDraft({
                    ...draft,
                    provider: event.target.value,
                    kind: (nextProvider?.default_kind ?? 'rss') as ExternalSourceKind,
                  })
                }}
              >
                {providers.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.label}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {draft.provider === 'site-search' ? (
            <>
              <label className="block space-y-1">
                <span className="text-muted-foreground text-xs">{t('webSources.query')}</span>
                <input
                  className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
                  value={draft.query}
                  onChange={(event) => setDraft({ ...draft, query: event.target.value })}
                />
              </label>
              <label className="block space-y-1">
                <span className="text-muted-foreground text-xs">{t('webSources.site')}</span>
                <input
                  className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
                  placeholder="khanacademy.org"
                  value={draft.site}
                  onChange={(event) => setDraft({ ...draft, site: event.target.value })}
                />
              </label>
            </>
          ) : provider !== undefined && provider.url_required ? (
            <label className="block space-y-1">
              <span className="text-muted-foreground text-xs">{t('webSources.url')}</span>
              <input
                type="url"
                required
                className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
                placeholder={
                  draft.provider === 'rss'
                    ? 'https://example.com/feed.xml'
                    : draft.provider === 'youtube'
                      ? 'https://youtube.com/@channel'
                      : 'https://cloud.example/remote.php/dav/files/me/'
                }
                value={draft.url}
                onChange={(event) => setDraft({ ...draft, url: event.target.value })}
              />
            </label>
          ) : null}
          {draft.provider === 'webdav' ? (
            <label className="block space-y-1">
              <span className="text-muted-foreground text-xs">{t('webSources.username')}</span>
              <input
                className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
                value={draft.username}
                onChange={(event) => setDraft({ ...draft, username: event.target.value })}
              />
            </label>
          ) : null}
          {draft.provider === 'google-drive' ? (
            <label className="block space-y-1">
              <span className="text-muted-foreground text-xs">{t('webSources.folderId')}</span>
              <input
                className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
                value={draft.folderId}
                onChange={(event) => setDraft({ ...draft, folderId: event.target.value })}
              />
            </label>
          ) : null}
          {draft.provider === 'dropbox' || draft.provider === 'onedrive' ? (
            <label className="block space-y-1">
              <span className="text-muted-foreground text-xs">
                {t('webSources.folderPath')}
              </span>
              <input
                className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
                value={draft.folderPath}
                onChange={(event) => setDraft({ ...draft, folderPath: event.target.value })}
              />
            </label>
          ) : null}
          {draft.provider === 'zotero' ? (
            <label className="block space-y-1">
              <span className="text-muted-foreground text-xs">{t('webSources.collection')}</span>
              <input
                className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
                value={draft.collection}
                onChange={(event) => setDraft({ ...draft, collection: event.target.value })}
              />
            </label>
          ) : null}
          {draft.provider === 'anki' ? (
            <label className="block space-y-1">
              <span className="text-muted-foreground text-xs">{t('webSources.decks')}</span>
              <input
                className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
                value={draft.decks}
                onChange={(event) => setDraft({ ...draft, decks: event.target.value })}
              />
            </label>
          ) : null}
          {provider !== undefined && provider.secret_slots.length > 0 ? (
            <>
              <label className="block space-y-1">
                <span className="text-muted-foreground text-xs">
                  {provider.secret_slots[0].label}
                </span>
                <input
                  type="password"
                  autoComplete="off"
                  className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
                  value={draft.secret}
                  onChange={(event) => setDraft({ ...draft, secret: event.target.value })}
                />
              </label>
              <p className="text-muted-foreground text-[11px]">{disclosure}</p>
            </>
          ) : null}
          {provider?.auth_kind === 'oauth2' ? (
            <p className="text-muted-foreground text-[11px]">{t('webSources.oauthHint')}</p>
          ) : null}
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
                onChange={(event) => setDraft({ ...draft, courseId: event.target.value })}
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
              <span className="text-muted-foreground text-xs">{t('webSources.interval')}</span>
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
            <label className="block flex-1 space-y-1">
              <span className="text-muted-foreground text-xs">{t('webSources.maxItems')}</span>
              <input
                type="number"
                min={1}
                max={100}
                className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
                value={draft.maxItems}
                onChange={(event) => setDraft({ ...draft, maxItems: event.target.value })}
              />
            </label>
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

function RemoteBackupsDialog({
  source,
  onClose,
}: {
  source: ExternalSourceRow
  onClose: () => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const backups = useQuery({
    queryKey: ['external-backups', source.id],
    queryFn: () => listExternalBackups(source.id),
  })
  const [notice, setNotice] = useState<string | null>(null)
  const restore = useMutation({
    mutationFn: (name: string) => restoreExternalBackup(source.id, name),
    onSuccess: async (result) => {
      setNotice(t('webSources.restoreDone', { count: result.materials }))
      await queryClient.invalidateQueries()
    },
    onError: (cause: Error) => setNotice(cause.message),
  })
  return (
    <Modal open onOpenChange={(next) => !next && onClose()}>
      <ModalContent size="md" closeLabel={t('common.close')}>
        <ModalHeader>
          <ModalTitle className="text-base">{t('webSources.restoreTitle')}</ModalTitle>
          <ModalDescription>{t('webSources.restoreHint')}</ModalDescription>
        </ModalHeader>
        <div className="space-y-2 px-6 pb-6">
          {(backups.data?.backups ?? []).length === 0 ? (
            <p className="text-muted-foreground text-xs">{t('webSources.remoteBackupsEmpty')}</p>
          ) : null}
          {(backups.data?.backups ?? []).map((backup) => (
            <div
              key={backup.name}
              className="border-border flex items-center justify-between gap-2 rounded-md border px-2 py-1.5"
            >
              <div className="text-xs">
                <div>{backup.name}</div>
                <div className="text-muted-foreground">{backup.created_at}</div>
              </div>
              <Button
                size="sm"
                variant="outline"
                disabled={restore.isPending}
                onClick={() => restore.mutate(backup.name)}
              >
                <ArchiveRestore aria-hidden />
                {t('webSources.restore')}
              </Button>
            </div>
          ))}
          {notice !== null ? (
            <p className="text-muted-foreground text-xs" role="status">
              {notice}
            </p>
          ) : null}
        </div>
      </ModalContent>
    </Modal>
  )
}

function statusVariant(status: string): 'outline' | 'danger' | 'secondary' {
  if (status === 'failing') return 'danger'
  if (status === 'degraded') return 'outline'
  return 'secondary'
}

export function WebSourcesCard() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [editor, setEditor] = useState<EditorState | null>(null)
  const [backupSource, setBackupSource] = useState<ExternalSourceRow | null>(null)
  const [scanNotice, setScanNotice] = useState<string | null>(null)

  const providers = useQuery({
    queryKey: ['source-providers'],
    queryFn: listSourceProviders,
  })
  const sources = useQuery({
    queryKey: ['external-sources'],
    queryFn: () => listExternalSources(),
  })
  const courses = useQuery({ queryKey: ['courses'], queryFn: listCourses })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['external-sources'] })

  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      updateExternalSource(id, { enabled }),
    onSuccess: invalidate,
  })
  const remove = useMutation({
    mutationFn: (id: string) => deleteExternalSource(id),
    onSuccess: invalidate,
  })
  const scanNow = useMutation({
    mutationFn: (id: string) => scanExternalSource(id),
    onSuccess: async (stats) => {
      setScanNotice(t('webSources.scanDone', { count: stats.new ?? 0 }))
      await invalidate()
      await queryClient.invalidateQueries({ queryKey: ['discovery', 'suggestions'] })
    },
    onError: (cause: Error) => setScanNotice(cause.message),
  })
  const connect = useMutation({
    mutationFn: (id: string) => connectExternalSource(id),
    onSuccess: async () => {
      setScanNotice(t('webSources.connected'))
      await invalidate()
    },
    onError: (cause: Error) => setScanNotice(cause.message),
  })
  const disconnect = useMutation({
    mutationFn: (id: string) => disconnectExternalSource(id),
    onSuccess: invalidate,
  })
  const backup = useMutation({
    mutationFn: (id: string) => uploadExternalBackup(id),
    onSuccess: (result) => setScanNotice(t('webSources.backupDone', { name: result.name })),
    onError: (cause: Error) => setScanNotice(cause.message),
  })

  const courseTitle = (courseId: string) =>
    (courses.data ?? []).find((course) => course.id === courseId)?.title ?? ''
  const providerRow = (row: ExternalSourceRow) =>
    providerFor(providers.data?.providers ?? [], row.provider)

  return (
    <Card data-testid="web-sources-card">
      <CardHeader>
        <CardTitle className="text-sm flex items-center gap-2">
          {t('webSources.title')}
          <span className="ml-auto">
            <ExtensionDocsButton extensionId="external-sources" />
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <p className="text-muted-foreground text-xs">{t('webSources.hint')}</p>
        <div className="space-y-1" data-testid="web-sources-list">
          {(sources.data ?? []).length === 0 ? (
            <p className="text-muted-foreground text-xs">{t('webSources.empty')}</p>
          ) : null}
          {(sources.data ?? []).map((row) => {
            const provider = providerRow(row)
            const secrets = row.secrets_configured ?? {}
            const conditions = row.conditions ?? []
            const oauthConnected = secrets.oauth === true
            return (
              <div
                key={row.id}
                className="border-border flex items-center justify-between gap-2 rounded-md border px-2 py-1.5"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="truncate text-sm">{row.label || row.url || row.kind}</span>
                    <Badge variant="outline">{provider?.label ?? row.provider}</Badge>
                    {row.course_id !== null ? (
                      <span className="text-muted-foreground truncate text-[11px]">
                        {courseTitle(row.course_id)}
                      </span>
                    ) : null}
                    {!row.enabled ? (
                      <Badge variant="outline">{t('webSources.disabled')}</Badge>
                    ) : null}
                    {row.status !== 'ok' ? (
                      <Badge variant={statusVariant(row.status)}>
                        {t(`webSources.status_${row.status}`)}
                      </Badge>
                    ) : null}
                    {conditions.map((condition) => (
                      <Badge key={condition} variant="outline">
                        {t(`webSources.condition_${condition}`)}
                      </Badge>
                    ))}
                    {provider !== undefined && provider.secret_slots.length > 0
                      ? provider.secret_slots.map((slot) =>
                          secrets[slot.name] === true ? (
                            <Badge key={slot.name} variant="secondary">
                              {t('webSources.secretStored')}
                            </Badge>
                          ) : null
                        )
                      : null}
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
                  {row.auth_kind === 'oauth2' ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={connect.isPending || disconnect.isPending}
                      onClick={() =>
                        oauthConnected ? disconnect.mutate(row.id) : connect.mutate(row.id)
                      }
                      title={oauthConnected ? t('webSources.disconnect') : t('webSources.connect')}
                    >
                      {connect.isPending ? (
                        <Loader2 className="animate-spin" aria-hidden />
                      ) : oauthConnected ? (
                        <Unlink aria-hidden />
                      ) : (
                        <Link2 aria-hidden />
                      )}
                      {oauthConnected ? t('webSources.disconnect') : t('webSources.connect')}
                    </Button>
                  ) : null}
                  {provider?.supports_backup === true ? (
                    <>
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={backup.isPending}
                        onClick={() => backup.mutate(row.id)}
                        title={t('webSources.backupNow')}
                      >
                        {backup.isPending ? (
                          <Loader2 className="animate-spin" aria-hidden />
                        ) : (
                          <CloudUpload aria-hidden />
                        )}
                         {t('webSources.backupNow')}
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setBackupSource(row)}
                        title={t('webSources.restoreTitle')}
                      >
                        <ArchiveRestore aria-hidden />
                      </Button>
                    </>
                  ) : null}
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
            )
          })}
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
        <SourceEditorDialog
          state={editor}
          providers={providers.data?.providers ?? []}
          disclosure={providers.data?.secret_disclosure ?? ''}
          onClose={() => setEditor(null)}
        />
      ) : null}
      {backupSource !== null ? (
        <RemoteBackupsDialog
          source={backupSource}
          onClose={() => setBackupSource(null)}
        />
      ) : null}
    </Card>
  )
}
