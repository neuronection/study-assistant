import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { WebSourcesCard } from './WebSourcesCard'

const listExternalSources = vi.fn()
const listSourceProviders = vi.fn()
const createExternalSource = vi.fn()
const updateExternalSource = vi.fn()
const deleteExternalSource = vi.fn()
const scanExternalSource = vi.fn()
const listCourses = vi.fn()
const connectExternalSource = vi.fn()
const disconnectExternalSource = vi.fn()
const uploadExternalBackup = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listExternalSources: (...args: Parameters<typeof actual.listExternalSources>) =>
      listExternalSources(...args),
    listSourceProviders: () => listSourceProviders(),
    createExternalSource: (body: unknown) => createExternalSource(body),
    updateExternalSource: (id: string, body: unknown) =>
      updateExternalSource(id, body),
    deleteExternalSource: (id: string) => deleteExternalSource(id),
    scanExternalSource: (id: string) => scanExternalSource(id),
    connectExternalSource: (id: string) => connectExternalSource(id),
    disconnectExternalSource: (id: string) => disconnectExternalSource(id),
    uploadExternalBackup: (id: string) => uploadExternalBackup(id),
    listCourses: () => listCourses(),
  }
})

const COURSES = [
  { id: '7', title: 'Calculus I' },
  { id: '8', title: 'Algebra' },
]

const SOURCE = {
  id: '3',
  course_id: '7',
  kind: 'rss',
  url: 'https://math.example/feed',
  label: 'Math Feed',
  options: {},
  enabled: true,
  scan_interval_sec: null,
  last_scan_error: null,
  last_scanned_at: null,
}

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <WebSourcesCard />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  listExternalSources.mockReset().mockResolvedValue([SOURCE])
  listSourceProviders.mockReset().mockResolvedValue({
    providers: [
      {
        id: 'rss',
        label: 'RSS / Atom feed',
        kinds: ['rss'],
        default_kind: 'rss',
        auth_kind: 'none',
        url_required: true,
        fields: ['url', 'max_items'],
        supports_backup: false,
        secret_slots: [],
        oauth: null,
      },
      {
        id: 'youtube',
        label: 'YouTube channel / playlist',
        kinds: ['youtube_channel', 'youtube_playlist'],
        default_kind: 'youtube_channel',
        auth_kind: 'none',
        url_required: true,
        fields: ['url', 'max_items'],
        supports_backup: false,
        secret_slots: [],
        oauth: null,
      },
      {
        id: 'site-search',
        label: 'Site search',
        kinds: ['site_search'],
        default_kind: 'site_search',
        auth_kind: 'none',
        url_required: true,
        fields: ['url', 'query', 'site'],
        supports_backup: false,
        secret_slots: [],
        oauth: null,
      },
    ],
    secret_disclosure:
      "Secret values are stored only in your operating system's keyring. They never enter the database, a config file, an environment block or a model prompt.",
  })
  createExternalSource.mockReset()
  updateExternalSource.mockReset().mockResolvedValue(SOURCE)
  deleteExternalSource.mockReset().mockResolvedValue(undefined)
  scanExternalSource.mockReset().mockResolvedValue({ new: 2, updated: 1 })
  listCourses.mockReset().mockResolvedValue(COURSES)
  connectExternalSource.mockReset().mockResolvedValue({ status: 'ok' })
  disconnectExternalSource.mockReset().mockResolvedValue({ status: 'needs-config' })
  uploadExternalBackup.mockReset().mockResolvedValue({
    name: 'manual-20261022-120000.zip',
    size: 10,
    location: 'https://cloud.example/dav/manual-20261022-120000.zip',
  })
})

describe('WebSourcesCard', () => {
  test('lists sources with kind, course and error badge', async () => {
    listExternalSources.mockResolvedValue([
      SOURCE,
      {
        ...SOURCE,
        id: '4',
        kind: 'youtube_channel',
        label: 'Math channel',
        enabled: false,
        last_scan_error: 'extractor broken',
      },
    ])
    renderCard()
    expect(await screen.findByText('Math Feed')).toBeInTheDocument()
    expect(screen.getAllByText('Calculus I').length).toBeGreaterThan(0)
    expect(screen.getByText('Math channel')).toBeInTheDocument()
    expect(screen.getByText(/extractor broken/)).toBeInTheDocument()
    expect(screen.getByText('Off')).toBeInTheDocument()
  })

  test('adding an RSS source posts it for the chosen course', async () => {
    createExternalSource.mockResolvedValue(SOURCE)
    renderCard()
    fireEvent.click(await screen.findByRole('button', { name: /add source/i }))
    fireEvent.change(
      await screen.findByPlaceholderText('https://example.com/feed.xml'),
      { target: { value: 'https://new.example/rss' } },
    )
    fireEvent.change(screen.getByLabelText('Label'), {
      target: { value: 'New feed' },
    })
    fireEvent.change(screen.getByLabelText('Course'), {
      target: { value: '8' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))
    await waitFor(() =>
      expect(createExternalSource).toHaveBeenCalledWith(
        expect.objectContaining({
          course_id: '8',
          provider: 'rss',
          kind: 'rss',
          url: 'https://new.example/rss',
          label: 'New feed',
        }),
      ),
    )
  })

  test('site search sources require a query before saving', async () => {
    createExternalSource.mockResolvedValue(SOURCE)
    renderCard()
    fireEvent.click(await screen.findByRole('button', { name: /add source/i }))
    fireEvent.change(screen.getByLabelText('Provider'), {
      target: { value: 'site-search' },
    })
    expect(screen.getByLabelText('Search query')).toBeInTheDocument()
    const save = screen.getByRole('button', { name: /^save$/i })
    expect(save).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Search query'), {
      target: { value: 'calculus' },
    })
    expect(save).toBeEnabled()
    fireEvent.change(screen.getByLabelText('Site filter (domain)'), {
      target: { value: 'khanacademy.org' },
    })
    fireEvent.change(screen.getByLabelText('Course'), {
      target: { value: '8' },
    })
    fireEvent.click(save)
    await waitFor(() =>
      expect(createExternalSource).toHaveBeenCalledWith(
        expect.objectContaining({
          provider: 'site-search',
          kind: 'site_search',
          options: { query: 'calculus', site: 'khanacademy.org' },
        }),
      ),
    )
  })

  test('scan now surfaces the new count and refreshes suggestions', async () => {
    renderCard()
    fireEvent.click(await screen.findByRole('button', { name: /scan now/i }))
    await waitFor(() => expect(scanExternalSource).toHaveBeenCalledWith('3'))
    expect(
      await screen.findByText(/scan finished — 2 new/i),
    ).toBeInTheDocument()
  })

  test('toggle and delete update the list', async () => {
    renderCard()
    fireEvent.click(await screen.findByRole('checkbox', { name: /enabled/i }))
    await waitFor(() =>
      expect(updateExternalSource).toHaveBeenCalledWith('3', { enabled: false }),
    )
    fireEvent.click(screen.getByRole('button', { name: /delete/i }))
    await waitFor(() => expect(deleteExternalSource).toHaveBeenCalledWith('3'))
  })

  test('catalog-driven providers expose connect and backup actions', async () => {
    const provider = (overrides: Record<string, unknown>) => ({
      kinds: [],
      default_kind: 'rss',
      auth_kind: 'none',
      url_required: true,
      fields: [],
      supports_backup: false,
      secret_slots: [],
      oauth: null,
      ...overrides,
    })
    listSourceProviders.mockResolvedValue({
      providers: [
        provider({ id: 'rss', label: 'RSS / Atom feed', kinds: ['rss'], default_kind: 'rss' }),
        provider({
          id: 'webdav',
          label: 'WebDAV / Nextcloud',
          kinds: ['webdav_folder'],
          default_kind: 'webdav_folder',
          auth_kind: 'token',
          fields: ['url', 'username'],
          supports_backup: true,
          secret_slots: [{ name: 'password', label: 'App password', required: true }],
        }),
        provider({
          id: 'google-drive',
          label: 'Google Drive',
          kinds: ['cloud_folder'],
          default_kind: 'cloud_folder',
          auth_kind: 'oauth2',
          url_required: false,
          oauth: { scopes: ['drive.readonly'], client_id_env: 'SA_GOOGLE_CLIENT_ID' },
        }),
      ],
      secret_disclosure:
        "Secret values are stored only in your operating system's keyring. They never enter the database, a config file, an environment block or a model prompt.",
    })
    listExternalSources.mockResolvedValue([
      {
        ...SOURCE,
        id: '9',
        provider: 'google-drive',
        kind: 'cloud_folder',
        auth_kind: 'oauth2',
        url: '',
        label: 'Drive notes',
        status: 'degraded',
        consecutive_failures: 1,
        conditions: ['needs-config'],
        secrets_configured: { oauth: false },
      },
      {
        ...SOURCE,
        id: '10',
        provider: 'webdav',
        kind: 'webdav_folder',
        auth_kind: 'token',
        label: 'Cloud notes',
        secrets_configured: { password: true },
      },
    ])
    renderCard()
    expect(await screen.findByText('Drive notes')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /^connect$/i }))
    await waitFor(() => expect(connectExternalSource).toHaveBeenCalledWith('9'))
    fireEvent.click(screen.getAllByRole('button', { name: /back up now/i })[0])
    await waitFor(() => expect(uploadExternalBackup).toHaveBeenCalledWith('10'))
    expect(await screen.findByText(/backup uploaded/i)).toBeInTheDocument()
  })

  test('token providers render the charter secret disclosure verbatim', async () => {
    listSourceProviders.mockResolvedValue({
      providers: [
        {
          id: 'webdav',
          label: 'WebDAV / Nextcloud',
          kinds: ['webdav_folder'],
          default_kind: 'webdav_folder',
          auth_kind: 'token',
          url_required: true,
          fields: ['url', 'username'],
          supports_backup: true,
          secret_slots: [{ name: 'password', label: 'App password', required: true }],
          oauth: null,
        },
      ],
      secret_disclosure:
        "Secret values are stored only in your operating system's keyring. They never enter the database, a config file, an environment block or a model prompt.",
    })
    renderCard()
    fireEvent.click(await screen.findByRole('button', { name: /add source/i }))
    fireEvent.change(screen.getByLabelText('Provider'), { target: { value: 'webdav' } })
    expect(screen.getByLabelText('App password')).toBeInTheDocument()
    expect(
      screen.getByText(
        "Secret values are stored only in your operating system's keyring. They never enter the database, a config file, an environment block or a model prompt.",
      ),
    ).toBeInTheDocument()
  })
})
