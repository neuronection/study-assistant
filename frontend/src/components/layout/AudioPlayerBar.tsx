import { useNavigate } from '@tanstack/react-router'
import { Download, Loader2, Pause, Play, Trash2, Volume2, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { useAudioPlayer } from '@/lib/audio-player'

function stamp(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000))
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

export function AudioPlayerBar() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const player = useAudioPlayer()
  if (!player.track) {
    return null
  }
  const duration = Math.max(player.durationMs, player.positionMs, 1)
  return (
    <div className="bg-surface border-border fixed bottom-[calc(4.25rem+env(safe-area-inset-bottom))] left-1/2 z-40 flex w-[min(94vw,46rem)] -translate-x-1/2 items-center gap-2 rounded-lg border p-2 shadow-[var(--as-shadow-3)] md:bottom-4">
      <Volume2 className="text-primary size-4 shrink-0" aria-hidden />
      <button
        type="button"
        className="min-w-0 flex-1 truncate text-left text-xs font-medium"
        onClick={() =>
          void navigate({
            to: '/library/$materialId',
            params: { materialId: player.track!.materialId },
          })
        }
      >
        {player.track.title}
      </button>
      <span className="text-muted-foreground hidden text-[10px] tabular-nums sm:inline">
        {stamp(player.positionMs)} / {stamp(player.durationMs)}
      </span>
      <input
        type="range"
        min={0}
        max={duration}
        value={Math.min(player.positionMs, duration)}
        aria-label={t('audio.seek')}
        onChange={(event) => player.seek(Number(event.target.value))}
        className="hidden w-28 sm:block"
      />
      <select
        value={player.sleepMinutes ?? ''}
        aria-label={t('audio.sleep')}
        onChange={(event) =>
          player.setSleepTimer(event.target.value ? Number(event.target.value) : null)
        }
        className="bg-surface border-border rounded border px-1 py-0.5 text-[10px]"
      >
        <option value="">{t('audio.sleepOff')}</option>
        {[5, 10, 20, 30].map((value) => (
          <option key={value} value={value}>
            {t('audio.sleepMinutes', { count: value })}
          </option>
        ))}
      </select>
      <select
        value={player.speed}
        aria-label={t('audio.speed')}
        onChange={(event) => player.setSpeed(Number(event.target.value))}
        className="bg-surface border-border rounded border px-1 py-0.5 text-[10px]"
      >
        {[0.75, 1, 1.25, 1.5, 2].map((value) => (
          <option key={value} value={value}>
            {value}×
          </option>
        ))}
      </select>
      {player.canDownload ? (
        <Button
          size="icon"
          variant="ghost"
          aria-label={
            player.offline === 'cached'
              ? t('audio.removeDownload')
              : t('audio.download')
          }
          title={
            player.downloadError
              ? t('audio.downloadFailed')
              : player.offline === 'cached'
                ? t('audio.offlineReady')
                : t('audio.download')
          }
          disabled={player.downloading}
          onClick={player.offline === 'cached' ? player.removeDownload : player.download}
        >
          {player.downloading ? (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          ) : player.offline === 'cached' ? (
            <Trash2 className="size-4" aria-hidden />
          ) : (
            <Download className="size-4" aria-hidden />
          )}
        </Button>
      ) : null}
      <Button
        size="icon"
        variant="ghost"
        aria-label={player.playing ? t('audio.pause') : t('audio.play')}
        onClick={() => player.toggle()}
      >
        {player.playing ? <Pause className="size-4" aria-hidden /> : <Play className="size-4" aria-hidden />}
      </Button>
      <Button
        size="icon"
        variant="ghost"
        aria-label={t('audio.close')}
        onClick={player.stop}
      >
        <X className="size-4" aria-hidden />
      </Button>
    </div>
  )
}
