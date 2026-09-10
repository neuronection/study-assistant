import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { speakText } from '@/lib/api'

export const MAX_SPEECH_CHARS = 9000

export function stripMathForSpeech(markdown: string): string {
  let text = markdown
  text = text.replace(/```[\w-]*\n?/g, ' ')
  text = text.replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
  text = text.replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
  text = text.replace(/\$\$([\s\S]*?)\$\$/g, (_m, math: string) => mathToSpeech(math))
  text = text.replace(/\\\[([\s\S]*?)\\\]/g, (_m, math: string) => mathToSpeech(math))
  text = text.replace(/\\\(([\s\S]*?)\\\)/g, (_m, math: string) => mathToSpeech(math))
  text = text.replace(/\$([^$\n]+)\$/g, (_m, math: string) => mathToSpeech(math))
  text = text.replace(/^#{1,6}\s+/gm, '')
  text = text.replace(/(\*\*|__)(.*?)\1/g, '$2')
  text = text.replace(/(\*|_)(.*?)\1/g, '$2')
  text = text.replace(/^>\s?/gm, '')
  text = text.replace(/^[-*+]\s+\[([ xX])\]\s+/gm, (_m, done: string) =>
    done.trim() === '' ? 'unchecked item: ' : 'checked item: '
  )
  text = text.replace(/^\s*[-*+]\s+/gm, '')
  text = text.replace(/^\s*\d+\.\s+/gm, '')
  return text.replace(/\n{2,}/g, '. ').replace(/[ \t]+/g, ' ').trim()
}

export function mathToSpeech(math: string): string {
  let out = math
  out = out.replace(/\\sin(?![a-zA-Z])/g, ' sine ')
  out = out.replace(/\\cos(?![a-zA-Z])/g, ' cosine ')
  out = out.replace(/\\tan(?![a-zA-Z])/g, ' tangent ')
  out = out.replace(/\\ln(?![a-zA-Z])/g, ' natural log ')
  out = out.replace(/\\log(?![a-zA-Z])/g, ' log ')
  for (let i = 0; i < 4; i += 1) {
    out = out.replace(/\\frac\{([^{}]*)\}\{([^{}]*)\}/g, '$1 over $2')
    out = out.replace(/\\dfrac\{([^{}]*)\}\{([^{}]*)\}/g, '$1 over $2')
    out = out.replace(/\\sqrt\{([^{}]*)\}/g, 'square root of $1')
  }
  out = out.replace(/\\left|\\right/g, '')
  out = out.replace(/\\cdot|\\times/g, ' times ')
  out = out.replace(/\\pm/g, ' plus or minus ')
  out = out.replace(/\\infty/g, ' infinity ')
  out = out.replace(/\\int/g, ' integral ')
  out = out.replace(/\\sum/g, ' sum ')
  out = out.replace(/\\lim/g, ' limit ')
  out = out.replace(/\\to|\\rightarrow/g, ' to ')
  out = out.replace(/\\neq|\\ne/g, ' not equal ')
  out = out.replace(/\\approx/g, ' approximately ')
  out = out.replace(/\\leq/g, ' less than or equal to ')
  out = out.replace(/\\geq/g, ' greater than or equal to ')
  out = out.replace(/\\[a-zA-Z]+/g, '')
  out = out.replace(/[{}]/g, ' ')
  out = out.replace(/_/g, ' subscript ').replace(/\^/g, ' superscript ')
  out = out.replace(/\\\\/g, ' ')
  out = out.replace(/\s+/g, ' ')
  return out.trim()
}

export function chunkForSpeech(text: string, max = MAX_SPEECH_CHARS): string[] {
  if (text.length <= max) return [text]
  const chunks: string[] = []
  let rest = text
  while (rest.length > max) {
    let cut = rest.lastIndexOf('. ', max)
    if (cut < max / 2) cut = max
    chunks.push(rest.slice(0, cut + 1).trim())
    rest = rest.slice(cut + 1)
  }
  if (rest.trim()) chunks.push(rest.trim())
  return chunks
}

export function speechSynthesisAvailable(): boolean {
  if (typeof window === 'undefined') return false
  const synth = (
    window as unknown as {
      speechSynthesis?: {
        getVoices(): unknown[]
        addEventListener(t: string, l: () => void): void
        removeEventListener(t: string, l: () => void): void
      }
    }
  ).speechSynthesis
  if (!synth) return false
  return synth.getVoices().length > 0
}

export function useSpeechAvailable(): boolean {
  const [available, setAvailable] = useState(false)
  useEffect(() => {
    if (typeof window === 'undefined') return undefined
    const synth = (
      window as unknown as {
        speechSynthesis?: {
          getVoices(): unknown[]
          addEventListener(t: string, l: () => void): void
          removeEventListener(t: string, l: () => void): void
        }
      }
    ).speechSynthesis
    if (!synth) return undefined
    const update = () => setAvailable(synth.getVoices().length > 0)
    update()
    synth.addEventListener('voiceschanged', update)
    const settle = window.setTimeout(update, 1000)
    return () => {
      synth.removeEventListener('voiceschanged', update)
      window.clearTimeout(settle)
    }
  }, [])
  return available
}

export type ReadAloudEngine = 'provider' | 'browser'

export interface ReadAloudState {
  engine: ReadAloudEngine | null
  speaking: boolean
  active: boolean
  rate: number
  play: () => void
  stop: () => void
  cycleRate: () => void
}

const RATES = [1, 1.25, 1.5, 0.75] as const

export function useReadAloud(markdown: string): ReadAloudState {
  const [speaking, setSpeaking] = useState(false)
  const [active, setActive] = useState(false)
  const [rateIndex, setRateIndex] = useState(0)
  const [providerReady, setProviderReady] = useState(false)
  const browserAvailable = useSpeechAvailable()
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const stoppedRef = useRef(false)
  const rateRef = useRef(1)

  useEffect(() => {
    let cancelled = false
    void import('@/lib/api/settings').then(({ listTaskDefaults }) =>
      listTaskDefaults()
        .then((defaults) => {
          if (!cancelled) {
            setProviderReady(
              defaults.some((entry) => entry.requires === 'speech' && entry.model_id != null)
            )
          }
        })
        .catch(() => {
          if (!cancelled) setProviderReady(false)
        })
    )
    return () => {
      cancelled = true
    }
  }, [])

  const engine: ReadAloudEngine | null = providerReady
    ? 'provider'
    : browserAvailable
      ? 'browser'
      : null

  const stop = useCallback(() => {
    stoppedRef.current = true
    if (audioRef.current) {
      audioRef.current.pause()
      if (audioRef.current.src.startsWith('blob:')) {
        URL.revokeObjectURL(audioRef.current.src)
      }
      audioRef.current = null
    }
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel()
    }
    setSpeaking(false)
    setActive(false)
  }, [])

  useEffect(() => stop, [stop])

  const playBrowser = useCallback(
    (text: string, rate: number) => {
      const synth = window.speechSynthesis
      synth.cancel()
      stoppedRef.current = false
      const chunks = chunkForSpeech(text)
      const speakChunk = (index: number) => {
        if (stoppedRef.current || index >= chunks.length) {
          if (!stoppedRef.current) {
            setSpeaking(false)
            setActive(false)
          }
          return
        }
        const utterance = new SpeechSynthesisUtterance(chunks[index])
        utterance.rate = rate
        utterance.onend = () => speakChunk(index + 1)
        utterance.onerror = () => {
          if (!stoppedRef.current) {
            setSpeaking(false)
            setActive(false)
          }
        }
        synth.speak(utterance)
      }
      setSpeaking(true)
      setActive(true)
      speakChunk(0)
    },
    []
  )

  const playProvider = useCallback(async (text: string) => {
    stoppedRef.current = false
    setSpeaking(true)
    setActive(true)
    try {
      const chunks = chunkForSpeech(text)
      for (const chunk of chunks) {
        if (stoppedRef.current) return
        const blob = await speakText(chunk)
        if (stoppedRef.current) return
        await new Promise<void>((resolve) => {
          const audio = new Audio(URL.createObjectURL(blob))
          audio.playbackRate = rateRef.current
          audioRef.current = audio
          audio.onended = () => resolve()
          audio.onerror = () => resolve()
          void audio.play()
        })
      }
      if (!stoppedRef.current) {
        setSpeaking(false)
        setActive(false)
      }
    } catch {
      if (!stoppedRef.current) {
        setSpeaking(false)
        setActive(false)
      }
    }
  }, [])

  const play = useCallback(() => {
    if (active) {
      stop()
      return
    }
    const text = stripMathForSpeech(markdown)
    if (!text) return
    rateRef.current = RATES[rateIndex]
    if (providerReady) {
      void playProvider(text)
    } else if (browserAvailable) {
      playBrowser(text, RATES[rateIndex])
    }
  }, [
    active,
    stop,
    markdown,
    providerReady,
    browserAvailable,
    playProvider,
    playBrowser,
    rateIndex,
  ])

  const cycleRate = useCallback(() => {
    setRateIndex((index) => {
      const next = (index + 1) % RATES.length
      rateRef.current = RATES[next]
      return next
    })
  }, [])

  return useMemo(
    () => ({
      engine,
      speaking,
      active,
      rate: RATES[rateIndex],
      play,
      stop,
      cycleRate,
    }),
    [engine, speaking, active, rateIndex, play, stop, cycleRate]
  )
}
