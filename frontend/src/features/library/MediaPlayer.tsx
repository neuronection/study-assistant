import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarPlus, Combine, Headphones, Layers, MapPin, Pause, Pencil, Play, Scissors, Sparkles, StickyNote, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useAudioPlayer } from '@/lib/audio-player'

import { Button } from '@/components/ui/button'
import { GenerateDialog } from '@/features/ai/GenerateDialog'
import { Spinner } from '@/components/ui/spinner'
import {
  blobUrl,
  createFlashcard,
  createMaterialAnchor,
  createNote,
  createPlanItem,
  deleteAnchor,
  getMaterialMedia,
  listMaterialAnchors,
  mergeMediaSegments,
  patchMediaSegment,
  recordActivation,
  splitMediaSegment,
  type MediaSegment,
} from '@/lib/api'
import { cn } from '@/lib/utils'

function stamp(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000))
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

export function MediaPlayer({ materialId }: { materialId: string }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const media = useQuery({
    queryKey: ['material-media', materialId],
    queryFn: () => getMaterialMedia(materialId),
  })
  const player = useRef<HTMLMediaElement>(null)
  const [localMs, setLocalMs] = useState(0)
  const global = useAudioPlayer()
  const [search, setSearch] = useState('')
  const [speed, setSpeed] = useState(1)
  const [noteOpen, setNoteOpen] = useState(false)
  const [note, setNote] = useState('')
  const [editing, setEditing] = useState<string | null>(null)
  const [editingText, setEditingText] = useState('')
  const [editingSpeaker, setEditingSpeaker] = useState('')
  const [momentAction, setMomentAction] = useState<string | null>(null)
  const [selectedMoments, setSelectedMoments] = useState<Set<string>>(new Set())
  const [studyOpen, setStudyOpen] = useState(false)
  const anchors = useQuery({
    queryKey: ['material-anchors', materialId],
    queryFn: () => listMaterialAnchors(materialId),
  })
  const moments = (anchors.data ?? []).filter((anchor) => anchor.anchor_kind === 'time_range')
  const addMoment = useMutation({
    mutationFn: () =>
      createMaterialAnchor(materialId, {
        anchor_kind: 'time_range',
        payload: {
          start_ms: Math.max(0, Math.floor(currentMs)),
          end_ms: Math.min(
            media.data?.duration_ms ?? Math.floor(currentMs) + 10_000,
            Math.floor(currentMs) + 10_000,
          ),
        },
        quote: active?.text ?? null,
        note_md: note.trim() || null,
        color: 'primary',
        source: 'user',
      }),
    onSuccess: async () => {
      setNote('')
      setNoteOpen(false)
      await queryClient.invalidateQueries({ queryKey: ['material-anchors', materialId] })
    },
  })
  const editSegment = useMutation({
    mutationFn: (segmentId: string) =>
      patchMediaSegment(segmentId, {
        text: editingText.trim(),
        speaker: editingSpeaker.trim() || null,
      }),
    onSuccess: async () => {
      setEditing(null)
      setEditingText('')
      setEditingSpeaker('')
      await queryClient.invalidateQueries({ queryKey: ['material-media', materialId] })
      await queryClient.invalidateQueries({ queryKey: ['material', materialId] })
    },
  })
  const split = useMutation({
    mutationFn: (segmentId: string) => splitMediaSegment(segmentId, currentMs),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['material-media', materialId] })
      await queryClient.invalidateQueries({ queryKey: ['material', materialId] })
    },
  })
  const merge = useMutation({
    mutationFn: ({ first, second }: { first: string; second: string }) =>
      mergeMediaSegments(first, second),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['material-media', materialId] })
      await queryClient.invalidateQueries({ queryKey: ['material', materialId] })
    },
  })
  const createMomentCard = useMutation({
    mutationFn: ({ quote, note }: { quote: string; note: string }) =>
      createFlashcard({
        kind: 'card_basic',
        front_md: quote || note || t('library.momentUntitled'),
        back_md: note || quote || t('library.momentUntitled'),
        course_id: media.data?.course_id ?? '',
      }),
    onSuccess: () => {
      void recordActivation('highlight_to_card', { surface: 'lecture_moment' })
      setMomentAction(t('library.momentCardCreated'))
    },
    onError: (err: Error) => setMomentAction(err.message),
  })

  const createMomentCards = useMutation({
    mutationFn: async (moments: { quote: string; note: string }[]) => {
      await Promise.all(
        moments.map((moment) =>
          createFlashcard({
            kind: 'card_basic',
            front_md: moment.quote || moment.note || t('library.momentUntitled'),
            back_md: moment.note || moment.quote || t('library.momentUntitled'),
            course_id: media.data?.course_id ?? '',
          })
        )
      )
      return moments.length
    },
    onSuccess: (count) => {
      void recordActivation('highlight_to_card', {
        surface: 'lecture_moment_batch',
        value: count,
      })
      setSelectedMoments(new Set())
      setMomentAction(t('library.momentCardsCreated', { count }))
    },
    onError: (err: Error) => setMomentAction(err.message),
  })

  const createMomentNote = useMutation({
    mutationFn: async ({ quote, note, time }: { quote: string; note: string; time: number }) =>
      createNote({
        title: t('library.momentNoteTitle', { time: stamp(time) }),
        body_md: [quote, note].filter(Boolean).join('\n\n'),
        course_id: media.data?.course_id ?? '',
      }),
    onSuccess: (note) => setMomentAction(t('library.momentNoteCreated', { id: note.id })),
    onError: (err: Error) => setMomentAction(err.message),
  })

  const createMomentPlan = useMutation({
    mutationFn: async ({ note, time }: { quote: string; note: string; time: number }) =>
      createPlanItem(media.data?.course_id ?? '', {
        title: note || t('library.momentPlanTitle', { time: stamp(time) }),
        kind: 'study',
        due_date: new Date().toISOString().slice(0, 10),
        node_id: null,
      }),
    onSuccess: () => setMomentAction(t('library.momentPlanCreated')),
    onError: (err: Error) => setMomentAction(err.message),
  })

  const removeMoment = useMutation({
    mutationFn: (anchorId: string) => deleteAnchor(anchorId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['material-anchors', materialId] })
    },
  })
  const segments = useMemo(() => media.data?.segments ?? [], [media.data?.segments])
  const visible = useMemo(() => {
    const query = search.trim().toLowerCase()
    return query
      ? segments.filter((segment) => segment.text.toLowerCase().includes(query))
      : segments
  }, [segments, search])
  useEffect(() => {
    if (!media.data?.blob_sha) {
      return
    }
    const raw = new URLSearchParams(window.location.search).get('t')
    const seconds = Number(raw)
    if (!Number.isFinite(seconds) || seconds <= 0) {
      return
    }
    if (media.data.mime?.startsWith('video')) {
      if (player.current) {
        player.current.currentTime = seconds
      }
      return
    }
    global.play({
      materialId,
      title: media.data.title ?? media.data.material_id,
      src: blobUrl(media.data.blob_sha),
    })
    const timer = window.setTimeout(() => global.seek(seconds * 1000), 100)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [media.data?.blob_sha])

  if (media.isLoading) {
    return <Spinner />
  }
  if (!media.data?.blob_sha) {
    return null
  }

  const seek = (segment: MediaSegment) => {
    if (!isVideo) {
      global.play(audioTrack)
      global.seek(segment.start_ms)
    } else if (player.current) {
      player.current.currentTime = segment.start_ms / 1000
      void player.current.play()
    }
    const url = new URL(window.location.href)
    url.searchParams.set('t', String(Math.floor(segment.start_ms / 1000)))
    window.history.replaceState(null, '', url)
  }

  const isVideo = media.data.mime?.startsWith('video') === true
  const isCurrent = global.track?.materialId === materialId
  const currentMs = isVideo ? localMs : isCurrent ? global.positionMs : 0
  const audioTrack = {
    materialId,
    title: media.data.title ?? media.data.material_id,
    src: blobUrl(media.data.blob_sha),
  }
  const active = segments.find(
    (segment) => currentMs >= segment.start_ms && currentMs < segment.end_ms,
  )
  const mediaElement = isVideo ? (
    <video
      ref={player as React.RefObject<HTMLVideoElement>}
      src={blobUrl(media.data.blob_sha)}
      controls
      className="max-h-72 w-full rounded-md bg-black"
      onTimeUpdate={(event) => setLocalMs(event.currentTarget.currentTime * 1000)}
    />
  ) : (
    <div className="bg-subtle flex items-center gap-2 rounded-md p-2">
      <Button
        size="icon"
        variant="ghost"
        aria-label={isCurrent && global.playing ? t('audio.pause') : t('audio.play')}
        onClick={() => global.toggle(audioTrack)}
      >
        {isCurrent && global.playing ? (
          <Pause className="size-4" aria-hidden />
        ) : (
          <Play className="size-4" aria-hidden />
        )}
      </Button>
      <input
        type="range"
        min={0}
        max={Math.max(media.data.duration_ms, 1)}
        value={isCurrent ? Math.min(global.positionMs, media.data.duration_ms) : 0}
        aria-label={t('audio.seek')}
        onChange={(event) => {
          if (!isCurrent) {
            global.play(audioTrack)
          }
          global.seek(Number(event.target.value))
        }}
        className="min-w-0 flex-1"
      />
      <span className="text-muted-foreground text-[11px] tabular-nums">
        {stamp(currentMs)} / {stamp(media.data.duration_ms)}
      </span>
    </div>
  )

  return (
    <div className="border-border bg-surface mb-4 space-y-3 rounded-lg border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Headphones className="text-primary size-4" aria-hidden />
        <span className="text-sm font-medium">{t('library.mediaPlayer')}</span>
        <label className="text-muted-foreground ml-auto flex items-center gap-1 text-[11px]">
          {t('library.mediaSpeed')}
          <select
            value={speed}
            aria-label={t('library.mediaSpeed')}
            onChange={(event) => {
              const next = Number(event.target.value)
              setSpeed(next)
              if (isVideo && player.current) {
                player.current.playbackRate = next
              } else {
                global.setSpeed(next)
              }
            }}
            className="bg-surface border-border rounded border px-1 py-0.5"
          >
            {[0.75, 1, 1.25, 1.5, 2].map((value) => (
              <option key={value} value={value}>
                {value}×
              </option>
            ))}
          </select>
        </label>
      </div>
      {mediaElement}
      <div className="flex items-center gap-2">
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && visible[0]) {
              event.preventDefault()
              seek(visible[0])
            }
          }}
          placeholder={t('library.mediaSearch')}
          aria-label={t('library.mediaSearch')}
          className="bg-surface border-border min-w-0 flex-1 rounded-md border px-2 py-1 text-xs"
        />
        {search.trim() ? (
          <span className="text-muted-foreground text-[10px]">
            {t('library.mediaSearchResults', { count: visible.length })}
          </span>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="outline" onClick={() => setNoteOpen((open) => !open)}>
          <MapPin className="size-3.5" aria-hidden />
          {t('library.markMoment')}
        </Button>
        <Button size="sm" variant="outline" onClick={() => setStudyOpen(true)}>
          <Sparkles className="size-3.5" aria-hidden />
          {t('library.studyLecture')}
        </Button>
        {noteOpen ? (
          <form
            className="flex min-w-0 flex-1 items-center gap-1"
            onSubmit={(event) => {
              event.preventDefault()
              addMoment.mutate()
            }}
          >
            <input
              autoFocus
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder={t('library.momentNote')}
              aria-label={t('library.momentNote')}
              className="bg-surface border-border min-w-0 flex-1 rounded-md border px-2 py-1 text-xs"
            />
            <Button size="sm" type="submit" disabled={addMoment.isPending}>
              {t('library.saveMoment')}
            </Button>
          </form>
        ) : null}
      </div>
      {moments.length > 0 ? (
        <div className="space-y-1">
          <p className="text-muted-foreground text-[11px] font-medium">
            {t('library.moments', { count: moments.length })}
          </p>
          {moments.map((moment) => {
            const start = Number(moment.payload.start_ms ?? 0)
            return (
              <div
                key={moment.id}
                className="hover:bg-subtle flex items-center gap-2 rounded px-2 py-1 text-xs"
              >
                <input
                  type="checkbox"
                  checked={selectedMoments.has(moment.id)}
                  aria-label={t('library.selectMoment', { time: stamp(start) })}
                  onChange={(event) =>
                    setSelectedMoments((current) => {
                      const next = new Set(current)
                      if (event.target.checked) {
                        next.add(moment.id)
                      } else {
                        next.delete(moment.id)
                      }
                      return next
                    })
                  }
                />
                <button
                  type="button"
                  className="flex min-w-0 flex-1 items-center gap-2 text-left"
                  onClick={() => {
                    if (player.current) {
                      player.current.currentTime = start / 1000
                      void player.current.play()
                    }
                  }}
                >
                  <span className="text-primary tabular-nums">{stamp(start)}</span>
                  <span className="truncate">{moment.note_md || t('library.momentUntitled')}</span>
                </button>
                <button
                  type="button"
                  aria-label={t('library.momentToCard')}
                  title={t('library.momentToCard')}
                  className="text-muted-foreground hover:text-primary"
                  onClick={() =>
                    createMomentCard.mutate({ quote: moment.quote ?? '', note: moment.note_md ?? '' })
                  }
                >
                  <Layers className="size-3" aria-hidden />
                </button>
                <button
                  type="button"
                  aria-label={t('library.momentToNote')}
                  title={t('library.momentToNote')}
                  className="text-muted-foreground hover:text-primary"
                  onClick={() =>
                    createMomentNote.mutate({
                      quote: moment.quote ?? '',
                      note: moment.note_md ?? '',
                      time: start,
                    })
                  }
                >
                  <StickyNote className="size-3" aria-hidden />
                </button>
                <button
                  type="button"
                  aria-label={t('library.momentToPlan')}
                  title={t('library.momentToPlan')}
                  className="text-muted-foreground hover:text-primary"
                  onClick={() =>
                    createMomentPlan.mutate({
                      quote: moment.quote ?? '',
                      note: moment.note_md ?? '',
                      time: start,
                    })
                  }
                >
                  <CalendarPlus className="size-3" aria-hidden />
                </button>
                <button
                  type="button"
                  aria-label={t('library.deleteMoment')}
                  className="text-muted-foreground hover:text-danger"
                  onClick={() => removeMoment.mutate(moment.id)}
                >
                  <Trash2 className="size-3" aria-hidden />
                </button>
              </div>
            )
          })}
        </div>
      ) : null}
      {moments.length > 0 ? (
        <Button
          size="sm"
          variant="outline"
          disabled={selectedMoments.size === 0 || createMomentCards.isPending}
          onClick={() =>
            createMomentCards.mutate(
              moments
                .filter((moment) => selectedMoments.has(moment.id))
                .map((moment) => ({ quote: moment.quote ?? '', note: moment.note_md ?? '' }))
            )
          }
        >
          <Layers className="size-3.5" aria-hidden />
          {t('library.makeMomentCards', { count: selectedMoments.size })}
        </Button>
      ) : null}
      {momentAction ? (
        <p className="text-muted-foreground text-[11px]" role="status">
          {momentAction}
        </p>
      ) : null}
      {visible.length === 0 ? (
        <p className="text-muted-foreground text-xs">{t('library.mediaNoTranscript')}</p>
      ) : (
        <ol className="max-h-64 space-y-1 overflow-y-auto">
          {visible.map((segment) => (
            <li key={segment.id}>
              {editing === segment.id ? (
                <div className="flex items-center gap-1">
                  <input
                    autoFocus
                    value={editingText}
                    onChange={(event) => setEditingText(event.target.value)}
                    aria-label={t('library.editTranscript')}
                    className="bg-surface border-border min-w-0 flex-1 rounded border px-2 py-1 text-xs"
                  />
                  <input
                    value={editingSpeaker}
                    onChange={(event) => setEditingSpeaker(event.target.value)}
                    aria-label={t('library.editSpeaker')}
                    placeholder={t('library.speakerPlaceholder')}
                    className="bg-surface border-border w-24 rounded border px-2 py-1 text-xs"
                  />
                  <Button
                    size="sm"
                    disabled={!editingText.trim() || editSegment.isPending}
                    onClick={() => editSegment.mutate(segment.id)}
                  >
                    {t('common.apply')}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>
                    {t('common.cancel')}
                  </Button>
                </div>
              ) : (
                <div className="flex items-start gap-1">
                  <button
                    type="button"
                    onClick={() => seek(segment)}
                    className={cn(
                      'hover:bg-subtle flex min-w-0 flex-1 items-start gap-2 rounded px-2 py-1 text-left text-xs',
                      active?.id === segment.id && 'bg-primary/10 text-primary',
                    )}
                  >
                    <span className="text-muted-foreground flex items-center gap-1 tabular-nums">
                      <Play className="size-3" aria-hidden />
                      {stamp(segment.start_ms)}
                    </span>
                    <span className="min-w-0 flex-1">{segment.text}</span>
                  </button>
                  <button
                    type="button"
                    aria-label={t('library.editTranscriptFor', { time: stamp(segment.start_ms) })}
                    className="text-muted-foreground hover:text-foreground p-1"
                    onClick={() => {
                      setEditing(segment.id)
                      setEditingText(segment.text)
                      setEditingSpeaker(segment.speaker ?? '')
                    }}
                  >
                    <Pencil className="size-3" aria-hidden />
                  </button>
                  {active?.id === segment.id &&
                  currentMs > segment.start_ms &&
                  currentMs < segment.end_ms ? (
                    <button
                      type="button"
                      aria-label={t('library.splitTranscript', { time: stamp(currentMs) })}
                      className="text-muted-foreground hover:text-foreground p-1"
                      onClick={() => split.mutate(segment.id)}
                    >
                      <Scissors className="size-3" aria-hidden />
                    </button>
                  ) : null}
                  {segments[segments.findIndex((entry) => entry.id === segment.id) + 1] ? (
                    <button
                      type="button"
                      aria-label={t('library.mergeTranscript')}
                      className="text-muted-foreground hover:text-foreground p-1"
                      onClick={() =>
                        merge.mutate({
                          first: segment.id,
                          second:
                            segments[segments.findIndex((entry) => entry.id === segment.id) + 1]!
                              .id,
                        })
                      }
                    >
                      <Combine className="size-3" aria-hidden />
                    </button>
                  ) : null}
                </div>
              )}
            </li>
          ))}
        </ol>
      )}
      {studyOpen && media.data.course_id ? (
        <GenerateDialog
          task="compose"
          courseId={media.data.course_id}
          initial={{
            composeKind: 'study_guide',
            materialIds: [materialId],
            instructions: t('library.studyLectureInstruction'),
          }}
          onClose={() => setStudyOpen(false)}
          onSuccess={() => setStudyOpen(false)}
        />
      ) : null}
    </div>
  )
}
