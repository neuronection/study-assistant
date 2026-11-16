import { useQuery } from '@tanstack/react-query'
import { AudioLines, Mic, Play, Volume2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from '@tanstack/react-router'
import { useEffect, useState } from 'react'

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { listTasks } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { storageKeys } from '@/lib/constants'

export function VoiceAudioCard() {
  const { t } = useTranslation()
  const [voiceTest, setVoiceTest] = useState<string | null>(null)
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([])
  const [audioInputs, setAudioInputs] = useState(0)
  const [speechRate, setSpeechRate] = useState(() => {
    try {
      return Number(window.localStorage.getItem(storageKeys.speechRate)) || 1
    } catch {
      return 1
    }
  })
  const [voice, setVoice] = useState(() => {
    try {
      return window.localStorage.getItem(storageKeys.browserVoice) ?? ''
    } catch {
      return ''
    }
  })
  const tasks = useQuery({ queryKey: ['tasks'], queryFn: listTasks })
  const stt = (tasks.data ?? []).find((task) => task.requires === 'stt')
  const tts = (tasks.data ?? []).find((task) => task.requires === 'tts')
  const browserSpeech =
    typeof window !== 'undefined' && 'speechSynthesis' in window
  const microphone =
    typeof navigator !== 'undefined' && Boolean(navigator.mediaDevices?.getUserMedia)
  useEffect(() => {
    if (!browserSpeech) return undefined
    const synth = window.speechSynthesis
    const update = () => setVoices(synth.getVoices())
    update()
    synth.addEventListener('voiceschanged', update)
    return () => synth.removeEventListener('voiceschanged', update)
  }, [browserSpeech])

  useEffect(() => {
    if (!microphone || navigator.mediaDevices.enumerateDevices === undefined) return undefined
    let cancelled = false
    void navigator.mediaDevices
      .enumerateDevices()
      .then((devices) => {
        if (!cancelled) {
          setAudioInputs(devices.filter((device) => device.kind === 'audioinput').length)
        }
      })
      .catch(() => {
        if (!cancelled) setAudioInputs(0)
      })
    return () => {
      cancelled = true
    }
  }, [microphone])

  const chooseVoice = (next: string) => {
    setVoice(next)
    try {
      window.localStorage.setItem(storageKeys.browserVoice, next)
    } catch {
      return
    }
  }

  const label = (task: typeof stt) =>
    task?.model_label ?? task?.fallback_model_label ?? task?.default_model_label ?? null

  const rows = [
    {
      icon: Mic,
      label: t('settings.voiceStt'),
      value: label(stt) ?? t('settings.voiceUnassigned'),
      ok: Boolean(label(stt)),
    },
    {
      icon: Volume2,
      label: t('settings.voiceTts'),
      value: label(tts) ?? t('settings.voiceDeviceFallback'),
      ok: Boolean(label(tts)),
    },
    {
      icon: AudioLines,
      label: t('settings.voiceBrowser'),
      value: browserSpeech ? t('settings.voiceAvailable') : t('settings.voiceUnavailable'),
      ok: browserSpeech,
    },
    {
      icon: Mic,
      label: t('settings.voiceMicrophone'),
      value: microphone ? t('settings.voiceAvailable') : t('settings.voiceUnavailable'),
      ok: microphone,
    },
  ]

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">{t('settings.voiceTitle')}</CardTitle>
        <CardDescription>{t('settings.voiceDescription')}</CardDescription>
      </CardHeader>
      <CardContent className="max-w-md space-y-2">
        {rows.map(({ icon: Icon, label: rowLabel, value, ok }) => (
          <div key={rowLabel} className="flex items-center gap-2 text-xs">
            <Icon className="text-muted-foreground size-3.5 shrink-0" aria-hidden />
            <span className="min-w-0 flex-1">{rowLabel}</span>
            <span
              className={ok ? 'text-success' : 'text-muted-foreground'}
              aria-label={`${rowLabel}: ${value}`}
            >
              {value}
            </span>
          </div>
        ))}
        {browserSpeech && voices.length > 0 ? (
          <label className="flex items-center gap-2 text-xs">
            <span className="min-w-0 flex-1">{t('settings.voicePicker')}</span>
            <select
              value={voice}
              onChange={(event) => chooseVoice(event.target.value)}
              aria-label={t('settings.voicePicker')}
              className="bg-surface border-border max-w-52 rounded-md border px-2 py-1 text-xs"
            >
              <option value="">{t('settings.voicePickerDefault')}</option>
              {voices.map((entry) => (
                <option key={entry.voiceURI} value={entry.voiceURI}>
                  {entry.name} ({entry.lang})
                </option>
              ))}
            </select>
          </label>
        ) : null}
        {microphone ? (
          <p className="text-muted-foreground text-[11px]">
            {t('settings.voiceInputCount', { count: audioInputs })}
          </p>
        ) : null}
        <label className="flex items-center gap-2 text-xs">
          <span className="min-w-0 flex-1">{t('settings.voiceSpeed')}</span>
          <select
            value={speechRate}
            onChange={(event) => {
              const next = Number(event.target.value)
              setSpeechRate(next)
              try {
                window.localStorage.setItem(storageKeys.speechRate, String(next))
              } catch {
                return
              }
            }}
            aria-label={t('settings.voiceSpeed')}
            className="bg-surface border-border rounded-md border px-2 py-1 text-xs"
          >
            {[0.75, 1, 1.25, 1.5, 2].map((rate) => (
              <option key={rate} value={rate}>
                {rate}×
              </option>
            ))}
          </select>
        </label>
        <p className="text-muted-foreground text-[11px]">{t('settings.voiceHint')}</p>
        <div className="flex flex-wrap items-center gap-2">
          <Link
            to="/settings"
            search={{ tab: 'ai', section: 'tasks' }}
            className="text-primary text-xs underline"
          >
            {t('settings.voiceAssign')}
          </Link>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
                setVoiceTest(t('settings.voiceTestUnsupported'))
                return
              }
              window.speechSynthesis.cancel()
              const utterance = new SpeechSynthesisUtterance(
                t('settings.voiceTestPhrase'),
              )
              const selected = window.speechSynthesis
                .getVoices()
                .find((entry) => entry.voiceURI === voice)
              if (selected !== undefined) utterance.voice = selected
              utterance.onend = () => setVoiceTest(t('settings.voiceTestDone'))
              utterance.onerror = () => setVoiceTest(t('settings.voiceTestFailed'))
              setVoiceTest(t('settings.voiceTestRunning'))
              window.speechSynthesis.speak(utterance)
            }}
          >
            <Play className="size-3.5" aria-hidden />
            {t('settings.voiceTest')}
          </Button>
        </div>
        {voiceTest ? <p className="text-muted-foreground text-[11px]">{voiceTest}</p> : null}
      </CardContent>
    </Card>
  )
}
