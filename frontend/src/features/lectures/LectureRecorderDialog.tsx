import { Link } from '@tanstack/react-router'
import { AudioLines, Square, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import {
  cancelLecture,
  createLecture,
  finalizeLecture,
  getLecture,
  patchLecture,
  uploadLectureChunk,
  type Lecture,
} from '@/lib/api'
import { JournalNonRetryableError, isLectureOp, offlineJournal } from '@/lib/offline/journal'
import { clearLectureDraft, loadLectureDraft, saveLectureDraft, type LectureDraft } from './lectureDraft'

type Phase = 'setup' | 'recover' | 'recording' | 'paused' | 'uploading' | 'ready' | 'error'

function preferredMime(): string {
  if (typeof MediaRecorder === 'undefined') {
    return 'audio/webm'
  }
  for (const candidate of [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/mp4',
    'audio/ogg;codecs=opus',
  ]) {
    if (MediaRecorder.isTypeSupported(candidate)) {
      return candidate
    }
  }
  return 'audio/webm'
}

async function sha256(buffer: ArrayBuffer): Promise<string> {
  if (!crypto.subtle) {
    throw new Error('SHA-256 is unavailable in this browser')
  }
  const digest = await crypto.subtle.digest('SHA-256', buffer)
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('')
}

export function LectureRecorderDialog({
  courseId,
  nodeId,
  onClose,
  onCreated,
}: {
  courseId: string
  nodeId: string | null
  onClose: () => void
  onCreated: () => void
}) {
  const { t } = useTranslation()
  const [phase, setPhase] = useState<Phase>('setup')
  const [consent, setConsent] = useState(false)
  const [title, setTitle] = useState(t('lectures.defaultTitle'))
  const [retention, setRetention] = useState('audio_and_text')
  const [error, setError] = useState<string | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const [chunkCount, setChunkCount] = useState(0)
  const [materialId, setMaterialId] = useState<string | null>(null)
  const [recovery, setRecovery] = useState<LectureDraft | null>(null)
  const sessionRef = useRef<Lecture | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const nextSeq = useRef(0)
  const drainPromise = useRef<Promise<void> | null>(null)
  const cancelled = useRef(false)
  const draftRef = useRef<LectureDraft | null>(null)

  const drain = async (): Promise<void> => {
    if (drainPromise.current) {
      return drainPromise.current
    }
    const work = (async () => {
      for (;;) {
        const pending = offlineJournal
          .getSnapshot()
          .ops.filter(
            (op) =>
              isLectureOp(op) &&
              (sessionRef.current === null ||
                op.payload.sessionId === sessionRef.current.id),
          )
        if (pending.length === 0) {
          return
        }
        const done = await offlineJournal.drain('lecture', async (op, blob) => {
          if (!isLectureOp(op)) {
            return
          }
          if (!blob) {
            throw new JournalNonRetryableError('The saved audio part is missing.')
          }
          const buffer = await blob.arrayBuffer()
          await uploadLectureChunk(
            op.payload.sessionId,
            op.payload.seq,
            buffer,
            op.payload.sha256,
          )
          setChunkCount((count) => count + 1)
        })
        if (done === 0) {
          return
        }
      }
    })()
    drainPromise.current = work
    try {
      await work
    } catch (err) {
      setError((err as Error).message)
      setPhase('error')
    } finally {
      drainPromise.current = null
    }
  }

  const persistChunk = async (blob: Blob) => {
    const session = sessionRef.current
    if (!session || cancelled.current) {
      return
    }
    try {
      const buffer = await blob.arrayBuffer()
      const digest = await sha256(buffer)
      await offlineJournal.enqueueLectureChunk(
        session.id,
        nextSeq.current,
        blob,
        digest,
        session.mime,
      )
      nextSeq.current += 1
      if (draftRef.current) {
        draftRef.current = {
          ...draftRef.current,
          nextSeq: nextSeq.current,
          updatedAt: Date.now(),
        }
        saveLectureDraft(draftRef.current)
      }
      await drain()
    } catch (err) {
      setError((err as Error).message)
      setPhase('error')
    }
  }

  const stopTracks = () => {
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    recorderRef.current = null
  }

  useEffect(() => {
    if (phase !== 'recording') {
      return undefined
    }
    const timer = window.setInterval(() => setElapsed((value) => value + 1), 1000)
    return () => window.clearInterval(timer)
  }, [phase])

  useEffect(() => () => stopTracks(), [])

  useEffect(() => {
    const draft = loadLectureDraft()
    if (!draft) {
      return
    }
    setRecovery(draft)
    setPhase('recover')
  }, [])

  const start = async () => {
    if (!consent) {
      return
    }
    cancelled.current = false
    nextSeq.current = 0
    setError(null)
    try {
      const mime = preferredMime()
      const session = await createLecture({
        course_id: courseId,
        node_id: nodeId,
        title,
        consent_confirmed: true,
        retention,
        mime,
      })
      sessionRef.current = session
      draftRef.current = {
        sessionId: session.id,
        courseId,
        nodeId,
        title,
        mime,
        retention,
        nextSeq: 0,
        updatedAt: Date.now(),
      }
      saveLectureDraft(draftRef.current)
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error(t('lectures.noMicrophone'))
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      const recorder = new MediaRecorder(stream, { mimeType: mime })
      recorderRef.current = recorder
      recorder.ondataavailable = (event) => {
        if (event.data.size === 0) {
          return
        }
        void persistChunk(event.data)
      }
      recorder.onstop = async () => {
        if (cancelled.current) {
          return
        }
        setPhase('uploading')
        await drain()
        try {
          const sessionNow = sessionRef.current
          if (!sessionNow || cancelled.current) {
            return
          }
          const result = await finalizeLecture(sessionNow.id)
          setMaterialId(result.material_id)
          setPhase('ready')
          clearLectureDraft()
          onCreated()
        } catch (err) {
          setError((err as Error).message)
          setPhase('error')
        }
      }
      recorder.onerror = () => {
        setError(t('lectures.recorderError'))
        setPhase('error')
      }
      recorder.start(15_000)
      setPhase('recording')
    } catch (err) {
      setError((err as Error).message)
      setPhase('error')
    }
  }

  const pause = async () => {
    recorderRef.current?.pause()
    setPhase('paused')
    if (sessionRef.current) {
      await patchLecture(sessionRef.current.id, { status: 'paused' }).catch(() => undefined)
    }
  }

  const resume = async () => {
    recorderRef.current?.resume()
    setPhase('recording')
    if (sessionRef.current) {
      await patchLecture(sessionRef.current.id, { status: 'recording' }).catch(() => undefined)
    }
  }

  const stop = () => {
    recorderRef.current?.stop()
    stopTracks()
  }

  const cancel = async () => {
    if (phase === 'ready') {
      onClose()
      return
    }
    cancelled.current = true
    recorderRef.current?.stop()
    stopTracks()
    if (sessionRef.current) {
      await cancelLecture(sessionRef.current.id).catch(() => undefined)
      for (const op of offlineJournal.getSnapshot().ops) {
        if (isLectureOp(op) && op.payload.sessionId === sessionRef.current.id) {
          await offlineJournal.remove(op.id)
        }
      }
    }
    clearLectureDraft()
    onClose()
  }

  const resumeUpload = async () => {
    if (!recovery) {
      return
    }
    setPhase('uploading')
    setError(null)
    try {
      const row = await getLecture(recovery.sessionId)
      sessionRef.current = row
      draftRef.current = recovery
      nextSeq.current = recovery.nextSeq
      await drain()
      const result = await finalizeLecture(row.id)
      setMaterialId(result.material_id)
      setPhase('ready')
      clearLectureDraft()
      onCreated()
    } catch (err) {
      setError((err as Error).message)
      setPhase('error')
    }
  }

  const discardRecovery = async () => {
    if (!recovery) {
      return
    }
    await cancelLecture(recovery.sessionId).catch(() => undefined)
    for (const op of offlineJournal.getSnapshot().ops) {
      if (isLectureOp(op) && op.payload.sessionId === recovery.sessionId) {
        await offlineJournal.remove(op.id)
      }
    }
    clearLectureDraft()
    setRecovery(null)
    setPhase('setup')
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={t('lectures.recordTitle')}
    >
      <div className="bg-surface border-border w-full max-w-md rounded-lg border shadow-[var(--as-shadow-3)]">
        <header className="border-border flex items-center justify-between border-b px-4 py-2">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <AudioLines className="text-primary size-4" aria-hidden />
            {t('lectures.recordTitle')}
          </h2>
          <button
            type="button"
            aria-label={t('chat.close')}
            onClick={() => void cancel()}
            className="text-muted-foreground hover:text-foreground rounded p-1"
          >
            <X className="size-4" aria-hidden />
          </button>
        </header>
        <div className="space-y-3 p-4">
          {phase === 'recover' && recovery ? (
            <div className="space-y-2">
              <p className="text-sm font-medium">{t('lectures.recoverTitle')}</p>
              <p className="text-muted-foreground text-xs">
                {t('lectures.recoverBody', {
                  title: recovery.title,
                  count: recovery.nextSeq,
                })}
              </p>
              <div className="flex flex-wrap gap-1">
                <Button size="sm" onClick={() => void resumeUpload()}>
                  {t('lectures.resumeUpload')}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => void discardRecovery()}>
                  {t('lectures.discard')}
                </Button>
              </div>
            </div>
          ) : phase === 'setup' ? (
            <>
              <p className="text-muted-foreground text-xs">{t('lectures.consentBody')}</p>
              <label className="flex items-start gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={consent}
                  onChange={(event) => setConsent(event.target.checked)}
                  className="mt-0.5"
                />
                {t('lectures.consentCheck')}
              </label>
              <label className="block space-y-1 text-xs">
                <span className="text-muted-foreground">{t('lectures.titleLabel')}</span>
                <input
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  className="bg-surface border-border w-full rounded-md border px-2 py-1.5 text-sm"
                />
              </label>
              <label className="block space-y-1 text-xs">
                <span className="text-muted-foreground">{t('lectures.retention')}</span>
                <select
                  value={retention}
                  onChange={(event) => setRetention(event.target.value)}
                  className="bg-surface border-border w-full rounded-md border px-2 py-1.5 text-sm"
                >
                  <option value="audio_and_text">{t('lectures.retentionAudio')}</option>
                  <option value="text_only">{t('lectures.retentionText')}</option>
                </select>
              </label>
              <p className="text-muted-foreground text-[11px]">{t('lectures.foregroundHint')}</p>
            </>
          ) : (
            <div className="space-y-2">
              <p className="text-sm font-medium">{title}</p>
              <p className="text-muted-foreground text-xs">
                {phase === 'recording'
                  ? t('lectures.recordingAt', { time: formatElapsed(elapsed) })
                  : phase === 'paused'
                    ? t('lectures.pausedAt', { time: formatElapsed(elapsed) })
                    : phase === 'uploading'
                      ? t('lectures.finalizing')
                      : phase === 'ready'
                        ? t('lectures.ready')
                        : error}
              </p>
              {phase === 'recording' || phase === 'paused' || phase === 'uploading' ? (
                <p className="text-muted-foreground text-[11px]">
                  {t('lectures.chunks', { count: chunkCount })}
                </p>
              ) : null}
              {(phase === 'recording' || phase === 'paused') && (
                <div className="flex flex-wrap gap-1">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => (phase === 'paused' ? void resume() : void pause())}
                  >
                    {phase === 'paused' ? t('lectures.resume') : t('lectures.pause')}
                  </Button>
                  <Button size="sm" variant="destructive" onClick={stop}>
                    <Square className="size-3.5" aria-hidden />
                    {t('lectures.stop')}
                  </Button>
                </div>
              )}
              {phase === 'uploading' ? <Spinner /> : null}
              {phase === 'ready' && materialId ? (
                <Button asChild size="sm">
                  <Link to="/library/$materialId" params={{ materialId }}>
                    {t('lectures.openRecording')}
                  </Link>
                </Button>
              ) : null}
              {phase === 'error' ? (
                <p className="text-danger text-xs" role="alert">
                  {error}
                </p>
              ) : null}
            </div>
          )}
          {phase === 'setup' && error ? (
            <p className="text-danger text-xs" role="alert">
              {error}
            </p>
          ) : null}
        </div>
        <footer className="border-border flex items-center justify-end gap-2 border-t px-4 py-2">
          <Button variant="ghost" size="sm" onClick={() => void cancel()}>
            {t('common.cancel')}
          </Button>
          {phase === 'setup' ? (
            <Button size="sm" disabled={!consent || !title.trim()} onClick={() => void start()}>
              {t('lectures.start')}
            </Button>
          ) : null}
        </footer>
      </div>
    </div>
  )
}

function formatElapsed(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}
