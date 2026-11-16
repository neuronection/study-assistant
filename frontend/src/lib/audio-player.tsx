import { createContext, useContext, useEffect, useRef, useState } from 'react'

import {
  audioStateKey,
  cacheAudio,
  offlineAudioSupported,
  readCachedAudio,
  removeCachedAudio,
  type OfflineAudioState,
} from './audio-offline'
import { UNAUTHENTICATED_EVENT } from './api/client'
import { rememberSessionScope } from './session-scope'

export interface AudioTrack {
  materialId: string
  title: string
  src: string
}

interface AudioPlayerValue {
  track: AudioTrack | null
  playing: boolean
  positionMs: number
  durationMs: number
  speed: number
  sleepMinutes: number | null
  play: (track: AudioTrack) => void
  toggle: (track?: AudioTrack) => void
  seek: (ms: number) => void
  setSpeed: (speed: number) => void
  setSleepTimer: (minutes: number | null) => void
  offline: OfflineAudioState
  canDownload: boolean
  downloading: boolean
  downloadError: boolean
  download: () => void
  removeDownload: () => void
  stop: () => void
}

const AudioPlayerContext = createContext<AudioPlayerValue | null>(null)

interface PersistedAudio {
  track: AudioTrack
  positionMs: number
  speed: number
}

function loadPersisted(scope: string): PersistedAudio | null {
  try {
    const raw = window.localStorage.getItem(audioStateKey(scope))
    if (!raw) {
      return null
    }
    const value = JSON.parse(raw) as Partial<PersistedAudio>
    if (
      value.track &&
      typeof value.track.materialId === 'string' &&
      typeof value.track.title === 'string' &&
      typeof value.track.src === 'string'
    ) {
      return {
        track: value.track,
        positionMs: Number(value.positionMs) || 0,
        speed: Number(value.speed) || 1,
      }
    }
    return null
  } catch {
    return null
  }
}

function savePersisted(scope: string, value: PersistedAudio | null): void {
  try {
    if (value === null) {
      window.localStorage.removeItem(audioStateKey(scope))
      return
    }
    window.localStorage.setItem(audioStateKey(scope), JSON.stringify(value))
  } catch {
    // best effort
  }
}

/** One app-shell player. The provider mounts with the resolved
 * `(user, profile)` scope: until it is non-null no persisted state or cache
 * is read, and a scope change releases the old playback before the new
 * scope's state loads. Storage cleanup is owned by `audio-offline.ts`;
 * this provider only owns the `<audio>` element, object URLs and in-memory
 * state. */
export function AudioPlayerProvider({
  scope,
  children,
}: {
  scope: string | null
  children: React.ReactNode
}) {
  const audio = useRef<HTMLAudioElement>(null)
  const objectUrl = useRef<string | null>(null)
  const scopeRef = useRef<string | null>(scope)
  const activeScopeRef = useRef<string | null>(scope)
  activeScopeRef.current = scope
  const [track, setTrack] = useState<AudioTrack | null>(null)
  const [playing, setPlaying] = useState(false)
  const [positionMs, setPositionMs] = useState(0)
  const [durationMs, setDurationMs] = useState(0)
  const [speed, setSpeedState] = useState(1)
  const [sleepMinutes, setSleepMinutes] = useState<number | null>(null)
  const [resolvedSrc, setResolvedSrc] = useState<string | null>(null)
  const [offline, setOffline] = useState<OfflineAudioState>('unknown')
  const [downloading, setDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState(false)
  const [loadedScope, setLoadedScope] = useState<string | null>(null)

  const releaseObjectUrl = () => {
    if (objectUrl.current !== null) {
      URL.revokeObjectURL(objectUrl.current)
      objectUrl.current = null
    }
  }

  const stopPlayerForScopeChange = () => {
    const element = audio.current
    if (element) {
      element.pause()
    }
    releaseObjectUrl()
    setPlaying(false)
    setTrack(null)
    setPositionMs(0)
    setDurationMs(0)
    setResolvedSrc(null)
    setOffline('unknown')
    setDownloadError(false)
    setDownloading(false)
    setSleepMinutes(null)
  }
  const stopPlayerForScopeChangeRef = useRef(stopPlayerForScopeChange)
  stopPlayerForScopeChangeRef.current = stopPlayerForScopeChange

  useEffect(() => {
    const previous = scopeRef.current
    scopeRef.current = scope
    if (previous !== scope) {
      stopPlayerForScopeChangeRef.current()
      setLoadedScope(null)
    }
    if (scope === null) {
      return
    }
    rememberSessionScope(scope)
    const persisted = loadPersisted(scope)
    setLoadedScope(scope)
    if (persisted !== null) {
      setTrack(persisted.track)
      setPositionMs(persisted.positionMs)
      setSpeedState(persisted.speed)
    } else {
      setTrack(null)
      setPositionMs(0)
      setSpeedState(1)
    }
  }, [scope])

  useEffect(() => {
    const onSessionLoss = () => {
      stopPlayerForScopeChangeRef.current()
      setLoadedScope(null)
    }
    window.addEventListener(UNAUTHENTICATED_EVENT, onSessionLoss)
    return () => window.removeEventListener(UNAUTHENTICATED_EVENT, onSessionLoss)
  }, [])

  useEffect(() => {
    if (scope === null || loadedScope !== scope) {
      return
    }
    if (track === null) {
      savePersisted(scope, null)
      return
    }
    savePersisted(scope, { track, positionMs, speed })
  }, [scope, loadedScope, track, positionMs, speed])

  useEffect(() => {
    const element = audio.current
    if (!element) {
      return
    }
    element.playbackRate = speed
  }, [speed, track])

  useEffect(() => {
    releaseObjectUrl()
    setDownloadError(false)
    if (scope === null || loadedScope !== scope) {
      setResolvedSrc(null)
      setOffline('unknown')
      return undefined
    }
    if (!track) {
      setResolvedSrc(null)
      setOffline('unknown')
      return undefined
    }
    let cancelled = false
    setOffline('unknown')
    setResolvedSrc(track.src)
    void readCachedAudio(scope, track.src)
      .then((blob) => {
        if (cancelled || blob === null) {
          if (!cancelled) setOffline('not-cached')
          return
        }
        setOffline('cached')
        if (navigator.onLine === false) {
          const url = URL.createObjectURL(blob)
          releaseObjectUrl()
          objectUrl.current = url
          setResolvedSrc(url)
        }
      })
      .catch(() => {
        if (!cancelled) setOffline('not-cached')
      })
    return () => {
      cancelled = true
    }
  }, [track, scope, loadedScope])

  useEffect(() => releaseObjectUrl, [])

  useEffect(() => {
    if (!('mediaSession' in navigator) || !track || loadedScope !== scope) {
      return
    }
    try {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: track.title,
        artist: 'Study Assistant',
      })
    } catch {
      // Media Session is optional
    }
  }, [track, scope, loadedScope])

  const play = (next: AudioTrack) => {
    if (scope === null) {
      return
    }
    if (track?.materialId !== next.materialId) {
      setTrack(next)
      setPositionMs(0)
    }
    setPlaying(true)
  }

  const toggle = (next?: AudioTrack) => {
    if (scope === null) {
      return
    }
    if (next && track?.materialId !== next.materialId) {
      setTrack(next)
      setPositionMs(0)
      setPlaying(true)
      return
    }
    if (!track) {
      return
    }
    setPlaying((value) => !value)
  }

  const seek = (ms: number) => {
    const element = audio.current
    const bounded = Math.max(0, ms)
    setPositionMs(bounded)
    if (element) {
      element.currentTime = bounded / 1000
      if (playing) {
        void element.play().catch(() => undefined)
      }
    }
  }

  const setSpeed = (next: number) => {
    setSpeedState(next)
    if (audio.current) {
      audio.current.playbackRate = next
    }
  }

  useEffect(() => {
    if (sleepMinutes === null || !playing) {
      return undefined
    }
    const timer = window.setTimeout(() => {
      setPlaying(false)
      setSleepMinutes(null)
    }, sleepMinutes * 60_000)
    return () => window.clearTimeout(timer)
  }, [sleepMinutes, playing])

  const setSleepTimer = (minutes: number | null) => setSleepMinutes(minutes)

  const download = () => {
    if (!track || downloading || scope === null) return
    const downloadScope = scope
    setDownloading(true)
    setDownloadError(false)
    void cacheAudio(downloadScope, track.src)
      .then((ok) => {
        if (activeScopeRef.current !== downloadScope) return
        setDownloading(false)
        if (ok) {
          setOffline('cached')
        } else {
          setDownloadError(true)
        }
      })
      .catch(() => {
        if (activeScopeRef.current !== downloadScope) return
        setDownloading(false)
        setDownloadError(true)
      })
  }

  const removeDownload = () => {
    if (!track || scope === null) return
    const removeScope = scope
    void removeCachedAudio(removeScope, track.src).then((ok) => {
      if (activeScopeRef.current !== removeScope) return
      if (!ok) {
        setDownloadError(true)
        return
      }
      setDownloadError(false)
      setOffline('not-cached')
      if (objectUrl.current !== null) {
        releaseObjectUrl()
        setResolvedSrc(track.src)
      }
    })
  }

  const stop = () => {
    const activeScope = scope
    stopPlayerForScopeChange()
    if (activeScope !== null) {
      savePersisted(activeScope, null)
    }
  }

  useEffect(() => {
    const element = audio.current
    if (!element || !track || loadedScope !== scope) {
      return
    }
    if (playing) {
      void element.play().catch(() => setPlaying(false))
    } else {
      element.pause()
    }
  }, [playing, track, scope, loadedScope])

  const inScope = scope !== null && loadedScope === scope
  const value: AudioPlayerValue = {
    track: inScope ? track : null,
    playing: inScope ? playing : false,
    positionMs: inScope ? positionMs : 0,
    durationMs: inScope ? durationMs : 0,
    speed: inScope ? speed : 1,
    sleepMinutes: inScope ? sleepMinutes : null,
    play,
    toggle,
    seek,
    setSpeed,
    setSleepTimer,
    offline: inScope ? offline : 'unknown',
    canDownload: offlineAudioSupported(),
    downloading: inScope ? downloading : false,
    downloadError: inScope ? downloadError : false,
    download,
    removeDownload,
    stop,
  }

  return (
    <AudioPlayerContext.Provider value={value}>
      {children}
      <audio
        ref={audio}
        src={inScope ? (resolvedSrc ?? track?.src) : undefined}
        preload="metadata"
        onLoadedMetadata={(event) => {
          setDurationMs(event.currentTarget.duration * 1000)
          event.currentTarget.currentTime = positionMs / 1000
        }}
        onTimeUpdate={(event) => setPositionMs(event.currentTarget.currentTime * 1000)}
        onEnded={() => setPlaying(false)}
      />
    </AudioPlayerContext.Provider>
  )
}

export function useAudioPlayer(): AudioPlayerValue {
  const value = useContext(AudioPlayerContext)
  if (!value) {
    throw new Error('useAudioPlayer must be used inside AudioPlayerProvider')
  }
  return value
}
