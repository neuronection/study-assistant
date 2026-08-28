import { afterEach, describe, expect, test, vi } from 'vitest'

import {
  apiDetailMessage,
  apiFetch,
  createModel,
  dueFlashcards,
  getDiagnostics,
  getHealth,
  importAnkiDeck,
  importInboxFile,
  importQuiz,
  importQpkg,
  listNotes,
  listQuizzes,
  setActiveProfile,
} from './api'

describe('getHealth', () => {
  test('returns parsed health payload on ok response', async () => {
    const fetchFn = vi.fn(
      async () => new Response(JSON.stringify({ status: 'ok', version: '1.2.3', db: 'ok' }), { status: 200 })
    )
    const health = await getHealth(fetchFn as unknown as typeof fetch)
    expect(health).toEqual({ status: 'ok', version: '1.2.3', db: 'ok' })
    expect(fetchFn).toHaveBeenCalledWith('/api/v1/health')
  })

  test('throws on error status', async () => {
    const fetchFn = vi.fn(async () => new Response('boom', { status: 500 }))
    await expect(getHealth(fetchFn as unknown as typeof fetch)).rejects.toThrow(
      'health check failed: 500'
    )
  })
})

describe('apiDetailMessage', () => {
  test('passes string details through', () => {
    expect(apiDetailMessage('provider not found')).toBe('provider not found')
    expect(apiDetailMessage('   ')).toBeNull()
    expect(apiDetailMessage(null)).toBeNull()
  })

  test('flattens FastAPI validation arrays into a readable message', () => {
    const detail = [
      {
        type: 'value_error',
        loc: ['body', 'caps'],
        msg: "Value error, unknown caps: telepathy",
        input: ['telepathy'],
      },
    ]
    expect(apiDetailMessage(detail)).toBe(
      'caps: Value error, unknown caps: telepathy',
    )
  })

  test('createModel surfaces a readable message on 422, not [object Object]', async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            detail: [
              {
                type: 'value_error',
                loc: ['body', 'caps'],
                msg: 'Value error, unknown caps: audio',
                input: ['audio'],
              },
            ],
          }),
          { status: 422 },
        ),
    )
    vi.stubGlobal('fetch', fetchMock)
    await expect(
      createModel({ provider_id: 1, external_id: 'whisper-1', caps: ['audio'] })
    ).rejects.toThrow('caps: Value error, unknown caps: audio')
  })
})

describe('apiFetch', () => {
  const makeFetchMock = () =>
    vi.fn(
      async (url: RequestInfo | URL, init?: RequestInit) => {
        void url
        void init
        return new Response('{}', { status: 200 })
      }
    )

  afterEach(() => {
    setActiveProfile(null)
    vi.unstubAllGlobals()
  })

  test('delegates to global fetch exactly once', async () => {
    const fetchMock = makeFetchMock()
    vi.stubGlobal('fetch', fetchMock)
    await apiFetch('/api/v1/courses')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/courses', { headers: new Headers() })
  })

  test('attaches active profile header', async () => {
    const fetchMock = makeFetchMock()
    vi.stubGlobal('fetch', fetchMock)
    setActiveProfile(7)
    await apiFetch('/api/v1/courses')
    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(new Headers(init.headers).get('X-Profile-Id')).toBe('7')
  })

  test('preserves existing headers', async () => {
    const fetchMock = makeFetchMock()
    vi.stubGlobal('fetch', fetchMock)
    await apiFetch('/api/v1/courses', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    })
    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(init.method).toBe('POST')
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
  })
})

describe('course scoping params', () => {
  const makeFetchMock = () =>
    vi.fn(async () => new Response('[]', { status: 200 }))

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  test('listQuizzes appends course_id only when provided', async () => {
    const fetchMock = makeFetchMock()
    vi.stubGlobal('fetch', fetchMock)
    await listQuizzes()
    await listQuizzes(5)
    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/v1/quiz/activities', {
      headers: new Headers(),
    })
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/v1/quiz/activities?course_id=5', {
      headers: new Headers(),
    })
  })

  test('dueFlashcards combines limit and course_id', async () => {
    const fetchMock = makeFetchMock()
    vi.stubGlobal('fetch', fetchMock)
    await dueFlashcards(20, 7)
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/flashcards/due?limit=20&course_id=7', {
      headers: new Headers(),
    })
  })

  test('listNotes combines query and course_id with encoding', async () => {
    const fetchMock = makeFetchMock()
    vi.stubGlobal('fetch', fetchMock)
    await listNotes('chain rule', 3)
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/notes?q=chain+rule&course_id=3', {
      headers: new Headers(),
    })
  })

  test('importQuiz appends course_id to dry_run', async () => {
    const fetchMock = makeFetchMock()
    vi.stubGlobal('fetch', fetchMock)
    await importQuiz({ title: 'T', questions: [] }, false, 9)
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/quiz/import?dry_run=false&course_id=9')
    expect(init.method).toBe('POST')
  })

  test('importQpkg sends the required course_id query param', async () => {
    const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    await importQpkg(new File(['x'], 'deck.qpkg'), true, 3)
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/quiz/import-qpkg?dry_run=true&course_id=3')
    expect(init.method).toBe('POST')
  })

  test('importInboxFile sends the required course_id query param', async () => {
    const fetchMock = makeFetchMock()
    vi.stubGlobal('fetch', fetchMock)
    await importInboxFile('set 1.caq.json', 5)
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/quiz/inbox/set%201.caq.json/import?course_id=5')
    expect(init.method).toBe('POST')
  })

  test('importAnkiDeck sends the required course_id query param', async () => {
    const fetchMock = makeFetchMock()
    vi.stubGlobal('fetch', fetchMock)
    await importAnkiDeck(new File(['x'], 'deck.apkg'), 7)
    const [url] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/flashcards/import-anki?course_id=7')
  })

  test('getDiagnostics appends course_id only when provided', async () => {
    const fetchMock = makeFetchMock()
    vi.stubGlobal('fetch', fetchMock)
    await getDiagnostics()
    await getDiagnostics(4)
    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/v1/analytics/diagnostics', {
      headers: new Headers(),
    })
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/v1/analytics/diagnostics?course_id=4', {
      headers: new Headers(),
    })
  })
})
