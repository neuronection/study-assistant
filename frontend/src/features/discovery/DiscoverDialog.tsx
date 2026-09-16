import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import {
  BookmarkPlus,
  Download,
  ExternalLink,
  EyeOff,
  Eye,
  Link2,
  Loader2,
  Trash2,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Modal,
  ModalContent,
  ModalDescription,
  ModalHeader,
  ModalTitle,
} from '@neuronection/assistant-ui'
import {
  createLinkMaterial,
  deleteDiscoverySuggestion,
  getJob,
  listDiscoverySuggestions,
  parseLinkMaterial,
  patchDiscoverySuggestion,
  saveDiscoverySuggestion,
  searchDiscovery,
  type DiscoveryResultRow,
  type DiscoverySuggestion,
} from '@/lib/api'
import { getProfilePreferences } from '@/lib/api'
import { cn } from '@/lib/utils'

const POLL_INTERVAL_MS = 800
const POLL_DEADLINE_MS = 15 * 60_000

async function pollJob(jobId: number): Promise<void> {
  const deadline = Date.now() + POLL_DEADLINE_MS
  while (Date.now() < deadline) {
    const job = await getJob(jobId)
    if (job.status === 'done') return
    if (job.status === 'failed') throw new Error(job.error || 'parse failed')
    if (job.status === 'cancelled') throw new Error('parse cancelled')
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS))
  }
  throw new Error('parse failed')
}

function providerOptions(
  prefs: { enabled: string[]; sites: { site: string; label: string | null }[] } | undefined,
  t: (key: string) => string
): { id: string; label: string }[] {
  const enabled = prefs?.enabled ?? ['web', 'youtube']
  const options: { id: string; label: string }[] = []
  if (enabled.includes('web')) options.push({ id: 'web', label: t('discovery.providerWeb') })
  if (enabled.includes('youtube'))
    options.push({ id: 'youtube', label: t('discovery.providerYoutube') })
  for (const site of prefs?.sites ?? []) {
    const id = `site:${site.site}`
    if (enabled.includes(id)) {
      options.push({ id, label: site.label || site.site })
    }
  }
  return options
}

type DiscoverDialogProps = {
  open: boolean
  onClose: () => void
  courseId: number | null
  nodeId?: number | null
  defaultQuery?: string
}

export function DiscoverDialog({ open, onClose, courseId, nodeId, defaultQuery }: DiscoverDialogProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [query, setQuery] = useState('')
  const [submitted, setSubmitted] = useState('')
  const [selectedProviders, setSelectedProviders] = useState<string[] | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setQuery(defaultQuery ?? '')
      setSubmitted('')
      setNotice(null)
      setSelectedProviders(null)
    }
  }, [open, defaultQuery])

  const preferences = useQuery({
    queryKey: ['profile-preferences'],
    queryFn: getProfilePreferences,
    enabled: open,
  })
  const providers = providerOptions(preferences.data?.discovery, t)

  const suggestions = useQuery({
    queryKey: ['discovery', 'suggestions', courseId],
    queryFn: () => listDiscoverySuggestions({ course_id: courseId, limit: 100 }),
    enabled: open,
  })

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['discovery', 'suggestions'] })
    await queryClient.invalidateQueries({ queryKey: ['materials'] })
  }

  const search = useMutation({
    mutationFn: () =>
      searchDiscovery({
        query: submitted,
        providers: selectedProviders,
        cap: 10,
      }),
    onError: (error: Error) => setNotice(error.message),
  })

  const runSearch = () => {
    const trimmed = query.trim()
    if (!trimmed) return
    setSubmitted(trimmed)
    setNotice(null)
    search.mutate()
  }

  const track = async (row: DiscoveryResultRow): Promise<DiscoverySuggestion> => {
    if (row.suggestion) {
      const all = suggestions.data?.items ?? []
      const existing = all.find((entry) => entry.id === row.suggestion?.id)
      if (existing) return existing
    }
    const saved = await saveDiscoverySuggestion({
      provider: row.provider,
      url: row.url,
      title: row.title,
      snippet: row.description || null,
      kind: row.kind,
      meta: row.meta,
      course_id: courseId,
      node_id: nodeId ?? null,
    })
    await queryClient.invalidateQueries({ queryKey: ['discovery', 'suggestions'] })
    return saved.suggestion
  }

  const attach = useMutation({
    mutationFn: async (row: DiscoveryResultRow) => {
      if (courseId === null) throw new Error(t('workspace.openCourseFirst'))
      const suggestion = await track(row)
      const created = await createLinkMaterial({
        course_id: courseId,
        url: row.url,
        title: row.title,
        node_id: nodeId ?? undefined,
      })
      return patchDiscoverySuggestion(suggestion.id, {
        material_id: created.material.id,
      })
    },
    onSuccess: async () => {
      setNotice(null)
      await refresh()
    },
    onError: (error: Error) => setNotice(error.message),
  })

  const importParse = useMutation({
    mutationFn: async (row: DiscoveryResultRow) => {
      if (courseId === null) throw new Error(t('workspace.openCourseFirst'))
      const suggestion = await track(row)
      const created = await createLinkMaterial({
        course_id: courseId,
        url: row.url,
        title: row.title,
        node_id: nodeId ?? undefined,
      })
      const queued = await parseLinkMaterial(created.material.id)
      await pollJob(queued.job_id)
      return patchDiscoverySuggestion(suggestion.id, {
        material_id: created.material.id,
      })
    },
    onSuccess: async () => {
      setNotice(null)
      await refresh()
    },
    onError: (error: Error) => setNotice(error.message),
  })

  const saveForLater = useMutation({
    mutationFn: (row: DiscoveryResultRow) => track(row),
    onSuccess: async () => {
      setNotice(null)
      await queryClient.invalidateQueries({ queryKey: ['discovery', 'suggestions'] })
      search.mutate()
    },
    onError: (error: Error) => setNotice(error.message),
  })

  const dismissResult = useMutation({
    mutationFn: async (row: DiscoveryResultRow) => {
      const suggestion = await track(row)
      return patchDiscoverySuggestion(suggestion.id, { status: 'dismissed' })
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['discovery', 'suggestions'] })
      search.mutate()
    },
    onError: (error: Error) => setNotice(error.message),
  })

  const patchSaved = useMutation({
    mutationFn: ({ id, ...body }: { id: number; status?: string; material_id?: number }) =>
      patchDiscoverySuggestion(id, body),
    onSuccess: async () => {
      setNotice(null)
      await refresh()
      if (submitted) search.mutate()
    },
    onError: (error: Error) => setNotice(error.message),
  })

  const forget = useMutation({
    mutationFn: (id: number) => deleteDiscoverySuggestion(id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['discovery', 'suggestions'] })
      if (submitted) search.mutate()
    },
    onError: (error: Error) => setNotice(error.message),
  })

  const busy = (key: string) => busyId === key

  const markBusy = (key: string, action: () => Promise<unknown>): (() => void) => () => {
    if (busyId !== null) return
    setBusyId(key)
    action()
      .catch(() => undefined)
      .finally(() => setBusyId(null))
  }

  const resultActions = (row: DiscoveryResultRow) => {
    const state = row.suggestion?.status ?? null
    return (
      <div className="flex shrink-0 flex-wrap items-center gap-1">
        {state === 'saved' ? (
          <Badge variant="secondary">{t('discovery.statusSaved')}</Badge>
        ) : null}
        {state === 'dismissed' ? (
          <Badge variant="outline">{t('discovery.statusDismissed')}</Badge>
        ) : null}
        {row.suggestion?.material_id ? (
          <Button
            size="sm"
            variant="outline"
            onClick={() =>
              navigate({
                to: '/library/$materialId',
                params: { materialId: String(row.suggestion?.material_id) },
              })
            }
          >
            {t('discovery.openMaterial')}
          </Button>
        ) : courseId !== null ? (
          <Button
            size="sm"
            variant="ghost"
            disabled={busy(`attach-${row.url}`)}
            onClick={markBusy(`attach-${row.url}`, () => attach.mutateAsync(row))}
          >
            {busy(`attach-${row.url}`) ? <Loader2 className="animate-spin" aria-hidden /> : <Link2 aria-hidden />}
            {t('discovery.attach')}
          </Button>
        ) : null}
        {courseId !== null && !row.suggestion?.material_id ? (
          <Button
            size="sm"
            variant="ghost"
            disabled={busy(`import-${row.url}`)}
            onClick={markBusy(`import-${row.url}`, () => importParse.mutateAsync(row))}
            title={t('discovery.importHint')}
          >
            {busy(`import-${row.url}`) ? <Loader2 className="animate-spin" aria-hidden /> : <Download aria-hidden />}
            {t('discovery.importParse')}
          </Button>
        ) : null}
        {state === null ? (
          <>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => saveForLater.mutate(row)}
            >
              <BookmarkPlus aria-hidden />
              {t('discovery.saveLater')}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => dismissResult.mutate(row)}
            >
              <EyeOff aria-hidden />
              {t('discovery.dismiss')}
            </Button>
          </>
        ) : null}
        {state === 'dismissed' ? (
          <Button
            size="sm"
            variant="ghost"
            onClick={() =>
              row.suggestion &&
              patchSaved.mutate({ id: row.suggestion.id, status: 'suggested' })
            }
          >
            <Eye aria-hidden />
            {t('discovery.restore')}
          </Button>
        ) : null}
      </div>
    )
  }

  const savedRowActions = (row: DiscoverySuggestion) => (
    <div className="flex shrink-0 flex-wrap items-center gap-1">
      <Button
        size="sm"
        variant="ghost"
        onClick={() => window.open(row.url, '_blank', 'noopener')}
      >
        <ExternalLink aria-hidden />
        {t('discovery.open')}
      </Button>
      {row.material_id ? (
        <Button
          size="sm"
          variant="outline"
          onClick={() =>
            navigate({
              to: '/library/$materialId',
              params: { materialId: String(row.material_id) },
            })
          }
        >
          {t('discovery.openMaterial')}
        </Button>
      ) : courseId !== null ? (
        <Button
          size="sm"
          variant="ghost"
          disabled={busy(`saved-attach-${row.id}`)}
          onClick={markBusy(`saved-attach-${row.id}`, async () => {
            if (courseId === null) throw new Error(t('workspace.openCourseFirst'))
            const created = await createLinkMaterial({
              course_id: courseId,
              url: row.url,
              title: row.title,
              node_id: nodeId ?? undefined,
            })
            patchSaved.mutate({ id: row.id, material_id: created.material.id })
          })}
        >
          <Link2 aria-hidden />
          {t('discovery.attach')}
        </Button>
      ) : null}
      <Button
        size="sm"
        variant="ghost"
        onClick={() =>
          patchSaved.mutate({
            id: row.id,
            status: row.status === 'dismissed' ? 'suggested' : 'dismissed',
          })
        }
      >
        {row.status === 'dismissed' ? <Eye aria-hidden /> : <EyeOff aria-hidden />}
        {row.status === 'dismissed' ? t('discovery.restore') : t('discovery.dismiss')}
      </Button>
      <Button
        size="sm"
        variant="ghost"
        className="text-destructive"
        onClick={() => forget.mutate(row.id)}
        title={t('discovery.forget')}
      >
        <Trash2 aria-hidden />
      </Button>
    </div>
  )

  const statusLabel = (status: string) =>
    status === 'saved'
      ? t('discovery.statusSaved')
      : status === 'dismissed'
        ? t('discovery.statusDismissed')
        : t('discovery.statusSuggested')

  return (
    <Modal open={open} onOpenChange={(next) => !next && onClose()}>
      <ModalContent size="lg" closeLabel={t('common.close')} aria-describedby="discover-hint">
        <ModalHeader>
          <ModalTitle className="text-base">{t('discovery.title')}</ModalTitle>
          <ModalDescription id="discover-hint">
            {t('discovery.hint')}
          </ModalDescription>
        </ModalHeader>
        <div className="space-y-3 px-6 pb-6" data-testid="discover-dialog">
          <form
            className="flex gap-2"
            onSubmit={(event) => {
              event.preventDefault()
              runSearch()
            }}
          >
            <input
              className="bg-surface border-border focus:border-primary min-w-0 flex-1 rounded-md border px-3 py-2 text-sm outline-none"
              placeholder={t('discovery.queryPlaceholder')}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              aria-label={t('discovery.queryPlaceholder')}
            />
            <Button type="submit" size="sm" disabled={!query.trim() || search.isPending}>
              {search.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
              {t('discovery.search')}
            </Button>
          </form>
          {providers.length > 0 ? (
            <div className="flex flex-wrap gap-1" role="group" aria-label={t('discovery.providersLabel')}>
              {providers.map((provider) => {
                const active =
                  selectedProviders === null || selectedProviders.includes(provider.id)
                return (
                  <button
                    key={provider.id}
                    type="button"
                    aria-pressed={active}
                    className={cn(
                      'rounded-full border px-2.5 py-0.5 text-xs',
                      active
                        ? 'border-primary bg-primary/10 text-foreground'
                        : 'border-border text-muted-foreground hover:text-foreground',
                    )}
                    onClick={() => {
                      const current =
                        selectedProviders ?? providers.map((entry) => entry.id)
                      const next = current.includes(provider.id)
                        ? current.filter((entry) => entry !== provider.id)
                        : [...current, provider.id]
                      setSelectedProviders(next.length === 0 ? [] : next)
                    }}
                  >
                    {provider.label}
                  </button>
                )
              })}
            </div>
          ) : null}
          {notice !== null ? (
            <p className="text-destructive text-xs" role="alert">
              {notice}
            </p>
          ) : null}
          {search.isPending ? (
            <p className="text-muted-foreground text-xs" role="status">
              <Loader2 className="mr-1 inline animate-spin" aria-hidden />
              {t('discovery.searching')}
            </p>
          ) : null}
          {search.data && search.data.results.length === 0 && !search.isPending ? (
            <p className="text-muted-foreground text-xs">{t('discovery.noResults')}</p>
          ) : null}
          {search.data?.errors.length ? (
            <p className="text-warning text-xs">
              {search.data.errors
                .map((entry) => `${entry.provider}: ${entry.error}`)
                .join(' · ')}
            </p>
          ) : null}
          <div className="space-y-2" data-testid="discover-results">
            {(search.data?.results ?? []).map((row) => (
              <div
                key={`${row.provider}-${row.url}`}
                className="border-border flex items-start justify-between gap-3 rounded-md border p-2"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline">{row.provider}</Badge>
                    <span className="text-muted-foreground text-[11px]">{row.kind}</span>
                  </div>
                  <p className="mt-1 truncate text-sm" title={row.title}>
                    {row.title}
                  </p>
                  {row.description ? (
                    <p className="text-muted-foreground mt-0.5 line-clamp-2 text-xs">
                      {row.description}
                    </p>
                  ) : null}
                </div>
                {resultActions(row)}
              </div>
            ))}
          </div>
          <div className="space-y-1" data-testid="discover-saved">
            <h3 className="text-muted-foreground text-xs font-semibold uppercase tracking-wide">
              {t('discovery.savedSection')}
            </h3>
            {(suggestions.data?.items ?? []).length === 0 ? (
              <p className="text-muted-foreground text-xs">{t('discovery.savedEmpty')}</p>
            ) : null}
            {(suggestions.data?.items ?? []).map((row) => (
              <div
                key={row.id}
                className={cn(
                  'border-border flex items-center justify-between gap-3 rounded-md border px-2 py-1.5',
                  row.status === 'dismissed' && 'opacity-60',
                )}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline">{row.provider}</Badge>
                    <Badge variant="secondary">{statusLabel(row.status)}</Badge>
                  </div>
                  <p className="truncate text-sm" title={row.title}>
                    {row.title}
                  </p>
                </div>
                {savedRowActions(row)}
              </div>
            ))}
          </div>
        </div>
      </ModalContent>
    </Modal>
  )
}
