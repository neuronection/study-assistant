import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError, transcribeAudio } from '@/lib/api'

export type DictationStatus = 'idle' | 'recording' | 'transcribing'

export interface DictationError {
  kind: 'unsupported' | 'denied' | 'unassigned' | 'failed'
  detail?: string
}

const PREFERRED_MIME_TYPES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/ogg;codecs=opus',
  'audio/mp4',
]

const MAX_LEVEL = 1
const LEVEL_BOOST = 4
const LEVEL_DECAY = 0.85

function pickMimeType(): string | null {
  if (typeof MediaRecorder === 'undefined') {
    return null
  }
  for (const mimeType of PREFERRED_MIME_TYPES) {
    if (MediaRecorder.isTypeSupported(mimeType)) {
      return mimeType
    }
  }
  return null
}

export function useDictation(options: { onResult: (text: string) => void }) {
  const [status, setStatus] = useState<DictationStatus>('idle')
  const [seconds, setSeconds] = useState(0)
  const [error, setError] = useState<DictationError | null>(null)

  const optionsRef = useRef(options)
  optionsRef.current = options

  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<BlobPart[]>([])
  const audioContextRef = useRef<AudioContext | null>(null)
  const rafRef = useRef<number | null>(null)
  const timerRef = useRef<number | null>(null)
  const levelRef = useRef(0)

  const teardown = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
    audioContextRef.current?.close().catch(() => undefined)
    audioContextRef.current = null
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    recorderRef.current = null
    levelRef.current = 0
  }, [])

  const startMeter = useCallback((stream: MediaStream) => {
    const context = new AudioContext()
    audioContextRef.current = context
    const analyser = context.createAnalyser()
    analyser.fftSize = 512
    context.createMediaStreamSource(stream).connect(analyser)
    const buffer = new Uint8Array(analyser.fftSize)
    const tick = () => {
      analyser.getByteTimeDomainData(buffer)
      let sum = 0
      for (const value of buffer) {
        const centered = (value - 128) / 128
        sum += centered * centered
      }
      const rms = Math.sqrt(sum / buffer.length)
      levelRef.current = Math.min(
        MAX_LEVEL,
        Math.max(rms * LEVEL_BOOST, levelRef.current * LEVEL_DECAY),
      )
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
  }, [])

  const start = useCallback(async () => {
    if (status !== 'idle') {
      return
    }
    setError(null)
    if (
      typeof navigator === 'undefined' ||
      !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === 'undefined'
    ) {
      setError({ kind: 'unsupported' })
      return
    }
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (requestError) {
      const name = requestError instanceof DOMException ? requestError.name : ''
      setError(
        name === 'NotAllowedError' || name === 'SecurityError' || name === 'NotFoundError'
          ? { kind: 'denied' }
          : {
              kind: 'failed',
              detail:
                requestError instanceof Error
                  ? requestError.message
                  : String(requestError),
            },
      )
      return
    }
    const mimeType = pickMimeType()
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
    const chunks: BlobPart[] = []
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        chunks.push(event.data)
      }
    }
    recorderRef.current = recorder
    streamRef.current = stream
    chunksRef.current = chunks
    recorder.start(250)
    setSeconds(0)
    setStatus('recording')
    startMeter(stream)
    timerRef.current = window.setInterval(() => {
      setSeconds((current) => current + 1)
    }, 1000)
  }, [startMeter, status])

  const cancel = useCallback(() => {
    const recorder = recorderRef.current
    if (recorder !== null && recorder.state !== 'inactive') {
      recorder.onstop = null
      recorder.stop()
    }
    teardown()
    setSeconds(0)
    setStatus('idle')
  }, [teardown])

  const stop = useCallback(async () => {
    const recorder = recorderRef.current
    if (recorder === null || recorder.state === 'inactive') {
      return
    }
    const mimeType = recorder.mimeType || 'audio/webm'
    const chunks = chunksRef.current
    const stopped = new Promise<void>((resolve) => {
      recorder.onstop = () => resolve()
    })
    recorder.stop()
    await stopped
    teardown()
    setSeconds(0)
    setStatus('transcribing')
    try {
      const blob = new Blob(chunks, { type: mimeType })
      const result = await transcribeAudio(blob)
      setStatus('idle')
      optionsRef.current.onResult(result.text)
    } catch (transcribeError) {
      if (transcribeError instanceof ApiError && transcribeError.status === 409) {
        setError({ kind: 'unassigned' })
      } else {
        setError({
          kind: 'failed',
          detail:
            transcribeError instanceof Error
              ? transcribeError.message
              : String(transcribeError),
        })
      }
      setStatus('idle')
    }
  }, [teardown])

  const dismissError = useCallback(() => {
    setError(null)
  }, [])

  useEffect(
    () => () => {
      const recorder = recorderRef.current
      if (recorder !== null && recorder.state !== 'inactive') {
        recorder.onstop = null
        recorder.stop()
      }
      teardown()
    },
    [teardown],
  )

  return { status, seconds, error, levelRef, start, stop, cancel, dismissError }
}
