import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { AudioLines, Loader2, Pause, Play, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { createNarration, getArtifact, retryArtifact, type Artifact } from '@/lib/api'
import { useCloseFloatings } from '@/lib/ui-overlays'

export function NarrateDialog({
  courseId,
  nodeId,
  onClose,
}: {
  courseId: string
  nodeId: string | null
  onClose: () => void
}) {
  useCloseFloatings()
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [title, setTitle] = useState('')
  const [length, setLength] = useState(5)
  const [artifact, setArtifact] = useState<Artifact | null>(null)
  const [speaking, setSpeaking] = useState(false)
  const [voiceError, setVoiceError] = useState<string | null>(null)
  const create = useMutation({
    mutationFn: () =>
      createNarration({
        course_id: courseId,
        node_id: nodeId,
        title: title.trim() || null,
        length_minutes: length,
        regenerate: true,
      }),
    onSuccess: (created) => {
      setArtifact(created)
      void queryClient.invalidateQueries({ queryKey: ['artifacts', courseId] })
    },
  })
  const polled = useQuery({
    queryKey: ['artifact-render', artifact?.id],
    queryFn: () => getArtifact(artifact!.id),
    enabled: artifact !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'ready' || status === 'failed' ? false : 2000
    },
  })
  const current = polled.data ?? artifact
  const retry = useMutation({
    mutationFn: () => retryArtifact(current!.id),
    onSuccess: setArtifact,
  })
  useEffect(() => () => window.speechSynthesis?.cancel(), [])
  const speak = (text: string) => {
    if (!('speechSynthesis' in window) || !text.trim()) {
      setVoiceError(t('narrate.noBrowserVoice'))
      return
    }
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.onend = () => setSpeaking(false)
    utterance.onerror = () => {
      setSpeaking(false)
      setVoiceError(t('narrate.browserVoiceFailed'))
    }
    setSpeaking(true)
    setVoiceError(null)
    window.speechSynthesis.speak(utterance)
  }
  const stopSpeaking = () => {
    window.speechSynthesis?.cancel()
    setSpeaking(false)
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={t('narrate.title')}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose()
        }
      }}
    >
      <div className="bg-surface border-border w-full max-w-md rounded-lg border shadow-[var(--as-shadow-3)]">
        <header className="border-border flex items-center justify-between border-b px-4 py-2">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <AudioLines className="text-primary size-4" aria-hidden />
            {t('narrate.title')}
          </h2>
          <button
            type="button"
            aria-label={t('chat.close')}
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground rounded p-1"
          >
            <X className="size-4" aria-hidden />
          </button>
        </header>
        <div className="space-y-3 p-4">
          {current === null ? (
            <>
              <p className="text-muted-foreground text-xs">{t('narrate.body')}</p>
              <label className="block space-y-1 text-xs">
                <span className="text-muted-foreground">{t('narrate.titleLabel')}</span>
                <input
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  placeholder={t('narrate.titlePlaceholder')}
                  className="bg-surface border-border w-full rounded-md border px-2 py-1.5 text-sm"
                />
              </label>
              <label className="block space-y-1 text-xs">
                <span className="text-muted-foreground">{t('narrate.length')}</span>
                <select
                  value={length}
                  onChange={(event) => setLength(Number(event.target.value))}
                  className="bg-surface border-border w-full rounded-md border px-2 py-1.5 text-sm"
                >
                  <option value={5}>{t('narrate.minutes', { count: 5 })}</option>
                  <option value={10}>{t('narrate.minutes', { count: 10 })}</option>
                  <option value={20}>{t('narrate.minutes', { count: 20 })}</option>
                </select>
              </label>
              <p className="text-muted-foreground text-[11px]">{t('narrate.voiceHint')}</p>
            </>
          ) : (
            <div className="space-y-2">
              <p className="text-sm font-medium">{current.title}</p>
              <p className="text-muted-foreground text-xs">
                {current.status === 'ready'
                  ? t('narrate.ready', { seconds: Math.round(current.spec.script?.length ?? 0) })
                  : current.status === 'failed'
                    ? t('narrate.failed')
                    : t('narrate.pending')}
              </p>
              {current.status === 'pending' || current.status === 'rendering' ? (
                <Spinner />
              ) : null}
              {current.status === 'ready' && current.output_material_id ? (
                <Button asChild size="sm">
                  <Link to="/library/$materialId" params={{ materialId: current.output_material_id }}>
                    {t('narrate.openAudio')}
                  </Link>
                </Button>
              ) : null}
              {current.status === 'ready' && current.spec.renderer === 'browser' && current.spec.script ? (
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        speaking ? stopSpeaking() : speak(current.spec.script ?? '')
                      }
                    >
                      {speaking ? <Pause className="size-3.5" aria-hidden /> : <Play className="size-3.5" aria-hidden />}
                      {speaking ? t('narrate.stopVoice') : t('narrate.playBrowser')}
                    </Button>
                    <span className="bg-subtle text-muted-foreground rounded-full px-2 py-0.5 text-[10px]">
                      {t('narrate.deviceVoice')}
                    </span>
                  </div>
                  {(current.spec.chapters ?? []).length > 0 ? (
                    <ul className="space-y-1">
                      {(current.spec.chapters ?? []).map((chapter, index) => (
                        <li key={`${chapter.title}-${index}`}>
                          <button
                            type="button"
                            className="hover:bg-subtle w-full rounded px-2 py-1 text-left text-xs"
                            onClick={() => speak(chapter.script ?? '')}
                          >
                            {chapter.title}
                          </button>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              ) : null}
              {voiceError ? <p className="text-danger text-xs">{voiceError}</p> : null}
              {current.status === 'failed' ? (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={retry.isPending}
                  onClick={() => retry.mutate()}
                >
                  {retry.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
                  {t('narrate.retry')}
                </Button>
              ) : null}
            </div>
          )}
          {create.isError ? (
            <p className="text-danger text-xs" role="alert">
              {(create.error as Error).message}
            </p>
          ) : null}
        </div>
        <footer className="border-border flex items-center justify-end gap-2 border-t px-4 py-2">
          <Button variant="ghost" size="sm" onClick={onClose}>
            {t('common.close')}
          </Button>
          {current === null ? (
            <Button size="sm" disabled={create.isPending} onClick={() => create.mutate()}>
              {create.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
              {t('narrate.create')}
            </Button>
          ) : null}
        </footer>
      </div>
    </div>
  )
}

