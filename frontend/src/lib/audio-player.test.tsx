import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { installFakeCaches } from '@/test/caches'

import { AudioPlayerProvider, useAudioPlayer } from './audio-player'
import { audioCacheName, audioStateKey } from './audio-offline'
import { resetSessionScopeForTests } from './session-scope'

const { apiFetch } = vi.hoisted(() => ({ apiFetch: vi.fn() }))
vi.mock('./api/client', () => ({
  apiFetch,
  UNAUTHENTICATED_EVENT: 'nx:unauthenticated',
}))

const SCOPE_A = 'u:user-1:p:profile-a'
const SCOPE_B = 'u:user-1:p:profile-b'
const SCOPE_C = 'u:user-1:p:profile-c'
const SRC_A = '/api/v1/blobs/a'
const SRC_B = '/api/v1/blobs/b'

const pause = vi.fn()
const play = vi.fn()
const createObjectURL = vi.fn(() => 'blob:mock-url')
const revokeObjectURL = vi.fn()

function Harness() {
  const player = useAudioPlayer()
  return (
    <div>
      <span data-testid="title">{player.track?.title ?? 'none'}</span>
      <span data-testid="offline">{player.offline}</span>
      <span data-testid="sleep">{player.sleepMinutes ?? 'none'}</span>
      <span data-testid="downloading">{player.downloading ? 'yes' : 'no'}</span>
      <button
        type="button"
        onClick={() =>
          player.play({ materialId: 'a', title: 'First lecture', src: SRC_A })
        }
      >
        play-a
      </button>
      <button
        type="button"
        onClick={() =>
          player.play({ materialId: 'b', title: 'Second lecture', src: SRC_B })
        }
      >
        play-b
      </button>
      <button type="button" onClick={player.download}>
        download
      </button>
      <button type="button" onClick={() => player.setSleepTimer(5)}>
        sleep
      </button>
      <button type="button" onClick={player.stop}>
        stop
      </button>
    </div>
  )
}

function renderPlayer(scope: string | null) {
  return render(
    <AudioPlayerProvider scope={scope}>
      <Harness />
    </AudioPlayerProvider>,
  )
}

function persist(scope: string, title: string, src: string) {
  window.localStorage.setItem(
    audioStateKey(scope),
    JSON.stringify({
      track: { materialId: title, title, src },
      positionMs: 1200,
      speed: 1.25,
    }),
  )
}

describe('AudioPlayerProvider scope isolation', () => {
  beforeEach(() => {
    resetSessionScopeForTests()
    window.localStorage.clear()
    apiFetch.mockReset()
    pause.mockReset()
    play.mockReset().mockResolvedValue(undefined)
    createObjectURL.mockClear()
    revokeObjectURL.mockClear()
    Object.defineProperty(HTMLMediaElement.prototype, 'play', {
      configurable: true,
      value: play,
    })
    Object.defineProperty(HTMLMediaElement.prototype, 'pause', {
      configurable: true,
      value: pause,
    })
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: createObjectURL,
    })
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: revokeObjectURL,
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  test('ignores persisted state until the scope resolves, then loads its own', async () => {
    installFakeCaches()
    persist(SCOPE_A, 'Scoped lecture', SRC_A)

    const { rerender } = renderPlayer(null)
    expect(screen.getByTestId('title')).toHaveTextContent('none')

    rerender(
      <AudioPlayerProvider scope={SCOPE_A}>
        <Harness />
      </AudioPlayerProvider>,
    )
    await waitFor(() =>
      expect(screen.getByTestId('title')).toHaveTextContent('Scoped lecture'),
    )
  })

  test('a scope change stops playback and loads the new scope state', async () => {
    const storage = installFakeCaches()
    persist(SCOPE_B, 'Second lecture', SRC_B)
    await storage.open(audioCacheName(SCOPE_A))

    const { rerender } = renderPlayer(SCOPE_A)
    fireEvent.click(screen.getByRole('button', { name: 'play-a' }))
    expect(screen.getByTestId('title')).toHaveTextContent('First lecture')

    rerender(
      <AudioPlayerProvider scope={SCOPE_B}>
        <Harness />
      </AudioPlayerProvider>,
    )

    await waitFor(() =>
      expect(screen.getByTestId('title')).toHaveTextContent('Second lecture'),
    )
    expect(pause).toHaveBeenCalled()
    expect(await caches.keys()).toContain(audioCacheName(SCOPE_A))
  })

  test('a scope without persisted state starts empty and never shows the old title', async () => {
    installFakeCaches()
    const { rerender } = renderPlayer(SCOPE_A)
    fireEvent.click(screen.getByRole('button', { name: 'play-a' }))
    expect(screen.getByTestId('title')).toHaveTextContent('First lecture')

    rerender(
      <AudioPlayerProvider scope={SCOPE_C}>
        <Harness />
      </AudioPlayerProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('title')).toHaveTextContent('none'))
    expect(pause).toHaveBeenCalled()
  })

  test('stop revokes the object URL and clears only the current scope state', async () => {
    const storage = installFakeCaches()
    persist(SCOPE_A, 'Cached lecture', SRC_A)
    persist(SCOPE_B, 'Other lecture', SRC_B)
    await storage.seed(audioCacheName(SCOPE_A), SRC_A, new Blob(['bytes']))
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)

    renderPlayer(SCOPE_A)
    await waitFor(() =>
      expect(screen.getByTestId('title')).toHaveTextContent('Cached lecture'),
    )
    await waitFor(() => expect(createObjectURL).toHaveBeenCalled())
    const url = createObjectURL.mock.results[0]?.value

    fireEvent.click(screen.getByRole('button', { name: 'stop' }))

    expect(revokeObjectURL).toHaveBeenCalledWith(url)
    expect(pause).toHaveBeenCalled()
    expect(window.localStorage.getItem(audioStateKey(SCOPE_A))).toBeNull()
    expect(window.localStorage.getItem(audioStateKey(SCOPE_B))).not.toBeNull()
  })

  test('session loss pauses the audio element', async () => {
    installFakeCaches()
    renderPlayer(SCOPE_A)
    fireEvent.click(screen.getByRole('button', { name: 'play-a' }))
    await waitFor(() => expect(play).toHaveBeenCalled())

    window.dispatchEvent(new Event('nx:unauthenticated'))

    await waitFor(() => expect(pause).toHaveBeenCalled())
    expect(screen.getByTestId('title')).toHaveTextContent('none')
  })

  test('download uses apiFetch and the scoped cache, never cache.add', async () => {
    const storage = installFakeCaches()
    apiFetch.mockResolvedValue(new Response(new Blob(['bytes'])))
    renderPlayer(SCOPE_A)
    fireEvent.click(screen.getByRole('button', { name: 'play-a' }))

    fireEvent.click(screen.getByRole('button', { name: 'download' }))

    await waitFor(() => expect(apiFetch).toHaveBeenCalledWith(SRC_A))
    const cache = storage.cache(audioCacheName(SCOPE_A))
    await waitFor(() => expect(cache?.put).toHaveBeenCalled())
    expect(cache?.add).not.toHaveBeenCalled()
  })

  test('a scope change resets the sleep timer and download state', async () => {
    installFakeCaches()
    const { rerender } = renderPlayer(SCOPE_A)
    fireEvent.click(screen.getByRole('button', { name: 'play-a' }))
    fireEvent.click(screen.getByRole('button', { name: 'sleep' }))
    expect(screen.getByTestId('sleep')).toHaveTextContent('5')

    rerender(
      <AudioPlayerProvider scope={SCOPE_C}>
        <Harness />
      </AudioPlayerProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('sleep')).toHaveTextContent('none'))
    expect(screen.getByTestId('downloading')).toHaveTextContent('no')
  })

  test('an in-flight download cannot write into the new scope', async () => {
    installFakeCaches()
    persist(SCOPE_B, 'Second lecture', SRC_B)
    let resolveFetch: ((response: Response) => void) | undefined
    apiFetch.mockImplementation(
      () =>
        new Promise<Response>((resolve) => {
          resolveFetch = resolve
        }),
    )
    const { rerender } = renderPlayer(SCOPE_A)
    fireEvent.click(screen.getByRole('button', { name: 'play-a' }))
    fireEvent.click(screen.getByRole('button', { name: 'download' }))
    expect(screen.getByTestId('downloading')).toHaveTextContent('yes')

    rerender(
      <AudioPlayerProvider scope={SCOPE_B}>
        <Harness />
      </AudioPlayerProvider>,
    )
    await waitFor(() =>
      expect(screen.getByTestId('title')).toHaveTextContent('Second lecture'),
    )
    await waitFor(() => expect(screen.getByTestId('offline')).toHaveTextContent('not-cached'))

    resolveFetch?.(new Response(new Blob(['bytes'])))
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(screen.getByTestId('offline')).toHaveTextContent('not-cached')
    expect(screen.getByTestId('downloading')).toHaveTextContent('no')
  })
})
