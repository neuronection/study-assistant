import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowUp,
  Check,
  ChevronRight,
  FolderClosed,
  FolderPlus,
  Layers,
  Link2,
  Loader2,
  Lock,
  Minus,
  Plus,
  X,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { MaterialRow } from '@/components/materials/MaterialRow'
import { UploadButton } from '@/components/materials/UploadButton'
import { UploadDropzone } from '@/components/materials/UploadDropzone'
import { useMaterialUpload } from '@/components/materials/materialUpload'
import { Button } from '@/components/ui/button'
import { ErrorBanner } from '@/components/ui/error-banner'
import { SearchInput } from '@/components/ui/SearchInput'
import { fuzzyFilter } from '@/lib/fuzzy'
import {
  allocateMaterial,
  allocateNodeFolder,
  browseSource,
  ingestSourceFile,
  listFolders,
  listMaterials,
  type Folder,
  type Material,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { useCloseFloatings } from '@/lib/ui-overlays'

type PickerLocation =
  | { kind: 'all' }
  | { kind: 'folder'; folderId: number | null }
  | { kind: 'link'; folderId: number; sourceId: number; subdir: string }

type PickableMaterial = {
  id: number
  title: string
  kind: string
  status: string
}

function CheckMark({ state }: { state: boolean | 'mixed' | 'off' }) {
  if (state === true) {
    return (
      <span className="bg-primary text-primary-foreground flex size-4 shrink-0 items-center justify-center rounded">
        <Check className="size-3" aria-hidden />
      </span>
    )
  }
  if (state === 'mixed') {
    return (
      <span className="bg-primary text-primary-foreground flex size-4 shrink-0 items-center justify-center rounded">
        <Minus className="size-3" aria-hidden />
      </span>
    )
  }
  return <span className="border-border size-4 shrink-0 rounded border" aria-hidden />
}

function FolderToggle({
  count,
  state,
  onToggle,
  label,
}: {
  count: number
  state: boolean | 'mixed'
  onToggle: () => void
  label: string
}) {
  const { t } = useTranslation()
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={state}
      title={t('materialPicker.selectFolder', { count })}
      className="text-muted-foreground hover:bg-subtle hover:text-foreground flex shrink-0 items-center gap-1 rounded px-1.5 py-1 text-[11px]"
      onClick={onToggle}
    >
      <CheckMark state={state} />
      {label}
    </button>
  )
}

function FolderAssignButton({
  folder,
  assigned,
  selected,
  onToggle,
}: {
  folder: { id: number; name: string }
  assigned: boolean
  selected: boolean
  onToggle: () => void
}) {
  const { t } = useTranslation()
  if (assigned) {
    return (
      <span
        className="text-success flex shrink-0 items-center gap-1 rounded px-1.5 py-1 text-[11px]"
        title={t('materialPicker.folderAssignedHere')}
      >
        <Lock className="size-3" aria-hidden />
      </span>
    )
  }
  return (
    <button
      type="button"
      className={cn(
        'flex shrink-0 items-center gap-1 rounded px-1.5 py-1 text-[11px]',
        selected
          ? 'bg-primary/10 text-primary'
          : 'text-muted-foreground hover:bg-subtle hover:text-foreground'
      )}
      title={t('materialPicker.assignFolder', { name: folder.name })}
      aria-pressed={selected}
      onClick={onToggle}
    >
      <FolderPlus className="size-3.5" aria-hidden />
    </button>
  )
}

export function MaterialPickerDialog({
  courseId,
  nodeId,
  nodeTitle,
  assignedIds,
  assignedFolderIds,
  onClose,
  mode = 'allocate',
  onSelect,
  confirmLabel,
  lockedLabel,
}: {
  courseId: number
  nodeId?: number | null
  nodeTitle?: string
  assignedIds: Set<number>
  assignedFolderIds?: Set<number>
  onClose: () => void
  mode?: 'allocate' | 'select'
  onSelect?: (ids: number[]) => void
  confirmLabel?: string
  lockedLabel?: string
}) {
  useCloseFloatings()
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [selected, setSelected] = useState<Map<number, string>>(new Map())
  const [selectedFolders, setSelectedFolders] = useState<Map<number, string>>(new Map())
  const [location, setLocation] = useState<PickerLocation>({ kind: 'folder', folderId: null })
  const [query, setQuery] = useState('')
  const [collapsed, setCollapsed] = useState<Record<number, boolean>>({})
  const [ingesting, setIngesting] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const folders = useQuery({
    queryKey: ['folders', courseId],
    queryFn: () => listFolders(courseId),
  })
  const allMaterials = useQuery({
    queryKey: ['materials', 'course', courseId],
    queryFn: () => listMaterials(undefined, courseId),
  })
  const unfiledMaterials = useQuery({
    queryKey: ['materials', 'unfiled', courseId],
    queryFn: () => listMaterials(undefined, courseId, true),
  })
  const linkState =
    location.kind === 'link'
      ? { folderId: location.folderId, sourceId: location.sourceId, subdir: location.subdir }
      : null
  const browse = useQuery({
    queryKey: ['source-browse', linkState?.sourceId ?? 0, linkState?.subdir ?? ''],
    queryFn: () => browseSource(linkState?.sourceId as number, linkState?.subdir ?? ''),
    enabled: linkState !== null,
  })

  const canAssignFolders = mode === 'allocate' && nodeId != null
  const lockedFolderIds = assignedFolderIds ?? new Set<number>()

  const allocate = useMutation({
    mutationFn: async () => {
      await Promise.all(
        Array.from(selected.keys()).map((materialId) =>
          allocateMaterial(nodeId as number, materialId)
        )
      )
      for (const folderId of selectedFolders.keys()) {
        await allocateNodeFolder(nodeId as number, folderId)
      }
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['node-workspace'] })
      await queryClient.invalidateQueries({ queryKey: ['tree'] })
      await queryClient.invalidateQueries({ queryKey: ['materials'] })
      onClose()
    },
    onError: (error: Error) => setActionError(error.message),
  })

  const upload = useMaterialUpload({
    courseId,
    getFolderId: () =>
      location.kind === 'folder' && location.folderId !== null ? location.folderId : null,
    onUploaded: (result) =>
      setSelected((current) => new Map(current).set(result.material.id, result.material.title)),
  })

  const childrenOf = useMemo(() => {
    const map = new Map<number | null, Folder[]>()
    for (const folder of folders.data ?? []) {
      const list = map.get(folder.parent_id) ?? []
      list.push(folder)
      map.set(folder.parent_id, list)
    }
    for (const list of map.values()) {
      list.sort((a, b) => a.name.localeCompare(b.name))
    }
    return map
  }, [folders.data])

  const materialsByFolder = useMemo(() => {
    const map = new Map<number, Material[]>()
    for (const material of allMaterials.data ?? []) {
      if (material.folder_id !== null) {
        const list = map.get(material.folder_id) ?? []
        list.push(material)
        map.set(material.folder_id, list)
      }
    }
    return map
  }, [allMaterials.data])

  const subtreeMaterialIds = (folderId: number): number[] => {
    const ids: number[] = []
    const stack = [folderId]
    while (stack.length > 0) {
      const current = stack.pop() as number
      for (const material of materialsByFolder.get(current) ?? []) {
        ids.push(material.id)
      }
      for (const child of childrenOf.get(current) ?? []) {
        stack.push(child.id)
      }
    }
    return ids
  }

  const folderCount = (folderId: number): number => subtreeMaterialIds(folderId).length

  const toggleIds = (entries: { id: number; title: string }[]) => {
    setSelected((current) => {
      const next = new Map(current)
      const allSelected = entries.every((entry) => next.has(entry.id))
      for (const entry of entries) {
        if (allSelected) {
          next.delete(entry.id)
        } else {
          next.set(entry.id, entry.title)
        }
      }
      return next
    })
  }

  const toggleMaterial = (material: PickableMaterial) =>
    setSelected((current) => {
      const next = new Map(current)
      if (next.has(material.id)) {
        next.delete(material.id)
      } else {
        next.set(material.id, material.title)
      }
      return next
    })

  const toggleFolder = (folder: Folder) =>
    setSelectedFolders((current) => {
      const next = new Map(current)
      if (next.has(folder.id)) {
        next.delete(folder.id)
      } else {
        next.set(folder.id, folder.name)
      }
      return next
    })

  const ingestAndSelect = async (relpath: string, name: string) => {
    if (linkState === null) {
      return
    }
    setIngesting(relpath)
    setActionError(null)
    try {
      const result = await ingestSourceFile(linkState.sourceId, relpath)
      setSelected((current) => new Map(current).set(result.material_id, name))
      await queryClient.invalidateQueries({ queryKey: ['source-browse'] })
      await queryClient.invalidateQueries({ queryKey: ['materials'] })
    } catch (error) {
      setActionError((error as Error).message)
    } finally {
      setIngesting(null)
    }
  }

  const folderChain = (folderId: number | null): Folder[] => {
    const chain: Folder[] = []
    let walker: Folder | undefined =
      folderId === null
        ? undefined
        : (folders.data ?? []).find((entry) => entry.id === folderId)
    while (walker !== undefined) {
      chain.unshift(walker)
      walker = (folders.data ?? []).find((entry) => entry.id === walker?.parent_id)
    }
    return chain
  }

  const currentFolder =
    location.kind === 'folder' && location.folderId !== null
      ? (folders.data ?? []).find((entry) => entry.id === location.folderId) ?? null
      : null

  const visibleMaterials: PickableMaterial[] = useMemo(() => {
    const toPickable = (entry: { id: number; title: string; kind: string; status: string }) => ({
      id: entry.id,
      title: entry.title,
      kind: entry.kind,
      status: entry.status,
    })
    let list: PickableMaterial[]
    if (location.kind === 'all') {
      list = (allMaterials.data ?? []).map(toPickable)
    } else if (location.kind === 'folder') {
      const folderId = location.folderId
      if (folderId === null) {
        list = (unfiledMaterials.data ?? []).map(toPickable)
      } else {
        list = (materialsByFolder.get(folderId) ?? []).map(toPickable)
      }
    } else {
      list = (browse.data?.materials ?? []).map(toPickable)
    }
    return fuzzyFilter(list, query, (entry) => entry.title)
  }, [location, allMaterials.data, unfiledMaterials.data, materialsByFolder, browse.data, query])

  const visibleSelectable = visibleMaterials.filter((entry) => !assignedIds.has(entry.id))
  const allVisibleSelected =
    visibleSelectable.length > 0 &&
    visibleSelectable.every((entry) => selected.has(entry.id))
  const someVisibleSelected = visibleSelectable.some((entry) => selected.has(entry.id))

  const childFolders =
    location.kind === 'folder'
      ? (childrenOf.get(location.folderId) ?? [])
      : location.kind === 'link'
        ? []
        : []

  const crumbs: { key: string; label: string; onClick: () => void }[] = []
  if (location.kind === 'all') {
    crumbs.push({
      key: 'all',
      label: t('materialPicker.allMaterials'),
      onClick: () => setLocation({ kind: 'all' }),
    })
  } else if (location.kind === 'folder') {
    crumbs.push({
      key: 'root',
      label: t('materialPicker.rootLabel'),
      onClick: () => setLocation({ kind: 'folder', folderId: null }),
    })
    for (const entry of folderChain(location.folderId)) {
      crumbs.push({
        key: `folder-${entry.id}`,
        label: entry.name,
        onClick: () => setLocation({ kind: 'folder', folderId: entry.id }),
      })
    }
  } else {
    const linkFolder = (folders.data ?? []).find((entry) => entry.id === location.folderId)
    crumbs.push({
      key: 'root',
      label: t('materialPicker.rootLabel'),
      onClick: () => setLocation({ kind: 'folder', folderId: null }),
    })
    if (linkFolder !== undefined) {
      crumbs.push({
        key: `folder-${linkFolder.id}`,
        label: linkFolder.name,
        onClick: () => setLocation({ ...location, subdir: '' }),
      })
    }
    const parts = location.subdir ? location.subdir.split('/') : []
    parts.forEach((part, index) => {
      crumbs.push({
        key: `sub-${index}-${part}`,
        label: part,
        onClick: () =>
          setLocation({ ...location, subdir: parts.slice(0, index + 1).join('/') }),
      })
    })
  }

  const upTarget = () => {
    if (location.kind === 'folder' && currentFolder !== null) {
      setLocation({ kind: 'folder', folderId: currentFolder.parent_id })
    } else if (location.kind === 'link' && location.subdir) {
      const parts = location.subdir.split('/')
      setLocation({ ...location, subdir: parts.slice(0, -1).join('/') })
    } else if (location.kind === 'link') {
      setLocation({ kind: 'folder', folderId: null })
    }
  }

  const openFolder = (entry: Folder) => {
    if (entry.source_id !== null) {
      setLocation({ kind: 'link', folderId: entry.id, sourceId: entry.source_id, subdir: '' })
    } else {
      setLocation({ kind: 'folder', folderId: entry.id })
    }
  }

  const renderSidebarNode = (entry: Folder, depth: number) => {
    const isLink = entry.source_id !== null
    const expanded = !collapsed[entry.id]
    const hasChildren = (childrenOf.get(entry.id) ?? []).length > 0
    const active =
      (location.kind === 'folder' && location.folderId === entry.id) ||
      (location.kind === 'link' && location.folderId === entry.id)
    return (
      <div key={entry.id}>
        <div
          className={cn(
            'hover:bg-subtle flex items-center gap-1 rounded-md pr-1.5 text-sm',
            active && 'bg-primary/10'
          )}
          style={{ paddingLeft: depth * 12 }}
        >
          {hasChildren ? (
            <button
              type="button"
              className="text-muted-foreground shrink-0 p-0.5"
              aria-label={t('courses.toggleNode')}
              aria-expanded={expanded}
              onClick={() => setCollapsed((current) => ({ ...current, [entry.id]: !expanded }))}
            >
              <ChevronRight
                className={cn('size-3.5 transition-transform', expanded && 'rotate-90')}
                aria-hidden
              />
            </button>
          ) : (
            <span className="w-[22px] shrink-0" aria-hidden />
          )}
          <button
            type="button"
            className="hover:bg-subtle flex min-w-0 flex-1 items-center gap-1.5 rounded py-1 text-left"
            onClick={() => openFolder(entry)}
          >
            {isLink ? (
              <span className="relative shrink-0">
                <FolderClosed className="text-primary size-4" aria-hidden />
                <Link2 className="text-primary absolute -right-1 -bottom-1 size-3" aria-hidden />
              </span>
            ) : (
              <FolderClosed className="text-primary size-4 shrink-0" aria-hidden />
            )}
            <span className="min-w-0 flex-1 truncate">{entry.name}</span>
          </button>
          {canAssignFolders ? (
            <FolderAssignButton
              folder={entry}
              assigned={lockedFolderIds.has(entry.id)}
              selected={selectedFolders.has(entry.id)}
              onToggle={() => toggleFolder(entry)}
            />
          ) : null}
          {!isLink ? (
            <span className="text-muted-foreground shrink-0 text-[10px]">
              {folderCount(entry.id)}
            </span>
          ) : null}
        </div>
        {expanded
          ? (childrenOf.get(entry.id) ?? []).map((child) => renderSidebarNode(child, depth + 1))
          : null}
      </div>
    )
  }

  const loading =
    folders.isLoading ||
    allMaterials.isLoading ||
    (location.kind === 'folder' &&
      location.folderId === null &&
      unfiledMaterials.isLoading) ||
    (location.kind === 'link' && browse.isLoading)

  const emptyList =
    !loading &&
    visibleMaterials.length === 0 &&
    childFolders.length === 0 &&
    (location.kind !== 'link' || (browse.data?.uningested.length ?? 0) === 0)

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose()
        }
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t('materialPicker.title')}
        className="bg-surface border-border flex h-[min(640px,90vh)] w-full max-w-3xl flex-col rounded-xl border shadow-xl"
      >
        <div className="border-border flex items-center gap-3 border-b px-5 py-3">
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-sm font-semibold">{t('materialPicker.title')}</h2>
            {nodeTitle ? (
              <p className="text-muted-foreground truncate text-xs">{nodeTitle}</p>
            ) : null}
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label={t('settings.cancel')}>
            <X className="size-4" aria-hidden />
          </Button>
        </div>

        <div className="flex min-h-0 flex-1">
          <nav
            className="border-border bg-subtle/40 hidden w-56 shrink-0 flex-col gap-0.5 overflow-y-auto border-r p-2 md:flex"
            aria-label={t('materialPicker.sidebar')}
          >
            <button
              type="button"
              className={cn(
                'hover:bg-subtle flex items-center gap-1.5 rounded-md px-2 py-1 text-left text-sm',
                location.kind === 'all' && 'bg-primary/10'
              )}
              onClick={() => setLocation({ kind: 'all' })}
            >
              <Layers className="text-primary size-4 shrink-0" aria-hidden />
              <span className="min-w-0 flex-1 truncate">{t('materialPicker.allMaterials')}</span>
              <span className="text-muted-foreground shrink-0 text-[10px]">
                {allMaterials.data?.length ?? 0}
              </span>
            </button>
            {(childrenOf.get(null) ?? []).map((entry) => renderSidebarNode(entry, 0))}
            {(folders.data ?? []).length === 0 && !folders.isLoading ? (
              <p className="text-muted-foreground px-2 py-1 text-xs">
                {t('materialPicker.noFolders')}
              </p>
            ) : null}
          </nav>

          <div className="flex min-w-0 flex-1 flex-col">
            <div className="border-border flex items-center gap-1 border-b px-3 py-2">
              <Button
                variant="ghost"
                size="icon"
                className="size-7"
                title={t('library.goUp')}
                disabled={location.kind === 'all' || (location.kind === 'folder' && location.folderId === null)}
                onClick={upTarget}
              >
                <ArrowUp className="size-4" aria-hidden />
              </Button>
              <div className="flex min-w-0 flex-1 items-center gap-0.5 overflow-x-auto text-xs">
                {crumbs.map((crumb, index) => (
                  <span key={crumb.key} className="flex shrink-0 items-center gap-0.5">
                    {index > 0 ? (
                      <ChevronRight className="text-muted-foreground size-3" aria-hidden />
                    ) : null}
                    {index === crumbs.length - 1 ? (
                      <span className="text-foreground max-w-40 truncate font-medium">
                        {crumb.label}
                      </span>
                    ) : (
                      <button
                        type="button"
                        className="text-muted-foreground hover:text-foreground max-w-32 truncate hover:underline"
                        onClick={crumb.onClick}
                      >
                        {crumb.label}
                      </button>
                    )}
                  </span>
                ))}
              </div>
            </div>

            <div className="border-border flex items-center gap-2 border-b px-3 py-2">
              <div className="min-w-0 flex-1">
                <SearchInput
                  value={query}
                  onChange={setQuery}
                  placeholder={t('materialPicker.searchPlaceholder')}
                  ariaLabel={t('materialPicker.searchPlaceholder')}
                  clearLabel={t('library.clearSearch')}
                />
              </div>
              {visibleSelectable.length > 0 ? (
                <button
                  type="button"
                  role="checkbox"
                  aria-checked={allVisibleSelected ? true : someVisibleSelected ? 'mixed' : false}
                  className="text-muted-foreground hover:bg-subtle hover:text-foreground flex shrink-0 items-center gap-1.5 rounded-md px-2 py-1.5 text-xs"
                  onClick={() => toggleIds(visibleSelectable)}
                >
                  <CheckMark state={allVisibleSelected ? true : someVisibleSelected ? 'mixed' : false} />
                  {t('materialPicker.selectAllShown', { count: visibleSelectable.length })}
                </button>
              ) : null}
            </div>

            <div className="min-h-0 flex-1 space-y-0.5 overflow-y-auto p-2">
              {loading ? (
                <Loader2
                  className="text-muted-foreground m-6 size-5 animate-spin"
                  aria-label={t('library.loading')}
                />
              ) : null}
              {!loading
                ? childFolders.map((entry) => {
                    const ids = subtreeMaterialIds(entry.id).filter((id) => !assignedIds.has(id))
                    const titles = new Map(
                      ids.map((id) => {
                        const material = (allMaterials.data ?? []).find((m) => m.id === id)
                        return [id, material?.title ?? String(id)]
                      })
                    )
                    const allSelected = ids.every((id) => selected.has(id))
                    const someSelected = ids.some((id) => selected.has(id))
                    return (
                      <div
                        key={entry.id}
                        className="hover:bg-subtle group flex items-center gap-2 rounded-md px-2 py-1.5 text-sm"
                      >
                        {entry.source_id !== null ? (
                          <>
                            <button
                              type="button"
                              className="flex min-w-0 flex-1 items-center gap-2 text-left"
                              onClick={() => openFolder(entry)}
                            >
                              <span className="relative shrink-0">
                                <FolderClosed className="text-primary size-4" aria-hidden />
                                <Link2
                                  className="text-primary absolute -right-1 -bottom-1 size-3"
                                  aria-hidden
                                />
                              </span>
                              <span className="min-w-0 flex-1 truncate">{entry.name}</span>
                              <span className="text-muted-foreground shrink-0 text-[10px]">
                                {t('materialPicker.linkChip')}
                              </span>
                            </button>
                            {canAssignFolders ? (
                              <FolderAssignButton
                                folder={entry}
                                assigned={lockedFolderIds.has(entry.id)}
                                selected={selectedFolders.has(entry.id)}
                                onToggle={() => toggleFolder(entry)}
                              />
                            ) : null}
                          </>
                        ) : (
                          <>
                            <button
                              type="button"
                              className="flex min-w-0 flex-1 items-center gap-2 text-left"
                              onClick={() => openFolder(entry)}
                            >
                              <FolderClosed className="text-primary size-4 shrink-0" aria-hidden />
                              <span className="min-w-0 flex-1 truncate">{entry.name}</span>
                            </button>
                            {canAssignFolders ? (
                              <FolderAssignButton
                                folder={entry}
                                assigned={lockedFolderIds.has(entry.id)}
                                selected={selectedFolders.has(entry.id)}
                                onToggle={() => toggleFolder(entry)}
                              />
                            ) : null}
                            <FolderToggle
                              count={ids.length}
                              state={allSelected ? true : someSelected ? 'mixed' : false}
                              label={String(ids.length)}
                              onToggle={() =>
                                toggleIds(
                                  ids.map((id) => ({
                                    id,
                                    title: titles.get(id) ?? String(id),
                                  }))
                                )
                              }
                            />
                          </>
                        )}
                      </div>
                    )
                  })
                : null}
              {!loading
                ? visibleMaterials.map((material) => (
                    <MaterialRow
                      key={material.id}
                      material={material}
                      selected={selected.has(material.id)}
                      onToggle={() => toggleMaterial(material)}
                      locked={assignedIds.has(material.id)}
                      lockedLabel={lockedLabel ?? t('materialPicker.assignedHere')}
                      className={selected.has(material.id) ? 'bg-primary/5' : undefined}
                    />
                  ))
                : null}
              {!loading && location.kind === 'link' && browse.data
                ? browse.data.uningested.map((entry) => (
                    <button
                      key={entry.relpath}
                      type="button"
                      className="border-border hover:bg-subtle flex w-full items-center gap-2 rounded-md border border-dashed px-2 py-1.5 text-left text-sm"
                      onClick={() => void ingestAndSelect(entry.relpath, entry.name)}
                    >
                      {ingesting === entry.relpath ? (
                        <Loader2 className="size-4 shrink-0 animate-spin" aria-hidden />
                      ) : (
                        <Plus className="text-muted-foreground size-4 shrink-0" aria-hidden />
                      )}
                      <span className="text-muted-foreground min-w-0 flex-1 truncate">
                        {entry.name}
                      </span>
                      <span className="bg-warning/15 text-warning shrink-0 rounded-full px-2 py-0.5 text-[10px]">
                        {ingesting === entry.relpath
                          ? t('materialPicker.ingesting')
                          : t('materialPicker.ingestAndSelect')}
                      </span>
                    </button>
                  ))
                : null}
              {!loading && location.kind !== 'link' ? (
                <UploadDropzone
                  upload={upload}
                  variant="row"
                  className="pt-1"
                  label={
                    location.kind === 'folder' && location.folderId !== null
                      ? t('library.uploadToFolder')
                      : t('library.uploadToLibrary')
                  }
                />
              ) : null}
              {emptyList ? (
                <p className="text-muted-foreground p-6 text-center text-sm">
                  {allMaterials.data?.length === 0
                    ? t('materialPicker.empty')
                    : t('materialPicker.emptyFolder')}
                </p>
              ) : null}
              {!loading && location.kind === 'link' && browse.data?.missing_target ? (
                <p className="text-danger p-2 text-xs">
                  {t('library.targetMissing', { path: browse.data.path })}
                </p>
              ) : null}
            </div>
          </div>
        </div>

        <div className="border-border space-y-2 border-t px-5 py-3">
          <ErrorBanner message={actionError} />
          <ErrorBanner message={allocate.isError ? (allocate.error as Error).message : null} />
          {selected.size > 0 || selectedFolders.size > 0 ? (
            <div className="flex flex-wrap gap-1">
              {Array.from(selectedFolders.entries()).map(([id, name]) => (
                <button
                  key={`folder-${id}`}
                  type="button"
                  className="bg-primary/15 text-primary hover:bg-primary/25 flex max-w-56 items-center gap-1 rounded-full px-2 py-0.5 text-[11px]"
                  title={`${name} — ${t('materialPicker.folderChip')}`}
                  onClick={() =>
                    setSelectedFolders((current) => {
                      const next = new Map(current)
                      next.delete(id)
                      return next
                    })
                  }
                >
                  <FolderClosed className="size-3 shrink-0" aria-hidden />
                  <span className="truncate">{name}</span>
                  <X className="size-3 shrink-0" aria-hidden />
                </button>
              ))}
              {Array.from(selected.entries()).map(([id, title]) => (
                <button
                  key={id}
                  type="button"
                  className="bg-primary/10 text-primary hover:bg-primary/20 flex max-w-56 items-center gap-1 rounded-full px-2 py-0.5 text-[11px]"
                  title={title}
                  onClick={() =>
                    setSelected((current) => {
                      const next = new Map(current)
                      next.delete(id)
                      return next
                    })
                  }
                >
                  <span className="truncate">{title}</span>
                  <X className="size-3 shrink-0" aria-hidden />
                </button>
              ))}
            </div>
          ) : null}
          <div className="flex items-center justify-between">
            {location.kind !== 'link' ? (
              <UploadButton upload={upload} variant="outline" label={t('library.upload')} />
            ) : (
              <span className="text-muted-foreground text-xs">
                {t('materialPicker.selectedCount', { count: selected.size })}
              </span>
            )}
            <div className="flex items-center gap-2">
              {location.kind !== 'link' ? (
                <span className="text-muted-foreground text-xs">
                  {t('materialPicker.selectedCount', { count: selected.size })}
                </span>
              ) : null}
              <Button variant="ghost" size="sm" onClick={onClose}>
                {t('settings.cancel')}
              </Button>
              <Button
                size="sm"
                disabled={
                  (selected.size === 0 && selectedFolders.size === 0) ||
                  allocate.isPending
                }
                onClick={() => {
                  if (mode === 'select') {
                    onSelect?.(Array.from(selected.keys()))
                  } else {
                    allocate.mutate()
                  }
                }}
              >
                {allocate.isPending ? (
                  <Loader2 className="animate-spin" aria-hidden />
                ) : null}
                {mode === 'select'
                  ? confirmLabel ?? t('materialPicker.add', { count: selected.size })
                  : selected.size === 0 && selectedFolders.size > 0
                    ? t('materialPicker.allocateFolders', {
                        count: selectedFolders.size,
                      })
                    : t('materialPicker.allocate', { count: selected.size })}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
