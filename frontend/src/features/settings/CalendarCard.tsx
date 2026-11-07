import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CalendarDays,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  Unplug,
} from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorBanner } from '@/components/ErrorBanner'
import {
  completeCalendarOAuth,
  createCalendarLink,
  deleteCalendarLink,
  discoverCalendars,
  listCalendarLinks,
  listCalendarProviders,
  setCalendarLinkSecret,
  startCalendarOAuth,
  syncCalendarLink,
  testCalendarLink,
  updateCalendarLink,
  type CalendarLink,
  type CalendarProvider,
  type CalendarSetupField,
  type DiscoveredCalendar,
} from '@/lib/api'
import { listCourses } from '@/lib/api/courses'

// Cloud calendars (ADR-0052 / plan 52, §12 Rev 4). Providers, scope strings,
// destinations and the bind form's fields render verbatim from the backend
// catalog — this card carries no provider list and no `if provider === "x"`
// branch, so adding a catalog provider needs no UI change. Credentials are
// written once through the secret endpoint or the OAuth pair; they never
// round-trip.
const inputClass =
  'bg-subtle border-border w-full rounded-md border px-2 py-1.5 text-xs'

function statusTone(status: string): string {
  if (status === 'ok') return 'text-emerald-600'
  if (status === 'needs-auth' || status === 'needs-secret') return 'text-amber-600'
  if (status === 'failing') return 'text-destructive'
  return 'text-muted-foreground'
}

function needsAttention(link: CalendarLink): boolean {
  return link.status !== 'ok' || link.last_error !== null
}

const AUTH_KIND_LABEL_KEYS: Record<string, string> = {
  oauth2: 'authKindOAuth',
  'app-password': 'authKindAppPassword',
  token: 'authKindToken',
  none: 'authKindNone',
}

function fieldVisible(field: CalendarSetupField, authKind: string): boolean {
  return field.auth_kind === null || field.auth_kind === authKind
}

interface PickerProps {
  provider: CalendarProvider
  authKind: string
  values: Record<string, string>
  linkId?: string
  onPicked: (calendar: DiscoveredCalendar) => void
}

// The calendar picker (plan 52 §9 M1): discovery through the backend, one
// bounded list of the account's calendars. Bind-form credentials ride this
// one request and are never stored; connected links discover via link_id.
function CalendarPicker({ provider, authKind, values, linkId, onPicked }: PickerProps) {
  const { t } = useTranslation()
  const [calendars, setCalendars] = useState<DiscoveredCalendar[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = async () => {
    setBusy(true)
    setError(null)
    try {
      const result = await discoverCalendars(
        linkId
          ? { link_id: linkId }
          : {
              provider: provider.id,
              auth_kind: authKind,
              base_url: values.base_url?.trim() || null,
              calendar_url: values.calendar_url?.trim() || null,
              username: values.username?.trim() || null,
              secret: values.secret?.trim() || null,
            },
      )
      setCalendars(result.calendars)
    } catch (cause) {
      setError((cause as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => void run()}
          disabled={busy}
        >
          {busy ? (
            <Loader2 className="size-3.5 animate-spin" aria-hidden />
          ) : (
            <Search className="size-3.5" aria-hidden />
          )}
          {t('settings.calendar.findCalendars')}
        </Button>
        {calendars && calendars.length === 0 ? (
          <span className="text-muted-foreground text-xs">
            {t('settings.calendar.noCalendars')}
          </span>
        ) : null}
        {calendars && calendars.length > 0 ? (
          <select
            className={`${inputClass} max-w-xs`}
            defaultValue=""
            onChange={(event) => {
              const picked = calendars.find((row) => row.id === event.target.value)
              if (picked) onPicked(picked)
            }}
          >
            <option value="">{t('settings.calendar.pickCalendar')}</option>
            {calendars.map((row) => (
              <option key={row.id} value={row.id}>
                {row.name}
              </option>
            ))}
          </select>
        ) : null}
      </div>
      <ErrorBanner message={error} />
    </div>
  )
}

interface SetupFieldProps {
  field: CalendarSetupField
  values: Record<string, string>
  onChange: (key: string, value: string) => void
}

function SetupFieldInput({ field, values, onChange }: SetupFieldProps) {
  const { t } = useTranslation()
  return (
    <label className="block space-y-1 text-xs">
      <span className="text-muted-foreground">
        {t(`settings.calendar.${field.label_key}`)}
      </span>
      <input
        className={inputClass}
        type={field.kind === 'secret' ? 'password' : 'text'}
        value={values[field.key] ?? ''}
        required={field.required}
        placeholder={field.placeholder ?? undefined}
        autoComplete={field.autocomplete ?? undefined}
        onChange={(event) => onChange(field.key, event.target.value)}
      />
    </label>
  )
}

interface AddFormProps {
  providers: CalendarProvider[]
  onDone: () => void
}

function AddCalendarForm({ providers, onDone }: AddFormProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const courses = useQuery({ queryKey: ['courses'], queryFn: listCourses })
  const [providerId, setProviderId] = useState(providers[0]?.id ?? '')
  const provider = providers.find((row) => row.id === providerId)
  const [authKind, setAuthKind] = useState(provider?.auth_kinds[0] ?? '')
  const [courseId, setCourseId] = useState('')
  const [label, setLabel] = useState('')
  const [direction, setDirection] = useState('push')
  const [values, setValues] = useState<Record<string, string>>({})
  const [picked, setPicked] = useState<DiscoveredCalendar | null>(null)
  const [error, setError] = useState<string | null>(null)

  const switchProvider = (id: string) => {
    setProviderId(id)
    const next = providers.find((row) => row.id === id)
    setAuthKind(next?.auth_kinds[0] ?? '')
    setValues({})
    setPicked(null)
  }

  const switchAuthKind = (kind: string) => {
    setAuthKind(kind)
    setValues({})
    setPicked(null)
  }

  const setValue = (key: string, value: string) =>
    setValues((previous) => ({ ...previous, [key]: value }))

  const save = useMutation({
    mutationFn: () =>
      createCalendarLink({
        course_id: courseId,
        provider: providerId,
        label: label.trim() || provider?.label || providerId,
        direction,
        auth_kind: authKind || null,
        base_url: values.base_url?.trim() || null,
        calendar_id: picked?.id ?? null,
        calendar_url: picked?.url ?? (values.calendar_url?.trim() || null),
        username: values.username?.trim() || null,
        secret: values.secret?.trim() || null,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['calendar-links'] })
      onDone()
    },
    onError: (cause: Error) => setError(cause.message),
  })

  const fields = (provider?.setup_fields ?? []).filter((field) =>
    fieldVisible(field, authKind),
  )

  return (
    <form
      className="space-y-2"
      onSubmit={(event) => {
        event.preventDefault()
        setError(null)
        save.mutate()
      }}
    >
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="space-y-1 text-xs">
          <span className="text-muted-foreground">{t('settings.calendar.provider')}</span>
          <select
            className={inputClass}
            value={providerId}
            onChange={(event) => switchProvider(event.target.value)}
          >
            {providers.map((row) => (
              <option key={row.id} value={row.id}>
                {row.label}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-xs">
          <span className="text-muted-foreground">{t('settings.calendar.course')}</span>
          <select
            className={inputClass}
            value={courseId}
            onChange={(event) => setCourseId(event.target.value)}
          >
            <option value="">{t('settings.calendar.pickCourse')}</option>
            {(courses.data ?? []).map((course) => (
              <option key={course.id} value={course.id}>
                {course.title}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-xs">
          <span className="text-muted-foreground">{t('settings.calendar.label')}</span>
          <input
            className={inputClass}
            value={label}
            placeholder={provider?.label ?? ''}
            onChange={(event) => setLabel(event.target.value)}
          />
        </label>
        <label className="space-y-1 text-xs">
          <span className="text-muted-foreground">{t('settings.calendar.direction')}</span>
          <select
            className={inputClass}
            value={direction}
            onChange={(event) => setDirection(event.target.value)}
          >
            <option value="push">{t('settings.calendar.directionPush')}</option>
            <option value="pull">{t('settings.calendar.directionPull')}</option>
            <option value="two-way">{t('settings.calendar.directionTwoWay')}</option>
          </select>
        </label>
        {provider && provider.auth_kinds.length > 1 ? (
          <label className="space-y-1 text-xs">
            <span className="text-muted-foreground">{t('settings.calendar.authKind')}</span>
            <select
              className={inputClass}
              value={authKind}
              onChange={(event) => switchAuthKind(event.target.value)}
            >
              {provider.auth_kinds.map((kind) => (
                <option key={kind} value={kind}>
                  {t(
                    `settings.calendar.${AUTH_KIND_LABEL_KEYS[kind] ?? 'authKindToken'}`,
                  )}
                </option>
              ))}
            </select>
          </label>
        ) : null}
      </div>

      {fields.map((field) =>
        field.kind === 'calendar' ? (
          <div key={field.key} className="space-y-1">
            <CalendarPicker
              provider={provider!}
              authKind={authKind}
              values={values}
              onPicked={(calendar) => setPicked(calendar)}
            />
            {field.manual_key ? (
              <SetupFieldInput
                field={{
                  ...field,
                  key: field.manual_key,
                  kind: 'url',
                  required: false,
                  label_key: 'calendarUrl',
                  placeholder: 'https://cloud.example.com/calendars/user/personal/',
                  autocomplete: null,
                  auth_kind: null,
                }}
                values={values}
                onChange={setValue}
              />
            ) : null}
            {picked ? (
              <p className="text-muted-foreground text-xs">
                {t('settings.calendar.pickedCalendar', { name: picked.name })}
              </p>
            ) : null}
          </div>
        ) : (
          <SetupFieldInput key={field.key} field={field} values={values} onChange={setValue} />
        ),
      )}

      {authKind === 'oauth2' ? (
        <p className="bg-subtle text-muted-foreground rounded-md px-2 py-1.5 text-xs">
          {t('settings.calendar.oauthHint')}
        </p>
      ) : null}
      {provider ? (
        <p className="text-muted-foreground text-xs">{provider.consent_notice}</p>
      ) : null}

      <ErrorBanner message={error} />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onDone}>
          {t('common.cancel')}
        </Button>
        <Button
          type="submit"
          size="sm"
          disabled={!courseId || !providerId || save.isPending}
        >
          {save.isPending ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : null}
          {t('settings.calendar.add')}
        </Button>
      </div>
    </form>
  )
}

interface OAuthPanelProps {
  link: CalendarLink
}

function OAuthPanel({ link }: OAuthPanelProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [code, setCode] = useState('')
  const [state, setState] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const start = useMutation({
    mutationFn: () => startCalendarOAuth(link.id),
    onSuccess: (payload) => {
      setState(payload.state)
      window.open(payload.authorize_url, '_blank', 'noopener,noreferrer')
    },
    onError: (cause: Error) => setError(cause.message),
  })

  const complete = useMutation({
    mutationFn: () => completeCalendarOAuth(link.id, code.trim(), state ?? ''),
    onSuccess: async () => {
      setCode('')
      setState(null)
      await queryClient.invalidateQueries({ queryKey: ['calendar-links'] })
    },
    onError: (cause: Error) => setError(cause.message),
  })

  return (
    <div className="bg-subtle mt-2 space-y-2 rounded-md p-2">
      <p className="text-xs">{t('settings.calendar.oauthSteps')}</p>
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="outline" onClick={() => start.mutate()} disabled={start.isPending}>
          {t('settings.calendar.connectAccount')}
        </Button>
        <input
          className={`${inputClass} max-w-xs`}
          value={code}
          placeholder={t('settings.calendar.codePlaceholder')}
          onChange={(event) => setCode(event.target.value)}
        />
        <Button
          size="sm"
          onClick={() => complete.mutate()}
          disabled={!code.trim() || !state || complete.isPending}
        >
          {t('settings.calendar.finish')}
        </Button>
      </div>
      <ErrorBanner message={error} />
    </div>
  )
}

interface SecretPanelProps {
  link: CalendarLink
}

function SecretPanel({ link }: SecretPanelProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [value, setValue] = useState('')
  const [error, setError] = useState<string | null>(null)
  const save = useMutation({
    mutationFn: () => setCalendarLinkSecret(link.id, value.trim()),
    onSuccess: async () => {
      setValue('')
      await queryClient.invalidateQueries({ queryKey: ['calendar-links'] })
    },
    onError: (cause: Error) => setError(cause.message),
  })
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      <input
        className={`${inputClass} max-w-xs`}
        type="password"
        value={value}
        autoComplete="new-password"
        placeholder={t('settings.calendar.credentialPlaceholder')}
        onChange={(event) => setValue(event.target.value)}
      />
      <Button size="sm" onClick={() => save.mutate()} disabled={!value.trim() || save.isPending}>
        {t('settings.calendar.saveCredential')}
      </Button>
      <ErrorBanner message={error} />
    </div>
  )
}

interface LinkPickerProps {
  link: CalendarLink
  provider: CalendarProvider
}

// Post-bind picker: OAuth accounts (no credential to type at bind time) and
// re-picking a collection. Discovery runs with the link's stored credential.
function LinkCalendarPicker({ link, provider }: LinkPickerProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const patch = useMutation({
    mutationFn: (calendar: DiscoveredCalendar) =>
      updateCalendarLink(link.id, {
        calendar_id: calendar.id,
        calendar_url: calendar.url ?? undefined,
      }),
    onSuccess: async () => {
      setOpen(false)
      await queryClient.invalidateQueries({ queryKey: ['calendar-links'] })
    },
    onError: (cause: Error) => setError(cause.message),
  })

  if (!provider.supports_discovery) return null
  if (link.auth_kind === 'oauth2' && link.status !== 'ok') return null

  return (
    <div className="mt-2 space-y-1">
      {open ? (
        <CalendarPicker
          provider={provider}
          authKind={link.auth_kind}
          values={{}}
          linkId={link.id}
          onPicked={(calendar) => patch.mutate(calendar)}
        />
      ) : (
        <Button size="sm" variant="ghost" onClick={() => setOpen(true)}>
          <CalendarDays className="size-3.5" aria-hidden />
          {t('settings.calendar.chooseCalendar')}
        </Button>
      )}
      <ErrorBanner message={error} />
    </div>
  )
}

export function CalendarCard() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const catalog = useQuery({ queryKey: ['calendar-providers'], queryFn: listCalendarProviders })
  const links = useQuery({ queryKey: ['calendar-links'], queryFn: () => listCalendarLinks() })
  const courses = useQuery({ queryKey: ['courses'], queryFn: listCourses })
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const runSync = useMutation({
    mutationFn: (linkId: string) => syncCalendarLink(linkId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['calendar-links'] })
      await queryClient.invalidateQueries({ queryKey: ['plan-items'] })
    },
    onError: (cause: Error) => setError(cause.message),
  })
  const runTest = useMutation({
    mutationFn: (linkId: string) => testCalendarLink(linkId),
    onError: (cause: Error) => setError(cause.message),
  })
  const remove = useMutation({
    mutationFn: (linkId: string) => deleteCalendarLink(linkId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['calendar-links'] })
    },
    onError: (cause: Error) => setError(cause.message),
  })

  const courseTitle = (id: string) =>
    (courses.data ?? []).find((course) => course.id === id)?.title ?? id

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CalendarDays className="size-4" aria-hidden />
          {t('settings.calendar.title')}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-muted-foreground text-xs">{t('settings.calendar.hint')}</p>

        <ErrorBanner
          message={
            error ??
            (catalog.isError ? (catalog.error as Error).message : null) ??
            (links.isError ? (links.error as Error).message : null)
          }
        />

        {catalog.data?.providers.length ? (
          adding ? (
            <AddCalendarForm
              providers={catalog.data.providers}
              onDone={() => setAdding(false)}
            />
          ) : (
            <Button size="sm" variant="outline" onClick={() => setAdding(true)}>
              <Plus className="size-3.5" aria-hidden />
              {t('settings.calendar.bind')}
            </Button>
          )
        ) : null}

        <div className="space-y-2">
          {(links.data ?? []).map((link) => {
            const provider = catalog.data?.providers.find((row) => row.id === link.provider)
            const needsOAuth = link.auth_kind === 'oauth2' && link.status === 'needs-auth'
            const needsSecret =
              ['app-password', 'token'].includes(link.auth_kind) &&
              !link.secret_configured
            return (
              <div key={link.id} className="border-border rounded-md border p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium">
                      {link.label}{' '}
                      <span className="text-muted-foreground font-normal">
                        · {provider?.label ?? link.provider}
                      </span>
                    </p>
                    <p className="text-muted-foreground text-xs">
                      {courseTitle(link.course_id)} · {link.direction} ·{' '}
                      <span className={statusTone(link.status)}>{link.status}</span>
                      {link.last_synced_at
                        ? ` · ${t('settings.calendar.lastSync')} ${new Date(link.last_synced_at).toLocaleString()}`
                        : ''}
                    </p>
                    {needsAttention(link) && link.last_error ? (
                      <p className="text-destructive mt-1 text-xs">{link.last_error}</p>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap items-center gap-1">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => runTest.mutate(link.id)}
                      disabled={runTest.isPending}
                    >
                      <Unplug className="size-3.5" aria-hidden />
                      {t('settings.calendar.test')}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => runSync.mutate(link.id)}
                      disabled={runSync.isPending}
                    >
                      <RefreshCw
                        className={`size-3.5 ${runSync.isPending ? 'animate-spin' : ''}`}
                        aria-hidden
                      />
                      {t('settings.calendar.sync')}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => remove.mutate(link.id)}
                      disabled={remove.isPending}
                      aria-label={t('settings.calendar.disconnect')}
                    >
                      <Trash2 className="size-3.5" aria-hidden />
                    </Button>
                  </div>
                </div>
                {provider ? (
                  <LinkCalendarPicker link={link} provider={provider} />
                ) : null}
                {needsOAuth ? <OAuthPanel link={link} /> : null}
                {needsSecret ? <SecretPanel link={link} /> : null}
              </div>
            )
          })}
          {links.isPending ? (
            <p className="text-muted-foreground flex items-center gap-2 text-xs">
              <Loader2 className="size-3.5 animate-spin" aria-hidden />
              {t('settings.calendar.loading')}
            </p>
          ) : null}
          {!links.isPending && (links.data ?? []).length === 0 ? (
            <p className="text-muted-foreground text-xs">{t('settings.calendar.empty')}</p>
          ) : null}
        </div>
      </CardContent>
    </Card>
  )
}
