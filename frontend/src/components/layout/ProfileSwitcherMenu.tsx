import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ProfileSwitcher } from '@/components/ui/profile-switcher'
import { createProfile, deleteProfile, patchProfile, type ProfileInfo } from '@/lib/api'

import { useConfirm } from '@/lib/use-confirm'

/** App-chrome profile switcher (identity-auth §6/§12): the shared
 * `ProfileSwitcher` bound to study's profile API — select, create,
 * rename, set-Default and delete (behind a confirm) over
 * list/create/patch/delete; the active selection stays AppShell-owned
 * (`null` = the instance Default, no X-Profile-Id header). */
export function ProfileSwitcherMenu({
  profiles,
  selectedId,
  loading = false,
  onSelect,
}: {
  profiles: ProfileInfo[]
  selectedId: string | null
  loading?: boolean
  onSelect: (profileId: string | null) => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const [confirm, confirmElement] = useConfirm()

  const create = useMutation({
    mutationFn: (name: string) => createProfile(name),
    onSuccess: async (profile) => {
      setError(null)
      await queryClient.invalidateQueries({ queryKey: ['profiles'] })
      onSelect(profile.id)
    },
    onError: (err: Error) => setError(err.message),
  })
  const rename = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      patchProfile(id, { name }),
    onSuccess: async () => {
      setError(null)
      await queryClient.invalidateQueries({ queryKey: ['profiles'] })
    },
    onError: (err: Error) => setError(err.message),
  })
  const setDefault = useMutation({
    mutationFn: (id: string) => patchProfile(id, { is_default: true }),
    onSuccess: async () => {
      setError(null)
      await queryClient.invalidateQueries({ queryKey: ['profiles'] })
    },
    onError: (err: Error) => setError(err.message),
  })
  const remove = useMutation({
    mutationFn: (profileId: string) => deleteProfile(profileId),
    onSuccess: async (_result, profileId) => {
      setError(null)
      await queryClient.invalidateQueries({ queryKey: ['profiles'] })
      if (selectedId === profileId) {
        onSelect(null)
      }
    },
    onError: (err: Error) => setError(err.message),
  })

  return (
    <>
      <ProfileSwitcher
        profiles={profiles}
        currentId={selectedId}
        loading={loading && profiles.length === 0}
        error={error}
        className="block w-full"
        labels={{
          trigger: t('profiles.manage'),
          panelTitle: t('profiles.manage'),
          currentBadge: t('profiles.currentBadge'),
          defaultBadge: t('profiles.defaultBadge'),
          newProfile: t('profiles.newProfile'),
          newProfilePlaceholder: t('profiles.namePlaceholder'),
          create: t('profiles.create'),
          rename: (name) => t('profiles.rename', { name }),
          renamePlaceholder: t('profiles.namePlaceholder'),
          renameSubmit: t('profiles.renameSubmit'),
          setDefault: (name) => t('profiles.setDefault', { name }),
          delete: (name) => t('profiles.delete', { name }),
          cancel: t('common.cancel'),
          loading: t('profiles.loading'),
          empty: t('profiles.empty'),
        }}
        onSelect={(profile) => onSelect(profile.is_default ? null : profile.id)}
        onCreate={(name) => create.mutate(name)}
        onRename={(profile, name) => rename.mutate({ id: profile.id, name })}
        onSetDefault={(profile) => setDefault.mutate(profile.id)}
        onDelete={async (profile) => {
          const ok = await confirm({
            title: t('common.remove'),
            description: t('profiles.confirmDelete'),
            confirmLabel: t('common.remove'),
            cancelLabel: t('common.cancel'),
            destructive: true,
          })
          if (ok) remove.mutate(profile.id)
        }}
      />
      {confirmElement}
    </>
  )
}
