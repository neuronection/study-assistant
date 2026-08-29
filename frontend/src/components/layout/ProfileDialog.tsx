import { Loader2, Plus, Trash2, UserRound } from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { createProfile, deleteProfile, type ProfileInfo } from '@/lib/api'

import { cn } from '@/lib/utils'
import { useCloseFloatings } from '@/lib/ui-overlays'
import { useConfirm } from '@/lib/use-confirm'

function ProfileAvatar({ profile }: { profile: ProfileInfo }) {
  const letter = (profile.name.trim()[0] ?? '?').toUpperCase()
  return (
    <span
      className="flex size-7 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold"
      style={
        profile.color
          ? { backgroundColor: `${profile.color}22`, color: profile.color }
          : undefined
      }
      aria-hidden
    >
      {profile.color ? letter : <UserRound className="size-3.5" />}
    </span>
  )
}

export function ProfileDialog({
  profiles,
  selectedId,
  onSelect,
  onClose,
}: {
  profiles: ProfileInfo[]
  selectedId: number | null
  onSelect: (profileId: number | null) => void
  onClose: () => void
}) {
  useCloseFloatings()
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [adding, setAdding] = useState(false)
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [confirm, confirmElement] = useConfirm()

  const create = useMutation({
    mutationFn: () => createProfile(name.trim()),
    onSuccess: async (profile) => {
      setName('')
      setError(null)
      await queryClient.invalidateQueries({ queryKey: ['profiles'] })
      onSelect(profile.id)
      onClose()
    },
    onError: (err: Error) => setError(err.message),
  })
  const remove = useMutation({
    mutationFn: (profileId: number) => deleteProfile(profileId),
    onSuccess: async (_result, profileId) => {
      await queryClient.invalidateQueries({ queryKey: ['profiles'] })
      if (selectedId === profileId) {
        onSelect(null)
      }
    },
    onError: (err: Error) => setError(err.message),
  })

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={t('profiles.manage')}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose()
        }
      }}
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          onClose()
        }
      }}
    >
      <div className="bg-surface border-border w-full max-w-sm rounded-xl border p-4 shadow-xl">
        <div className="flex items-center gap-2">
          <span className="bg-primary/10 text-primary flex size-8 items-center justify-center rounded-lg" aria-hidden>
            <UserRound className="size-4" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="text-sm font-semibold">{t('profiles.manage')}</h2>
            <p className="text-muted-foreground text-xs">{t('profiles.manageHint')}</p>
          </div>
        </div>

        <ul className="border-border mt-3 space-y-0.5 border-y py-2">
          {profiles.map((profile, index) => {
            const active = selectedId === profile.id || (selectedId === null && index === 0)
            return (
              <li key={profile.id} className="group hover:bg-subtle flex items-center gap-2 rounded-md px-2 py-1.5">
                <button
                  type="button"
                  className="flex min-w-0 flex-1 items-center gap-2 text-left text-xs"
                  onClick={() => {
                    onSelect(index === 0 ? null : profile.id)
                    onClose()
                  }}
                >
                  <ProfileAvatar profile={profile} />
                  <span className={cn('min-w-0 flex-1 truncate', active && 'font-medium')}>
                    {index === 0 ? t('profiles.default') : profile.name}
                  </span>
                </button>
                {index > 0 ? (
                  <button
                    type="button"
                    className="text-muted-foreground hidden shrink-0 group-hover:block hover:text-danger"
                    title={t('common.remove')}
                    disabled={remove.isPending}
                    onClick={async () => {
                      const ok = await confirm({
                        title: t('common.remove'),
                        description: t('profiles.confirmDelete'),
                        confirmLabel: t('common.remove'),
                        cancelLabel: t('common.cancel'),
                        destructive: true,
                      })
                      if (ok) remove.mutate(profile.id)
                    }}
                  >
                    <Trash2 className="size-3.5" aria-hidden />
                  </button>
                ) : null}
              </li>
            )
          })}
        </ul>

        {adding ? (
          <form
            className="mt-3"
            onSubmit={(event) => {
              event.preventDefault()
              if (name.trim()) {
                create.mutate()
              }
            }}
          >
            <p className="text-muted-foreground mb-1.5 text-[10px] font-medium tracking-wide uppercase">
              {t('profiles.addTitle')}
            </p>
            <div className="flex gap-2">
              <input
                autoFocus
                className="bg-surface border-border min-w-0 flex-1 rounded-md border px-2 py-1.5 text-xs"
                placeholder={t('profiles.namePlaceholder')}
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
              <Button type="submit" size="sm" disabled={!name.trim() || create.isPending}>
                {create.isPending ? (
                  <Loader2 className="animate-spin" aria-hidden />
                ) : (
                  <Plus aria-hidden />
                )}
                {t('settings.add')}
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={create.isPending}
                onClick={() => {
                  setName('')
                  setError(null)
                  setAdding(false)
                }}
              >
                {t('common.cancel')}
              </Button>
            </div>
          </form>
        ) : (
          <Button
            type="button"
            variant="outline"
            className="mt-3 w-full border-dashed"
            onClick={() => setAdding(true)}
          >
            <Plus aria-hidden />
            {t('profiles.addTitle')}
          </Button>
        )}
        {error ? <p className="text-danger mt-2 text-xs">{error}</p> : null}
      </div>
      {confirmElement}
    </div>
  )
}
