import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { AudioPlayerBar } from './AudioPlayerBar'
import { AudioPlayerProvider, useAudioPlayer } from '@/lib/audio-player'
import { audioCacheName } from '@/lib/audio-offline'
import { installFakeCaches } from '@/test/caches'

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => vi.fn(),
}))

const { apiFetch } = vi.hoisted(() => ({ apiFetch: vi.fn() }))
vi.mock('@/lib/api/client', () => ({
  apiFetch,
  UNAUTHENTICATED_EVENT: 'nx:unauthenticated',
}))

const SCOPE = 'u:user-1:p:profile-a'

function Harness() {
  const player = useAudioPlayer()
  return (
    <button
      type="button"
      onClick={() =>
        player.play({ materialId: 'm1', title: 'Lecture recording', src: '/audio.webm' })
      }
    >
      load
    </button>
  )
}

function renderPlayer() {
  return render(
    <AudioPlayerProvider scope={SCOPE}>
      <Harness />
      <AudioPlayerBar />
    </AudioPlayerProvider>,
  )
}

describe('AudioPlayerBar', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  beforeEach(() => {
    apiFetch.mockReset()
    apiFetch.mockResolvedValue(new Response(new Blob(['bytes'])))
    Object.defineProperty(HTMLMediaElement.prototype, 'play', {
      configurable: true,
      value: vi.fn().mockResolvedValue(undefined),
    })
    Object.defineProperty(HTMLMediaElement.prototype, 'pause', {
      configurable: true,
      value: vi.fn(),
    })
  })

  test('appears when a track starts and can be closed', () => {
    renderPlayer()
    fireEvent.click(screen.getByRole('button', { name: 'load' }))
    expect(screen.getByText('Lecture recording')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Close audio player' }))
    expect(screen.queryByText('Lecture recording')).not.toBeInTheDocument()
  })

  test('downloads the current track for offline and can remove it', async () => {
    const storage = installFakeCaches()
    renderPlayer()
    fireEvent.click(screen.getByRole('button', { name: 'load' }))
    const download = await screen.findByRole('button', { name: 'Download for offline' })
    fireEvent.click(download)
    const cache = storage.cache(audioCacheName(SCOPE))
    await waitFor(() => expect(cache?.put).toHaveBeenCalled())
    expect(cache?.add).not.toHaveBeenCalled()
    const remove = await screen.findByRole('button', { name: 'Remove offline download' })
    fireEvent.click(remove)
    await waitFor(() => expect(cache?.delete).toHaveBeenCalledWith('/audio.webm'))
  })
})
