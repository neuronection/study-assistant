import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'
import {useNavigate} from '@tanstack/react-router'
import {BookOpen, ChevronRight, ExternalLink, FolderClosed, Loader2, Plus, Upload, X} from 'lucide-react'
import {useCallback, useEffect, useMemo, useRef, useState} from 'react'
import {useTranslation} from 'react-i18next'
import {Button} from '@/components/ui/button'
import {ContextMenu, type ContextMenuItem} from '@/components/ui/ContextMenu'
import {AssignToNodeDialog} from '../AssignToNodeDialog'
import {EmptyState} from '@/components/ui/empty-state'
import {ExpandableSearch} from '@/components/ui/ExpandableSearch'
import {ViewToggle} from '@/components/ui/ViewToggle'
import {useStoredView} from '@/lib/useStoredView'
import {isKeyboardClick, useSelection} from '@/lib/useSelection'
import {MaterialBrowser, MaterialBrowserSkeleton, type MaterialFolderSpec} from '@/components/materials/MaterialBrowser'
import {type Crumb} from '@/features/library/LibraryBreadcrumbs'
import {KindIcon} from '@/features/library/KindIcon'
import {MaterialRow} from '@/components/materials/MaterialRow'
import {MaterialTile} from '@/components/materials/MaterialTile'
import {MaterialUploadDropzone} from '@/components/materials/MaterialUploadDropzone'
import {ReExtractDialog} from '@/components/materials/ReExtractDialog'
import {DiscoverDialog} from '@/features/discovery/DiscoverDialog'
import {useMaterialUpload} from '@/components/materials/materialUpload'
import {useWindowDropRegistration} from '@/lib/window-drop-store'
import {useImportUrlStore} from '@/lib/import-url-store'
import {useCreateMaterialMenu} from '@/components/materials/createMaterialMenu'
import {NewFolderDialog} from '@/components/materials/NewFolderDialog'
import {NewTextFileDialog, type TextFileCreateInput, type TextFileSaveInput} from '@/features/library/NewTextFileDialog'
import {MarqueeSurface} from '@/components/ui/Marquee'
import {fuzzyFilter} from '@/lib/fuzzy'
import {allocateMaterial, allocateNodeFolder, browseSource, createFolder, createTextMaterial, deallocateMaterial, deallocateNodeFolder, deriveMaterials, ingestSourceFile, getPlacementSuggestions, getUnassignedMaterials, mirrorFolder as mirrorFolderApi, listFolders, listMaterials, type Folder, type Material, type WorkspaceFolder, type WorkspaceMaterial, type PlacementSuggestion, type TextFileEditState, updateTextMaterial} from '@/lib/api'
import {cn} from '@/lib/utils'
import {buildDragPayload} from '@/lib/dragPayload'
import {MaterialPickerDialog} from '../MaterialPickerDialog'
import {storageKeys} from '@/lib/constants'
import type { WorkspaceData } from './shared'

function WorkspaceMaterialRow({
  entry,
  onUnassign,
  unassignTitle,
  onOpen,
  onContextMenu,
  selectionState,
  onPointerDown,
  onDragStart,
}: {
  entry: WorkspaceMaterial
  onUnassign?: (materialId: string) => void
  unassignTitle?: string
  onOpen: (materialId: string, event: React.MouseEvent<Element>) => void
  onContextMenu?: (event: React.MouseEvent<HTMLDivElement>) => void
  selectionState?: 'none' | 'selected' | 'cut'
  onPointerDown?: (event: React.MouseEvent<HTMLDivElement>) => void
  onDragStart?: (event: React.DragEvent<HTMLDivElement>) => void
}) {
  const { t } = useTranslation()
  const viaBadge = entry.via_folder_name ? (
    <span
      className="bg-subtle text-muted-foreground flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[10px]"
      title={t('workspace.viaFolderTitle', { name: entry.via_folder_name })}
    >
      <FolderClosed className="size-3" aria-hidden />
      {entry.via_folder_name}
    </span>
  ) : null
  return (
    <MaterialRow
      material={{
        id: entry.material_id,
        title: entry.title,
        kind: entry.kind,
        aiComposed: entry.provenance?.source === 'ai-composed',
        readStatus: entry.read_status,
        progress: entry.progress,
        rationale: entry.rationale ?? undefined,
      }}
      className="group"
      draggable
      onDragStart={onDragStart}
      title={t('workspace.materialDragHint')}
      selectionState={selectionState}
      onMouseDown={onPointerDown}
      onOpen={(event) => onOpen(entry.material_id, event)}      onContextMenu={onContextMenu}
      action={
        <>
          {viaBadge}
          {onUnassign ? (
            <button
              type="button"
              className="text-muted-foreground hidden shrink-0 group-hover:block"
              title={unassignTitle ?? t('courses.deallocate')}
              onClick={() => onUnassign(entry.material_id)}
            >
              <X className="size-3.5" aria-hidden />
            </button>
          ) : null}
        </>
      }
    />
  )
}


export function MaterialsTab({
  courseId,
  currentId,
  workspace,
  folderId,
  onOpenMaterial,
  onOpenFolder,
  onCloseFolder,
}: {
  courseId: string
  currentId: string
  workspace: WorkspaceData
  folderId: string | null
  onOpenMaterial: (materialId: string) => void
  onOpenFolder: (folderId: string) => void
  onCloseFolder: () => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [pickerOpen, setPickerOpen] = useState(false)
  const [reExtractTarget, setReExtractTarget] = useState<string | null>(null)
  const [view, setView] = useStoredView(storageKeys.materialsView, 'list')
  const [menu, setMenu] = useState<{
    x: number
    y: number
    entry: WorkspaceMaterial
    canUnassign: boolean
  } | null>(null)
  const [folderMenu, setFolderMenu] = useState<{
    x: number
    y: number
    folder: WorkspaceFolder
  } | null>(null)
  const [browseFolderMenu, setBrowseFolderMenu] = useState<{
    x: number
    y: number
    folder: Folder
  } | null>(null)
  const [browseMenu, setBrowseMenu] = useState<{
    x: number
    y: number
    material: { id: string; title: string }
  } | null>(null)
  const [assignOpen, setAssignOpen] = useState(false)
  const [textDialog, setTextDialog] = useState<'txt' | 'md' | null>(null)
  const [folderDialog, setFolderDialog] = useState(false)
  const [paneMenu, setPaneMenu] = useState<{ x: number; y: number } | null>(null)
  const [createError, setCreateError] = useState<string | null>(null)
  const [materialQuery, setMaterialQuery] = useState('')
  const [discoverOpen, setDiscoverOpen] = useState(false)
  const [unassignedOpen, setUnassignedOpen] = useState(false)
  const [unassignedTarget, setUnassignedTarget] = useState<string | null>(null)
  const unassigned = useQuery({
    queryKey: ['materials', 'unassigned', courseId],
    queryFn: () => getUnassignedMaterials(courseId),
    enabled: workspace.node.is_root && folderId === null,
  })
  const allFoldersQuery = useQuery({
    queryKey: ['folders', courseId],
    queryFn: () => listFolders(courseId),
    enabled: folderId !== null,
  })
  const folderMaterialsQuery = useQuery({
    queryKey: ['materials', folderId, courseId],
    queryFn: () => listMaterials(folderId!),
    enabled: folderId !== null,
  })
  const allFolders = useMemo(() => allFoldersQuery.data ?? [], [allFoldersQuery.data])
  const browseFolder =
    folderId !== null ? (allFolders.find((entry) => entry.id === folderId) ?? null) : null
  const linkedSourceId = browseFolder?.source_id ?? null
  const [sourceSubdir, setSourceSubdir] = useState('')
  useEffect(() => {
    setSourceSubdir('')
  }, [folderId])
  const sourceBrowseQuery = useQuery({
    queryKey: ['source-browse', linkedSourceId, sourceSubdir],
    queryFn: () => browseSource(linkedSourceId!, sourceSubdir),
    enabled: linkedSourceId !== null,
  })
  const sourceBrowse = linkedSourceId !== null ? (sourceBrowseQuery.data ?? null) : null
  const browseActive =
    folderId !== null && allFoldersQuery.data !== undefined && browseFolder !== null
  const browseSubfolders = useMemo(
    () =>
      browseActive
        ? allFolders
            .filter((entry) => entry.parent_id === folderId)
            .sort((a, b) => a.name.localeCompare(b.name))
        : [],
    [allFolders, browseActive, folderId]
  )
  const browseMaterials = useMemo(
    () => (browseActive ? (folderMaterialsQuery.data ?? []) : []),
    [browseActive, folderMaterialsQuery.data]
  )
  const browseCrumbs: Crumb[] = useMemo(() => {
    if (!browseActive || browseFolder === null) {
      return []
    }
    const items: Crumb[] = [
      {
        key: 'materials-root',
        label: t('workspace.materialsCrumbRoot'),
        onClick: onCloseFolder,
      },
    ]
    if (linkedSourceId !== null) {
      items.push({
        key: `f${browseFolder.id}`,
        label: browseFolder.name,
        onClick: sourceSubdir === '' ? undefined : () => setSourceSubdir(''),
      })
      const parts = sourceSubdir ? sourceSubdir.split('/') : []
      parts.forEach((part, index) => {
        items.push({
          key: `sub-${index}-${part}`,
          label: part,
          onClick: () => setSourceSubdir(parts.slice(0, index + 1).join('/')),
        })
      })
      return items
    }
    const chain: Folder[] = []
    let walker: Folder | null = browseFolder
    while (walker !== null) {
      chain.unshift(walker)
      walker = allFolders.find((entry) => entry.id === walker?.parent_id) ?? null
    }
    return [
      ...items,
      ...chain.map((entry) => ({
        key: `f${entry.id}`,
        label: entry.name,
        onClick:
          entry.id === browseFolder.id
            ? undefined
            : () => {
                if (entry.parent_id === null) {
                  onCloseFolder()
                } else {
                  onOpenFolder(entry.id)
                }
              },
      })),
    ]
  }, [
    browseActive,
    browseFolder,
    allFolders,
    t,
    onCloseFolder,
    onOpenFolder,
    linkedSourceId,
    sourceSubdir,
  ])
  const [suggestions, setSuggestions] = useState<PlacementSuggestion[] | null>(null)
  const [suggestPending, setSuggestPending] = useState(false)
  const suggestPlacementsMutation = async (): Promise<void> => {
    setSuggestPending(true)
    try {
      const result = await getPlacementSuggestions(
        courseId,
        (unassigned.data?.materials ?? []).map((entry) => entry.id),
      )
      setSuggestions(result.suggestions)
    } finally {
      setSuggestPending(false)
    }
  }
  const assignUnassigned = useMutation({
    mutationFn: async ({ nodeId, materialId }: { nodeId: string; materialId: string }) => {
      await allocateMaterial(nodeId, materialId)
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['materials'] })
      await refresh()
    },
    onError: (error: Error) => setCreateError(error.message),
  })
  const normalizedQuery = materialQuery.trim()
  const visibleFolders = useMemo(
    () =>
      normalizedQuery
        ? fuzzyFilter(workspace.folders, normalizedQuery, (folder) => folder.name)
        : workspace.folders,
    [workspace.folders, normalizedQuery]
  )
  const visibleMaterials = useMemo(
    () =>
      normalizedQuery
        ? fuzzyFilter(workspace.materials, normalizedQuery, (entry) => entry.title)
        : workspace.materials,
    [workspace.materials, normalizedQuery]
  )
  const visibleBrowseMaterials = useMemo(
    () =>
      normalizedQuery
        ? fuzzyFilter(browseMaterials, normalizedQuery, (entry) => entry.title)
        : browseMaterials,
    [browseMaterials, normalizedQuery]
  )
  const linkedMaterials = useMemo(
    () =>
      normalizedQuery
        ? fuzzyFilter(sourceBrowse?.materials ?? [], normalizedQuery, (entry) => entry.title)
        : (sourceBrowse?.materials ?? []),
    [sourceBrowse, normalizedQuery]
  )
  const ingestLinked = useMutation({
    mutationFn: ({ sourceId, relpath }: { sourceId: string; relpath: string }) =>
      ingestSourceFile(sourceId, relpath),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['source-browse'] })
    },
    onError: (error: Error) => setCreateError(error.message),
  })

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['node-workspace', String(currentId)] })
    await queryClient.invalidateQueries({ queryKey: ['tree', courseId] })
  }

  const unassign = useMutation({
    mutationFn: (materialId: string) => deallocateMaterial(currentId, materialId),
    onSuccess: () => void refresh(),
  })

  const [deriveNotice, setDeriveNotice] = useState<string | null>(null)
  const derive = useMutation({
    mutationFn: (ids: string[]) => deriveMaterials(ids),
    onSuccess: (result) => {
      void refresh()
      const parts: string[] = []
      if (result.created > 0) {
        parts.push(t('library.deriveBatchSaved', { count: result.created }))
      }
      if (result.deduped > 0) {
        parts.push(t('library.deriveBatchDeduped', { count: result.deduped }))
      }
      if (result.skipped > 0) {
        parts.push(t('library.deriveBatchSkipped', { count: result.skipped }))
      }
      setDeriveNotice(parts.join(' · '))
    },
    onError: (error: Error) => setDeriveNotice(error.message),
  })

  const onCreateText = async (
    input: TextFileCreateInput
  ): Promise<TextFileEditState | null> => {
    const state = await createTextMaterial({
      course_id: courseId,
      folder_id: null,
      filename: input.filename,
      content: input.content,
      description: input.description,
      drawings: input.drawings,
    })
    if (state !== null) {
      await allocateMaterial(currentId, state.materialId)
      await refresh()
      await queryClient.invalidateQueries({ queryKey: ['materials'] })
    }
    return state
  }
  const onSaveText = async (
    input: TextFileSaveInput
  ): Promise<TextFileEditState> => {
    const next = await updateTextMaterial({
      materialId: input.state.materialId,
      content: input.content,
      description: input.description,
      drawings: input.drawings,
    })
    await refresh()
    return next
  }

  const createFolderAndAssign = useMutation({
    mutationFn: async (name: string) => {
      const folder = await createFolder(name, null, courseId)
      await allocateNodeFolder(currentId, folder.id)
      return folder
    },
    onSuccess: async () => {
      setFolderDialog(false)
      setCreateError(null)
      await refresh()
      await queryClient.invalidateQueries({ queryKey: ['folders'] })
    },
    onError: (error: Error) => setCreateError(error.message),
  })

  const unassignFolder = useMutation({
    mutationFn: (folderId: string) => deallocateNodeFolder(currentId, folderId),
    onSuccess: () => void refresh(),
  })

  const assignSelection = useMutation({
    mutationFn: async ({ nodeId }: { nodeId: string }) => {
      for (const materialId of selectedMaterialIds) {
        await allocateMaterial(nodeId, materialId)
      }
      for (const folderId of selectedFolderIds) {
        await allocateNodeFolder(nodeId, folderId)
      }
    },
    onSuccess: async () => {
      setAssignOpen(false)
      await queryClient.invalidateQueries({ queryKey: ['tree'] })
      await queryClient.invalidateQueries({ queryKey: ['node-workspace'] })
    },
  })

  const materialOrder = useMemo(
    () =>
      browseActive
        ? linkedSourceId !== null
          ? linkedMaterials.map((entry) => `m${entry.id}`)
          : [
              ...browseSubfolders.map((entry) => `f${entry.id}`),
              ...visibleBrowseMaterials.map((entry) => `m${entry.id}`),
            ]
        : workspace.materials.map((entry) => `m${entry.material_id}`),
    [
      browseActive,
      linkedSourceId,
      linkedMaterials,
      browseSubfolders,
      visibleBrowseMaterials,
      workspace.materials,
    ]
  )
  const selection = useSelection(materialOrder)
  const selectedMaterialIds = useMemo(
    () =>
      [...selection.selected]
        .filter((key) => key.startsWith('m'))
        .map((key) => key.slice(1)),
    [selection.selected]
  )
  const selectedFolderIds = useMemo(
    () =>
      [...selection.selected]
        .filter((key) => key.startsWith('f'))
        .map((key) => key.slice(1)),
    [selection.selected]
  )
  const liveSelection = useRef(selection.selected)
  liveSelection.current = selection.selected

  const unassignSelected = () => {
    const viaFolder = new Set(workspace.folder_material_ids)
    const materialIds = [...liveSelection.current]
      .filter((key) => key.startsWith('m'))
      .map((key) => key.slice(1))
      .filter((materialId) => !viaFolder.has(materialId))
    for (const materialId of materialIds) {
      unassign.mutate(materialId)
    }
    const folderIds = [...liveSelection.current]
      .filter((key) => key.startsWith('f'))
      .map((key) => key.slice(1))
    for (const folderId of folderIds) {
      unassignFolder.mutate(folderId)
    }
    selection.clear()
  }

  const upload = useMaterialUpload({
    courseId: courseId,
    getTargetNodeId: () => currentId,
    onFolderCreated: async (folder) => {
      await allocateNodeFolder(currentId, folder.id)
      await refresh()
      await queryClient.invalidateQueries({ queryKey: ['folders'] })
    },
    onUploaded: async () => {
      await refresh()
    },
  })

  useWindowDropRegistration(true, workspace.node.title, () => upload)

  const createMenu = useCreateMaterialMenu({
    upload,
    onNewText: (kind) => setTextDialog(kind),
    onNewFolder: () => setFolderDialog(true),
    onNewUrl: () =>
      useImportUrlStore.getState().openImport(undefined, currentId),
    onDiscover: () => setDiscoverOpen(true),
  })

  const openContextMenu = (
    event: React.MouseEvent,
    entry: WorkspaceMaterial,
    canUnassign: boolean,
  ) => {
    event.preventDefault()
    if (!selection.selected.has(`m${entry.material_id}`)) {
      selection.set([`m${entry.material_id}`])
    }
    setMenu({ x: event.clientX, y: event.clientY, entry, canUnassign })
  }

  const openFolderContextMenu = useCallback(
    (event: React.MouseEvent, folder: WorkspaceFolder) => {
      event.preventDefault()
      if (!selection.selected.has(`f${folder.folder_id}`)) {
        selection.set([`f${folder.folder_id}`])
      }
      setFolderMenu({ x: event.clientX, y: event.clientY, folder })
    },
    [selection]
  )

  const openFolderInLibrary = useCallback(
    (folder: WorkspaceFolder) => {
      void navigate({
        to: '/library',
        search: {
          course: courseId,
          folder: folder.folder_id,
          source: folder.source_id ?? undefined,
        },
      })
    },
    [navigate, courseId]
  )

  const openBrowseFolderInLibrary = useCallback(
    (folder: Folder) => {
      void navigate({
        to: '/library',
        search: {
          course: courseId,
          folder: folder.id,
          source: folder.source_id ?? undefined,
        },
      })
    },
    [navigate, courseId]
  )

  const openInLibraryCrumb =
    browseActive && browseFolder !== null ? (
      <Button
        variant="outline"
        size="sm"
        onClick={() => openBrowseFolderInLibrary(browseFolder)}
      >
        <ExternalLink aria-hidden />
        {t('workspace.openFolderInLibrary')}
      </Button>
    ) : undefined

  const folderSpecs: MaterialFolderSpec[] = useMemo(() => {
    if (browseActive) {
      if (linkedSourceId !== null) {
        return (sourceBrowse?.subdirs ?? []).map((entry) => ({
          key: `sub-${entry.name}`,
          name: entry.name,
          onOpen: () =>
            setSourceSubdir(sourceSubdir ? `${sourceSubdir}/${entry.name}` : entry.name),
        }))
      }
      return browseSubfolders.map((entry) => ({
        key: `f${entry.id}`,
        name: entry.name,
        linked: entry.source_id !== null,
        selectionState: selection.selected.has(`f${entry.id}`) ? 'selected' : 'none',
        onPointerDown: (event) => selection.pointerDown(`f${entry.id}`, event),
        onOpen: () => onOpenFolder(entry.id),
        onContextMenu: (event) => {
          event.preventDefault()
          if (!selection.selected.has(`f${entry.id}`)) {
            selection.set([`f${entry.id}`])
          }
          setBrowseFolderMenu({ x: event.clientX, y: event.clientY, folder: entry })
        },
      }))
    }
    return visibleFolders.map((folder) => ({
      key: `f${folder.folder_id}`,
      name: folder.name,
      linked: folder.source_id !== null,
      title: t('workspace.folderMembers', { count: folder.member_count }),
      selectionState: selection.selected.has(`f${folder.folder_id}`) ? 'selected' : 'none',
      onPointerDown: (event) => selection.pointerDown(`f${folder.folder_id}`, event),
      onOpen: () => onOpenFolder(folder.folder_id),
      onContextMenu: (event) => openFolderContextMenu(event, folder),
      gridMeta: (
        <span className="text-muted-foreground text-[10px]">{folder.member_count}</span>
      ),
      trailing: (
        <>
          <span className="text-muted-foreground shrink-0 text-[10px]">
            {folder.member_count}
          </span>
          <button
            type="button"
            className="text-muted-foreground hidden shrink-0 group-hover:block"
            title={t('workspace.unassignFolder')}
            onClick={() => unassignFolder.mutate(folder.folder_id)}
          >
            <X className="size-3.5" aria-hidden />
          </button>
        </>
      ),
    }))
  }, [
    browseActive,
    linkedSourceId,
    sourceBrowse,
    sourceSubdir,
    browseSubfolders,
    selection,
    onOpenFolder,
    visibleFolders,
    t,
    unassignFolder,
    openFolderContextMenu,
  ])

  const renderLinkedEntry = (entry: {
    id: string
    title: string
    kind: string
    status: string
  }) => {
    const key = `m${entry.id}`
    return view === 'grid' ? (
      <MaterialTile
        key={entry.id}
        data-selectable-id={key}
        material={{
          id: entry.id,
          title: entry.title,
          kind: entry.kind,
          status: entry.status,
        }}
        selectionState={selection.selected.has(key) ? 'selected' : 'none'}
        className="w-full"
        onMouseDown={(event) => selection.pointerDown(key, event)}
        onClick={(event) => {
          if (isKeyboardClick(event)) {
            onOpenMaterial(entry.id)
          }
        }}
        onDoubleClick={() => onOpenMaterial(entry.id)}
        onContextMenu={(event) => {
          event.preventDefault()
          setBrowseMenu({
            x: event.clientX,
            y: event.clientY,
            material: entry,
          })
        }}
      />
    ) : (
      <div key={entry.id} data-selectable-id={key}>
        <MaterialRow
          material={{
            id: entry.id,
            title: entry.title,
            kind: entry.kind,
            status: entry.status,
          }}
          selectionState={selection.selected.has(key) ? 'selected' : 'none'}
          onMouseDown={(event) => selection.pointerDown(key, event)}
          onOpen={() => onOpenMaterial(entry.id)}
          action={
            <span className="text-muted-foreground shrink-0 text-xs">{entry.kind}</span>
          }
          onContextMenu={(event) => {
            event.preventDefault()
            setBrowseMenu({
              x: event.clientX,
              y: event.clientY,
              material: entry,
            })
          }}
        />
      </div>
    )
  }

  const renderBrowseEntry = (entry: Material) => {
    const key = `m${entry.id}`
    return view === 'grid' ? (
      <MaterialTile
        key={entry.id}
        data-selectable-id={key}
        material={{
          id: entry.id,
          title: entry.title,
          kind: entry.kind,
          status: entry.status,
          aiComposed: entry.provenance?.source === 'ai-composed',
        }}
        selectionState={selection.selected.has(key) ? 'selected' : 'none'}
        className="w-full"
        onMouseDown={(event) => selection.pointerDown(key, event)}
        onClick={(event) => {
          if (isKeyboardClick(event)) {
            onOpenMaterial(entry.id)
          }
        }}
        onDoubleClick={() => onOpenMaterial(entry.id)}
        onContextMenu={(event) => {
          event.preventDefault()
          if (!selection.selected.has(key)) {
            selection.set([key])
          }
          setBrowseMenu({ x: event.clientX, y: event.clientY, material: entry })
        }}
      />
    ) : (
      <div key={entry.id} data-selectable-id={key}>
        <MaterialRow
          material={{
            id: entry.id,
            title: entry.title,
            kind: entry.kind,
            status: entry.status,
            aiComposed: entry.provenance?.source === 'ai-composed',
          }}
          selectionState={selection.selected.has(key) ? 'selected' : 'none'}
          onMouseDown={(event) => selection.pointerDown(key, event)}
          onOpen={() => onOpenMaterial(entry.id)}
          action={
            <span className="text-muted-foreground shrink-0 text-xs">{entry.kind}</span>
          }
          onContextMenu={(event) => {
            event.preventDefault()
            if (!selection.selected.has(key)) {
              selection.set([key])
            }
            setBrowseMenu({ x: event.clientX, y: event.clientY, material: entry })
          }}
        />
      </div>
    )
  }

  const entryMenu = (
    entry: WorkspaceMaterial,
    canUnassign: boolean,
  ): ContextMenuItem[] => {
    const multi = selection.selected.size > 1
    const items: ContextMenuItem[] = []
    if (!multi) {
      items.push({
        key: 'open',
        label: t('common.open'),
        onSelect: () => onOpenMaterial(entry.material_id),
      })
    }
    const selectedIds = [...selection.selected]
      .filter((key) => key.startsWith('m'))
      .map((key) => key.slice(1))
    const pool =
      multi && selection.selected.has(`m${entry.material_id}`)
        ? selectedIds
        : [entry.material_id]
    const derivable = pool.filter((id) =>
      (workspace.materials ?? []).some(
        (candidate) => candidate.material_id === id && candidate.has_extraction
      )
    )
    if (derivable.length > 0) {
      items.push({
        key: 'derive',
        label: multi
          ? t('library.deriveMany', { count: derivable.length })
          : t('library.deriveMaterial'),
        disabled: derive.isPending,
        onSelect: () => derive.mutate(derivable),
      })
    }
    if (
      !multi &&
      (entry.reextract_modes?.length ?? 0) > 1 &&
      entry.status !== 'pending' &&
      entry.status !== 'processing'
    ) {
      items.push({
        key: 're-extract',
        label: t('reextract.menuEntry'),
        onSelect: () => setReExtractTarget(entry.material_id),
      })
    }
    items.push({
      key: 'assign',
      label: t('workspace.assignSelection'),
      onSelect: () => setAssignOpen(true),
    })
    if (canUnassign && entry.via_folder_id === null) {
      items.push({
        key: 'unassign',
        label: multi ? t('workspace.unassignSelection') : t('courses.deallocate'),
        danger: true,
        onSelect: multi
          ? unassignSelected
          : () => unassign.mutate(entry.material_id),
      })
    }
    return items
  }

  const mirrorFolder = useMutation({
    mutationFn: ({ folderId }: { folderId: string }) =>
      mirrorFolderApi(currentId, folderId),
    onSuccess: () => void refresh(),
  })

  const mirrorFeedback = (
    created: number,
    reused: number,
    skipped: string[],
  ): void => {
    const parts: string[] = []
    if (created > 0) {
      parts.push(t('workspace.mirrorCreated', { count: created }))
    }
    if (reused > 0) {
      parts.push(t('workspace.mirrorReused', { count: reused }))
    }
    if (parts.length === 0) {
      parts.push(t('workspace.mirrorNone'))
    }
    if (skipped.length > 0) {
      parts.push(t('workspace.mirrorSkipped', { count: skipped.length }))
    }
    setDeriveNotice(parts.join(' · '))
  }

  const folderMenuItems = (folder: WorkspaceFolder): ContextMenuItem[] => {
    const multi = selection.selected.size > 1
    const items: ContextMenuItem[] = [
      {
        key: 'open',
        label: t('common.open'),
        onSelect: () => onOpenFolder(folder.folder_id),
      },
      {
        key: 'open-in-library',
        label: t('workspace.openFolderInLibrary'),
        onSelect: () => openFolderInLibrary(folder),
      },
      {
        key: 'assign',
        label: t('workspace.assignSelection'),
        onSelect: () => setAssignOpen(true),
      },
      {
        key: 'mirror',
        label: t('workspace.mirrorFolder'),
        onSelect: () =>
          mirrorFolder.mutate(
            { folderId: folder.folder_id },
            {
              onSuccess: (result) =>
                mirrorFeedback(
                  result.created_nodes,
                  result.reused_nodes,
                  result.skipped_folders ?? [],
                ),
            },
          ),
      },
    ]
    if (multi) {
      items.push({
        key: 'unassign',
        label: t('workspace.unassignSelection'),
        danger: true,
        onSelect: unassignSelected,
      })
    } else {
      items.push({
        key: 'unassign-folder',
        label: t('workspace.unassignFolder'),
        danger: true,
        onSelect: () => unassignFolder.mutate(folder.folder_id),
      })
    }
    return items
  }

  const renderEntry = (entry: WorkspaceMaterial, canUnassign: boolean) => {
    const key = `m${entry.material_id}`
    const materialIds = [...liveSelection.current]
      .filter((entry2) => entry2.startsWith('m'))
      .map((entry2) => entry2.slice(1))
    const dragMaterialIds = selection.selected.has(key)
      ? materialIds
      : [entry.material_id]
    const rowCanUnassign = canUnassign && entry.via_folder_id === null
    return view === 'grid' ? (
      <div
        key={entry.material_id}
        data-selectable-id={key}
        draggable
        onDragStart={(event) =>
          buildDragPayload(event, {
            key,
            id: entry.material_id,
            kind: 'material',
            selected: selection.selected,
            selectedPayload: {
              folderIds: [],
              materialIds: dragMaterialIds,
              noteIds: [],
            },
            setSelection: (keys) => selection.set(keys),
            countLabel: (count) => t('drag.items', { count }),
          })
        }
        title={t('workspace.materialDragHint')}
      >
        <MaterialTile
          material={{
            id: entry.material_id,
            title: entry.title,
            kind: entry.kind,
            aiComposed: entry.provenance?.source === 'ai-composed',
          }}
          selectionState={selection.selected.has(key) ? 'selected' : 'none'}
          className="w-full"
          onMouseDown={(event) => selection.pointerDown(key, event)}
          onClick={(event) => {
            if (isKeyboardClick(event)) {
              onOpenMaterial(entry.material_id)
            }
          }}
          onDoubleClick={() => onOpenMaterial(entry.material_id)}
          onContextMenu={(event) => openContextMenu(event, entry, canUnassign)}
        />
      </div>
    ) : (
      <div key={entry.material_id} data-selectable-id={key}>
        <WorkspaceMaterialRow
          entry={entry}
          selectionState={selection.selected.has(key) ? 'selected' : 'none'}
          onPointerDown={(event) => selection.pointerDown(key, event)}
          onDragStart={(event) =>
            buildDragPayload(event, {
              key,
              id: entry.material_id,
              kind: 'material',
              selected: selection.selected,
              selectedPayload: {
                folderIds: [],
                materialIds: dragMaterialIds,
                noteIds: [],
              },
              setSelection: (keys) => selection.set(keys),
              countLabel: (count) => t('drag.items', { count }),
            })
          }
          onUnassign={
            rowCanUnassign ? (materialId) => unassign.mutate(materialId) : undefined
          }
          onOpen={(materialId) => onOpenMaterial(materialId)}
          onContextMenu={(event) => openContextMenu(event, entry, canUnassign)}
        />
      </div>
    )
  }

  return (
    <MarqueeSurface
      className="min-h-0 flex-1 space-y-4"
      selection={selection}
      clearBlocked={() =>
        menu !== null ||
        folderMenu !== null ||
        browseFolderMenu !== null ||
        browseMenu !== null ||
        paneMenu !== null ||
        textDialog !== null ||
        folderDialog ||
        pickerOpen ||
        assignOpen
      }
      onContextMenu={(event) => {
        if (event.defaultPrevented) {
          return
        }
        const target = event.target as HTMLElement
        if (
          target.closest(
            '[data-selectable-id], button, input, textarea, select, a, [data-no-marquee]'
          ) !== null
        ) {
          return
        }
        event.preventDefault()
        setPaneMenu({ x: event.clientX, y: event.clientY })
      }}
    >
      {createMenu.inputs}
      {!browseActive ? (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            aria-haspopup="menu"
            disabled={upload.uploading}
            onClick={(event) => {
              const rect = event.currentTarget.getBoundingClientRect()
              setPaneMenu({ x: rect.left, y: rect.bottom + 4 })
            }}
          >
            {upload.uploading ? (
              <Loader2 className="animate-spin" aria-hidden />
            ) : (
              <Plus aria-hidden />
            )}
            {t('library.create')}
          </Button>
          <Button variant="outline" size="sm" onClick={() => setPickerOpen(true)}>
            <BookOpen aria-hidden />
            {t('workspace.assignMaterial')}
          </Button>
          {createError !== null ? (
            <p className="text-warning text-xs" role="alert">
              {createError}
            </p>
          ) : null}
          {deriveNotice !== null ? (
            <p className="text-muted-foreground text-xs" role="status">
              {deriveNotice}
            </p>
          ) : null}
        </div>
      ) : null}
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">
            {browseActive && browseFolder !== null
              ? browseFolder.name
              : t('chapter.nodeMaterials')}
          </h2>
          <div className="flex items-center gap-2">
            <ExpandableSearch
              value={materialQuery}
              onChange={setMaterialQuery}
              placeholder={t('workspace.searchPlaceholder')}
              ariaLabel={t('workspace.searchPlaceholder')}
              clearLabel={t('library.clearSearch')}
            />
            <ViewToggle view={view} onChange={setView} />
          </div>
        </div>
        {workspace.node.is_root &&
        (unassigned.data?.count ?? 0) > 0 &&
        !unassignedOpen ? (
          <button
            type="button"
            data-testid="needs-placement-strip"
            className="text-warning hover:bg-subtle flex w-full items-center justify-between rounded-md border border-dashed px-3 py-2 text-xs"
            onClick={() => setUnassignedOpen(true)}
          >
            <span>
              {t('workspace.needsPlacement', { count: unassigned.data?.count ?? 0 })}
            </span>
            <ChevronRight className="size-3.5 shrink-0" aria-hidden />
          </button>
        ) : null}
        {unassignedOpen && workspace.node.is_root ? (
          <div
            data-testid="needs-placement-panel"
            className="border-border space-y-1 rounded-md border border-dashed p-2"
          >
            {(unassigned.data?.materials ?? []).map((entry) => {
              const candidates =
                suggestions?.find((item) => item.material_id === entry.id)
                  ?.candidates ?? []
              return (
                <div key={entry.id} className="flex items-center justify-between gap-2 py-0.5">
                  <span className="min-w-0 flex-1 truncate text-xs">{entry.title}</span>
                  <div className="flex shrink-0 items-center gap-1">
                    {candidates.map((candidate) => (
                      <button
                        key={candidate.node_id}
                        type="button"
                        title={candidate.matched_on.join(', ')}
                        className="border-border hover:bg-subtle text-muted-foreground rounded-md border border-dashed px-1.5 py-0.5 text-[11px]"
                        disabled={assignUnassigned.isPending}
                        onClick={() =>
                          assignUnassigned.mutate(
                            { nodeId: candidate.node_id, materialId: entry.id },
                            {
                              onSuccess: () => setSuggestions(
                                (current) =>
                                  (current ?? []).filter(
                                    (item) => item.material_id !== entry.id,
                                  ),
                              ),
                            },
                          )
                        }
                      >
                        {candidate.breadcrumb.length > 1
                          ? `${candidate.breadcrumb[candidate.breadcrumb.length - 2].title} › ${candidate.node_title}`
                          : candidate.node_title}
                      </button>
                    ))}
                    <Button
                      size="sm"
                      variant="outline"
                      data-testid={`needs-placement-assign-${entry.id}`}
                      onClick={() => setUnassignedTarget(entry.id)}
                    >
                      {t('workspace.assignNeedsPlacement')}
                    </Button>
                  </div>
                </div>
              )
            })}
            <div className="flex items-center justify-between">
              <button
                type="button"
                className="text-muted-foreground text-left text-xs"
                onClick={() =>
                  void suggestPlacementsMutation()
                }
                disabled={suggestPending}
              >
                {suggestPending
                  ? t('workspace.suggestPending')
                  : t('workspace.suggestForAll')}
              </button>
              <button
                type="button"
                className="text-muted-foreground text-left text-xs"
                onClick={() => setUnassignedOpen(false)}
              >
                {t('workspace.needsPlacementCollapse')}
              </button>
            </div>
          </div>
        ) : null}
        {browseActive ? (
          linkedSourceId !== null ? (
            sourceBrowseQuery.isLoading || sourceBrowse === null ? (
              <MaterialBrowserSkeleton view={view} count={6} />
            ) : (
              <MaterialBrowser
                view={view}
                folders={folderSpecs}
                crumbs={browseCrumbs}
                crumbsExtra={openInLibraryCrumb}
                className={view === 'grid' ? 'gap-2' : 'gap-1'}
              >
                {createError !== null ? (
                  <p className="text-warning col-span-full p-2 text-xs" role="alert">
                    {createError}
                  </p>
                ) : null}
                {sourceBrowse.missing_target ? (
                  <p className="text-danger col-span-full flex flex-wrap items-center gap-2 p-2 text-xs">
                    <span>
                      {t('library.targetMissing', { path: sourceBrowse.path })}
                    </span>
                  </p>
                ) : null}
                {sourceBrowse.last_scan_error ? (
                  <p
                    className="text-warning col-span-full p-2 text-xs"
                    title={sourceBrowse.last_scan_error}
                  >
                    {t('library.scanError', { message: sourceBrowse.last_scan_error })}
                  </p>
                ) : null}
                {linkedMaterials.map(renderLinkedEntry)}
                {sourceBrowse.uningested.map((entry) => (
                  <button
                    key={entry.relpath}
                    type="button"
                    className={cn(
                      'group border-border flex cursor-pointer select-none flex-col items-center gap-2 rounded-lg border border-dashed p-3 text-center transition-colors hover:bg-subtle',
                      view === 'list' &&
                        'flex w-full flex-row items-center gap-2 rounded-md px-3 py-2 text-left text-sm'
                    )}
                    title={t('library.ingestHint')}
                    onClick={() =>
                      ingestLinked.mutate({
                        sourceId: linkedSourceId,
                        relpath: entry.relpath,
                      })
                    }
                  >
                    <KindIcon
                      kind="doc"
                      className="text-muted-foreground/60 shrink-0"
                    />
                    <span
                      className={cn(
                        'text-xs',
                        view === 'grid' ? 'line-clamp-2' : 'min-w-0 flex-1 truncate'
                      )}
                    >
                      {entry.name}
                    </span>
                    <span className="bg-warning/15 text-warning shrink-0 rounded-full px-2 py-0.5 text-[10px]">
                      {t('library.pendingIngest')}
                    </span>
                  </button>
                ))}
                {!sourceBrowse.missing_target &&
                sourceBrowse.subdirs.length === 0 &&
                linkedMaterials.length === 0 &&
                sourceBrowse.uningested.length === 0 ? (
                  normalizedQuery ? (
                    <p className="text-muted-foreground py-2 text-center text-sm">
                      {t('workspace.noSearchResults')}
                    </p>
                  ) : (
                    <EmptyState
                      icon={FolderClosed}
                      compact
                      title={t('workspace.folderEmpty')}
                    />
                  )
                ) : null}
              </MaterialBrowser>
            )
          ) : folderMaterialsQuery.isLoading ? (
            <MaterialBrowserSkeleton view={view} count={6} />
          ) : browseSubfolders.length === 0 && visibleBrowseMaterials.length === 0 ? (
            normalizedQuery ? (
              <p className="text-muted-foreground py-2 text-center text-sm">
                {t('workspace.noSearchResults')}
              </p>
            ) : (
              <EmptyState icon={FolderClosed} compact title={t('workspace.folderEmpty')} />
            )
          ) : (
            <MaterialBrowser
              view={view}
              folders={folderSpecs}
              crumbs={browseCrumbs}
              crumbsExtra={openInLibraryCrumb}
            >
              {visibleBrowseMaterials.map(renderBrowseEntry)}
            </MaterialBrowser>
          )
        ) : workspace.materials.length === 0 && workspace.folders.length === 0 ? (
          <EmptyState
            icon={Upload}
            title={t('workspace.uploadEmptyLabel')}
            description={t('workspace.uploadEmptyHint')}
            action={
              <MaterialUploadDropzone
                upload={upload}
                hint={t('workspace.uploadEmptyHint')}
              />
            }
          />
        ) : visibleFolders.length === 0 && visibleMaterials.length === 0 ? (
          <p className="text-muted-foreground py-2 text-center text-sm">
            {t('workspace.noSearchResults')}
          </p>
        ) : (
          <MaterialBrowser view={view} folders={folderSpecs}>
            {visibleMaterials.map((entry) => renderEntry(entry, true))}
          </MaterialBrowser>
        )}
      </div>

      {menu !== null ? (
        <ContextMenu
          x={menu.x}
          y={menu.y}
          items={entryMenu(menu.entry, menu.canUnassign)}
          onClose={() => setMenu(null)}
        />
      ) : null}
      {folderMenu !== null ? (
        <ContextMenu
          x={folderMenu.x}
          y={folderMenu.y}
          items={folderMenuItems(folderMenu.folder)}
          onClose={() => setFolderMenu(null)}
        />
      ) : null}
      {browseFolderMenu !== null ? (
        <ContextMenu
          x={browseFolderMenu.x}
          y={browseFolderMenu.y}
          items={[
            {
              key: 'open',
              label: t('common.open'),
              onSelect: () => onOpenFolder(browseFolderMenu.folder.id),
            },
            {
              key: 'open-in-library',
              label: t('workspace.openFolderInLibrary'),
              onSelect: () => openBrowseFolderInLibrary(browseFolderMenu.folder),
            },
            {
              key: 'assign',
              label: t('workspace.assignSelection'),
              onSelect: () => setAssignOpen(true),
            },
          ]}
          onClose={() => setBrowseFolderMenu(null)}
        />
      ) : null}
      {browseMenu !== null ? (
        <ContextMenu
          x={browseMenu.x}
          y={browseMenu.y}
          items={[
            {
              key: 'open',
              label: t('common.open'),
              onSelect: () => onOpenMaterial(browseMenu.material.id),
            },
            {
              key: 'assign',
              label: t('workspace.assignSelection'),
              onSelect: () => setAssignOpen(true),
            },
          ]}
          onClose={() => setBrowseMenu(null)}
        />
      ) : null}
      {paneMenu !== null ? (
        <ContextMenu
          x={paneMenu.x}
          y={paneMenu.y}
          items={createMenu.items}
          onClose={() => setPaneMenu(null)}
        />
      ) : null}

      {textDialog !== null ? (
        <NewTextFileDialog
          defaultKind={textDialog}
          courseId={courseId}
          onCreate={onCreateText}
          onSave={onSaveText}
          onCancel={() => setTextDialog(null)}
        />
      ) : null}
      {folderDialog ? (
        <NewFolderDialog
          title={t('library.newFolder')}
          namePlaceholder={t('library.folderName')}
          onConfirm={(name) => createFolderAndAssign.mutate(name)}
          onCancel={() => setFolderDialog(false)}
        />
      ) : null}

      {reExtractTarget !== null ? (
        <ReExtractDialog
          materialId={reExtractTarget}
          open
          onClose={() => setReExtractTarget(null)}
          onSuccess={async () => {
            await refresh()
          }}
        />
      ) : null}
      <DiscoverDialog
        open={discoverOpen}
        onClose={() => setDiscoverOpen(false)}
        courseId={courseId}
        nodeId={currentId}
        defaultQuery={workspace.node.is_root ? '' : workspace.node.title}
      />
      {pickerOpen ? (
        <MaterialPickerDialog
          courseId={courseId}
          nodeId={currentId}
          nodeTitle={workspace.node.title}
          assignedIds={new Set([
            ...workspace.materials.map((entry) => entry.material_id),
            ...workspace.folder_material_ids,
          ])}
          assignedFolderIds={
            new Set(workspace.folders.map((entry) => entry.folder_id))
          }
          onClose={() => setPickerOpen(false)}
        />
      ) : null}
      {assignOpen ? (
        <AssignToNodeDialog
          courseId={courseId}
          title={t('assignToNode.title')}
          countText={t('assignToNode.materialCount', {
            count: selection.selected.size,
          })}
          confirmLabel={t('assignToNode.assign')}
          onDone={(nodeId) => assignSelection.mutateAsync({ nodeId })}
          onClose={() => setAssignOpen(false)}
        />
      ) : null}
      {unassignedTarget !== null ? (
        <AssignToNodeDialog
          courseId={courseId}
          title={t('workspace.assignNeedsPlacement')}
          countText={
            (unassigned.data?.materials ?? []).find(
              (entry) => entry.id === unassignedTarget,
            )?.title ?? ''
          }
          confirmLabel={t('assignToNode.assign')}
          onDone={async (nodeId) => {
            await assignUnassigned.mutateAsync({
              nodeId,
              materialId: unassignedTarget,
            })
            setUnassignedTarget(null)
          }}
          onClose={() => setUnassignedTarget(null)}
        />
      ) : null}
    </MarqueeSurface>
  )
}

