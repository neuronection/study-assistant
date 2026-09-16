import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearch } from '@tanstack/react-router'
import {
  ArrowUp,
  ChevronRight,
  GraduationCap,
  Link2,
  Plus,
  RefreshCw,
  Star,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/ui/empty-state'
import { ExpandableSearch } from '@/components/ui/ExpandableSearch'
import { patchMaterial } from '@/lib/api'
import { WorkspaceGate } from '@/components/workspace/WorkspaceGate'
import {
  addSource,
  allocateMaterial,
  allocateNodeFolder,
  browseSource,
  copyMaterial,
  createFolder,
  createTextMaterial,
  deleteFolder,
  deleteMaterial,
  deriveMaterials,
  getFolderDeleteInfo,
  ingestSourceFile,
  listCourses,
  listJobs,
  retryJob,
  reingestMaterial,
  listFolders,
   listMaterials,
   getUnassignedMaterials,
   moveFolder,
   moveMaterial,
   relinkSource,
   renameFolder,
   renameMaterial,
   revealSource,
   scanSource,
   setSourceMirror,
   mirrorBackfillSource,
   search,
   unlinkFolder,
   updateTextMaterial,
 } from '@/lib/api'
import type {
  Folder,
  FolderDeleteInfo,
  JobInfo,
  Material,
  TextFileEditState,
} from '@/lib/api'
import { useClipboardStore } from '@/lib/clipboard-store'
import {
  buildDragPayload as buildDragPayloadShared,
  ITEM_MIME,
  parseDragPayload,
} from '@/lib/dragPayload'
import { useCurrentOrigin } from '@/lib/origin'
import { useConfirm } from '@/lib/use-confirm'
import { cn } from '@/lib/utils'
import { isKeyboardClick, useSelection } from '@/lib/useSelection'
import { useWorkspaceStore } from '@/lib/workspace-store'
import { useImportUrlStore } from '@/lib/import-url-store'
import { getWsClient } from '@/lib/ws-client'

import { LibraryBreadcrumbs, type Crumb } from './LibraryBreadcrumbs'
import { ContextMenu, type ContextMenuItem } from '@/components/ui/ContextMenu'
import { MarqueeBand, useMarquee } from '@/components/ui/Marquee'
import { AskMaterialsDialog } from './AskMaterialsDialog'
import { FolderPickerDialog } from './FolderPickerDialog'
import { FolderDeleteDialog } from './FolderDeleteDialog'

import { KindIcon } from './KindIcon'
import { LinkRefBadge } from './LinkRefBadge'
import { LinkedLocationsDialog } from './LinkedLocationsDialog'
import type { LinkedLocationsTarget } from './LinkedLocationsDialog'
import { NameEditor, normalizeName } from './NameEditor'
import { NewTextFileDialog, type TextFileCreateInput, type TextFileSaveInput } from './NewTextFileDialog'
import { ViewToggle, type LibraryView } from '@/components/ui/ViewToggle'
import {
  MaterialBrowser,
  MaterialBrowserSkeleton,
  folderTileClass,
  folderRowClass,
  type MaterialFolderSpec,
} from '@/components/materials/MaterialBrowser'
import { MaterialRow } from '@/components/materials/MaterialRow'
import { MaterialTile } from '@/components/materials/MaterialTile'
import { ReExtractDialog } from '@/components/materials/ReExtractDialog'
import { useMaterialUpload } from '@/components/materials/materialUpload'
import { useCreateMaterialMenu } from '@/components/materials/createMaterialMenu'
import { DiscoverDialog } from '@/features/discovery/DiscoverDialog'
import { useWindowDropRegistration } from '@/lib/window-drop-store'
import { AssignToNodeDialog } from '@/features/courses/AssignToNodeDialog'
import { storageKeys, WsTopic } from '@/lib/constants'

interface JobProgress {
  progress: number
  stage: string
  status: string
}

interface MenuState {
  x: number
  y: number
  items: ContextMenuItem[]
}

interface LinkState {
  folderId: number
  sourceId: number
  subdir: string
}

const VIEW_KEY = storageKeys.libraryView

function fileBackedKind(entry: { blob_sha: string | null; reextract_modes?: string[] }): boolean {
  return entry.blob_sha !== null && (entry.reextract_modes?.length ?? 0) > 0
}

function selectableModes(entry: { reextract_modes?: string[] }): number {
  return entry.reextract_modes?.length ?? 0
}

function readStoredView(): LibraryView {
  try {
    const raw = window.localStorage.getItem(VIEW_KEY)
    return raw === 'list' ? 'list' : 'grid'
  } catch {
    return 'grid'
  }
}

export function LibraryPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const from = useCurrentOrigin()
  const searchParams = useSearch({ from: '/library' })
  const queryClient = useQueryClient()
  const workspace = useWorkspaceStore()
  const courseId = searchParams.course ?? null
  const folderId = searchParams.folder ?? null
  const [view, setView] = useState<LibraryView>(readStoredView)
  const [unassignedTarget, setUnassignedTarget] = useState<number | null>(null)
  const [menu, setMenu] = useState<MenuState | null>(null)
  const [renamingId, setRenamingId] = useState<number | null>(null)
  const [renameDraft, setRenameDraft] = useState('')
  const [renamingMaterialId, setRenamingMaterialId] = useState<number | null>(null)
  const [materialDraft, setMaterialDraft] = useState('')
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [textDialog, setTextDialog] = useState<'txt' | 'md' | null>(null)
  const [linkPicker, setLinkPicker] = useState(false)
  const [discoverOpen, setDiscoverOpen] = useState(false)
  const [relinkSourceId, setRelinkSourceId] = useState<number | null>(null)
  const [linkState, setLinkState] = useState<LinkState | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [submittedQuery, setSubmittedQuery] = useState('')
  const [confirm, confirmElement] = useConfirm()

  useEffect(() => {
    const id = setTimeout(() => setSubmittedQuery(searchQuery.trim()), 250)
    return () => clearTimeout(id)
  }, [searchQuery])
  const [job, setJob] = useState<JobProgress | null>(null)
  const [uploadJobId, setUploadJobId] = useState<number | null>(null)
  const jobHideTimer = useRef<number | null>(null)
  const clearJobHideTimer = (): void => {
    if (jobHideTimer.current !== null) {
      clearTimeout(jobHideTimer.current)
      jobHideTimer.current = null
    }
  }
  const [notice, setNotice] = useState<string | null>(null)
  const [folderDeleteTarget, setFolderDeleteTarget] = useState<{
    folder: Folder
    info: FolderDeleteInfo
  } | null>(null)

  useEffect(() => {
    if (searchParams.course === undefined && workspace.courseId !== null) {
      void navigate({ to: '/library', search: { course: workspace.courseId }, replace: true })
    }
  }, [searchParams.course, workspace.courseId, navigate])

  useEffect(() => {
    try {
      window.localStorage.setItem(VIEW_KEY, view)
    } catch {
      // view preference is best-effort only
    }
  }, [view])

  const courses = useQuery({ queryKey: ['courses'], queryFn: listCourses })
  const course = (courses.data ?? []).find((entry) => entry.id === courseId) ?? null
  const folders = useQuery({
    queryKey: ['folders', courseId],
    queryFn: () => listFolders(courseId ?? undefined),
    enabled: courseId !== null,
  })
  const allFolders = useMemo(() => folders.data ?? [], [folders.data])
  const currentFolder = allFolders.find((entry) => entry.id === folderId) ?? null
  const dropTargetLabel = course?.title ?? t('library.title')

  useEffect(() => {
    if (linkState !== null) {
      return
    }
    if (searchParams.source === undefined || searchParams.folder === undefined) {
      return
    }
    const folder = allFolders.find(
      (entry) =>
        entry.id === searchParams.folder && entry.source_id === searchParams.source
    )
    if (folder && folder.source_id !== null) {
      setLinkState({ folderId: folder.id, sourceId: folder.source_id, subdir: '' })
    }
  }, [searchParams.source, searchParams.folder, allFolders, linkState])
  const materials = useQuery({
    queryKey: ['materials', folderId, courseId],
    queryFn: () =>
      folderId !== null
        ? listMaterials(folderId)
        : courseId !== null
          ? listMaterials(undefined, courseId, true)
          : Promise.resolve([]),
    enabled: courseId !== null && linkState === null,
  })
  const unassigned = useQuery({
    queryKey: ['materials', 'unassigned', courseId],
    queryFn: () => getUnassignedMaterials(courseId as number),
    enabled: courseId !== null && linkState === null,
  })
  const [starredOnly, setStarredOnly] = useState(false)
  const [tagFilter, setTagFilter] = useState<string | null>(null)
  const starMutation = useMutation({
    mutationFn: async ({ ids, starred }: { ids: number[]; starred: boolean }) => {
      await Promise.all(ids.map((id) => patchMaterial(id, { starred })))
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['materials'] })
      await queryClient.invalidateQueries({ queryKey: ['material'] })
    },
  })
  const browse = useQuery({
    queryKey: ['source-browse', linkState?.sourceId ?? 0, linkState?.subdir ?? ''],
    queryFn: () => browseSource(linkState?.sourceId as number, linkState?.subdir ?? ''),
    enabled: linkState !== null,
  })
  const searchResults = useQuery({
    queryKey: ['search', courseId, submittedQuery],
    queryFn: () => search(submittedQuery, courseId ?? undefined),
    enabled: submittedQuery.length > 0,
  })

  const refreshFolders = () =>
    queryClient.invalidateQueries({ queryKey: ['folders', courseId] })
  const refreshBrowse = () =>
    queryClient.invalidateQueries({ queryKey: ['source-browse'] })
  const refreshMaterials = () => {
    void queryClient.invalidateQueries({ queryKey: ['materials'] })
    void queryClient.invalidateQueries({ queryKey: ['courses'] })
    void refreshBrowse()
  }

  const createFolderMutation = useMutation({
    mutationFn: () => {
      if (courseId === null) {
        throw new Error(t('library.needsCourse'))
      }
      return createFolder(newName.trim(), folderId, courseId)
    },
    onSuccess: async () => {
      setCreating(false)
      setNewName('')
      await refreshFolders()
    },
  })
  const renameFolderMutation = useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) => renameFolder(id, name),
    onSuccess: () => void refreshFolders(),
  })
  const renameMaterialMutation = useMutation({
    mutationFn: ({ id, title }: { id: number; title: string }) =>
      renameMaterial(id, title),
    onSuccess: () => refreshMaterials(),
  })
  const deleteFolderMutation = useMutation({
    mutationFn: ({ id, force }: { id: number; force: boolean }) => deleteFolder(id, force),
    onSuccess: async () => {
      if (folderId !== null) {
        await navigate({
          to: '/library',
          search: { course: courseId ?? undefined, folder: undefined },
        })
      }
      await queryClient.invalidateQueries({ queryKey: ['materials'] })
      await refreshFolders()
    },
    onError: (error: Error) => setNotice(error.message),
  })
  const deleteMaterialMutation = useMutation({
    mutationFn: (id: number) => deleteMaterial(id),
    onSuccess: () => refreshMaterials(),
    onError: (error: Error) => setNotice(error.message),
  })
  const reingestMutation = useMutation({
    mutationFn: async (ids: number[]) => {
      const jobs = []
      for (const id of ids) {
        jobs.push(await reingestMaterial(id))
      }
      return jobs
    },
    onSuccess: () => {
      refreshMaterials()
    },
    onError: (error: Error) => setNotice(error.message),
  })
  const deriveMutation = useMutation({
    mutationFn: (ids: number[]) => deriveMaterials(ids),
    onSuccess: (result) => {
      refreshMaterials()
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
      setNotice(parts.join(' · '))
    },
    onError: (error: Error) => setNotice(error.message),
  })
  const jobRetryMutation = useMutation({
    mutationFn: async ({ materialId }: { materialId: number }) => {
      const jobs = await listJobs({ status: 'failed', limit: 200 })
      const failedJobs = jobs.filter(
        (job) =>
          job.status === 'failed' &&
          job.retriable &&
          job.material_id === materialId
      )
      for (const job of failedJobs) {
        await retryJob(job.id)
      }
      return failedJobs.length
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['jobs-summary'] }),
    onError: (error: Error) => setNotice(error.message),
  })
  const onCreateText = async (
    input: TextFileCreateInput
  ): Promise<TextFileEditState | null> => {
    if (courseId === null) {
      throw new Error(t('library.needsCourse'))
    }
    const state = await createTextMaterial({
      course_id: courseId,
      folder_id: folderId,
      filename: input.filename,
      content: input.content,
      description: input.description,
      drawings: input.drawings,
    })
    if (state !== null) {
      if (state.jobId !== null) {
        clearJobHideTimer()
        setUploadJobId(state.jobId)
        setJob({ progress: 0, stage: 'ingesting', status: 'queued' })
      }
      await refreshMaterials()
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
    await refreshMaterials()
    return next
  }
  const addSourceMutation = useMutation({
    mutationFn: (path: string) =>
      addSource({
        label: path.split('/').filter(Boolean).pop() ?? 'link',
        path,
        course_id: courseId as number,
      }),
    onSuccess: async () => {
      setLinkPicker(false)
      await refreshFolders()
      await queryClient.invalidateQueries({ queryKey: ['sources'] })
    },
    onError: (error: Error) => setNotice(error.message),
  })
  const relinkMutation = useMutation({
    mutationFn: ({ id, path }: { id: number; path: string }) => relinkSource(id, path),
    onSuccess: async () => {
      setRelinkSourceId(null)
      await refreshBrowse()
      await queryClient.invalidateQueries({ queryKey: ['sources'] })
    },
    onError: (error: Error) => setNotice(error.message),
  })
  const ingestMutation = useMutation({
    mutationFn: ({ sourceId, relpath }: { sourceId: number; relpath: string }) =>
      ingestSourceFile(sourceId, relpath),
    onSuccess: () => refreshMaterials(),
    onError: (error: Error) => setNotice(error.message),
  })
  const scanMutation = useMutation({
    mutationFn: (sourceId: number) => scanSource(sourceId),
    onSuccess: async (result) => {
      const extra =
        result.new_relpaths && result.new_relpaths.length > 0
          ? ' · ' + t('sources.newFiles', { files: result.new_relpaths.join(', ') })
          : ''
      setNotice(
        t('sources.scanResult', {
          added: result.stats.new,
          updated: result.stats.updated,
          missing: result.stats.missing,
        }) + extra
      )
      await refreshMaterials()
      await refreshFolders()
      await queryClient.invalidateQueries({ queryKey: ['sources'] })
    },
    onError: (error: Error) => setNotice(error.message),
  })
  const toggleMirrorMutation = useMutation({
    mutationFn: ({ sourceId, mirror }: { sourceId: number; mirror: boolean }) =>
      setSourceMirror(sourceId, mirror),
    onSuccess: async (source) => {
      setNotice(
        source.mirror_subdirs
          ? t('sources.mirrorEnabled')
          : t('sources.mirrorDisabled')
      )
      await queryClient.invalidateQueries({ queryKey: ['sources'] })
    },
    onError: (error: Error) => setNotice(error.message),
  })
  const mirrorBackfillMutation = useMutation({
    mutationFn: (sourceId: number) => mirrorBackfillSource(sourceId),
    onSuccess: async (result) => {
      setNotice(
        t('sources.mirrorBackfilled', {
          count: result.stats.backfilled ?? 0,
        })
      )
      await refreshMaterials()
      await refreshFolders()
      await queryClient.invalidateQueries({ queryKey: ['sources'] })
    },
    onError: (error: Error) => setNotice(error.message),
  })
  const revealMutation = useMutation({
    mutationFn: (sourceId: number) => revealSource(sourceId),
    onError: (error: Error) => setNotice(error.message),
  })
  const unlinkMutation = useMutation({
    mutationFn: (folderIdToDelete: number) => unlinkFolder(folderIdToDelete),
    onSuccess: async () => {
      setLinkState(null)
      await refreshMaterials()
      await refreshFolders()
      await queryClient.invalidateQueries({ queryKey: ['sources'] })
    },
  })

  const upload = useMaterialUpload({
    courseId,
    getFolderId: () => folderId,
    onUploaded: async (result) => {
      if (result.job_id !== null) {
        clearJobHideTimer()
        setUploadJobId(result.job_id)
        setJob({ progress: 0, stage: 'uploading', status: 'queued' })
      }
      await refreshMaterials()
    },
  })
  useWindowDropRegistration(courseId !== null, dropTargetLabel, () => upload)


  useEffect(() => () => clearJobHideTimer(), [])

  useEffect(() => {
    if (uploadJobId === null) {
      return
    }
    const unsubscribe = getWsClient().subscribe(WsTopic.jobs(uploadJobId), (payload) => {
      const progress = payload as JobProgress
      setJob(progress)
      if (
        progress.status === 'done' ||
        progress.status === 'failed' ||
        progress.status === 'cancelled'
      ) {
        void queryClient.invalidateQueries({ queryKey: ['materials'] })
        void queryClient.invalidateQueries({ queryKey: ['source-browse'] })
        clearJobHideTimer()
        jobHideTimer.current = window.setTimeout(() => {
          setJob(null)
          setUploadJobId(null)
        }, 1500)
      }
    })
    return () => {
      unsubscribe()
    }
  }, [uploadJobId, queryClient])


  const childFolders = useMemo(
    () =>
      allFolders
        .filter((entry) =>
          folderId === null ? entry.parent_id === null : entry.parent_id === folderId
        )
        .sort((a, b) => a.name.localeCompare(b.name)),
    [allFolders, folderId]
  )

  const shownMaterials = useMemo(
    () =>
      (materials.data ?? []).filter(
        (entry) =>
          (!starredOnly || entry.starred === true) &&
          (tagFilter === null || (entry.tags ?? []).includes(tagFilter)),
      ),
    [materials.data, starredOnly, tagFilter]
  )
  const allTags = useMemo(
    () =>
      Array.from(
        new Set((materials.data ?? []).flatMap((entry) => entry.tags ?? [])),
      ).sort(),
    [materials.data]
  )
  const visibleMaterialIds = useMemo(
    () => shownMaterials.map((entry) => entry.id),
    [shownMaterials]
  )
  const order = useMemo(
    () => [
      ...childFolders.map((entry) => `f${entry.id}`),
      ...visibleMaterialIds.map((id) => `m${id}`),
    ],
    [childFolders, visibleMaterialIds]
  )
  const selection = useSelection(order)
  const selectedFolderIds = useMemo(
    () =>
      [...selection.selected]
        .filter((key) => key.startsWith('f'))
        .map((key) => Number(key.slice(1))),
    [selection.selected]
  )
  const selectedMaterialIds = useMemo(
    () =>
      [...selection.selected]
        .filter((key) => key.startsWith('m'))
        .map((key) => Number(key.slice(1))),
    [selection.selected]
  )
  const clipboardItem = useClipboardStore((state) => state.item)
  const [assignOpen, setAssignOpen] = useState(false)
  const [askMaterialsOpen, setAskMaterialsOpen] = useState<Material[] | null>(null)
  const [reExtractTarget, setReExtractTarget] = useState<number | null>(null)
  const [linkedTarget, setLinkedTarget] = useState<LinkedLocationsTarget | null>(null)
  const [assignFoldersOpen, setAssignFoldersOpen] = useState(false)
  const [dropTarget, setDropTarget] = useState<number | null>(null)
  const paneRef = useRef<HTMLDivElement>(null)

  const goToCourse = useCallback(
    (id: number | null) => {
      workspace.setCourse(id)
      setLinkState(null)
      selection.clear()
      void navigate({ to: '/library', search: { course: id ?? undefined, folder: undefined } })
    },
    [navigate, workspace, selection]
  )

  const goToFolder = useCallback(
    (id: number | null) => {
      setLinkState(null)
      selection.clear()
      void navigate({
        to: '/library',
        search: { course: courseId ?? undefined, folder: id ?? undefined },
      })
    },
    [navigate, courseId, selection]
  )

  const moveMaterialMutation = useMutation({
    mutationFn: ({ id, target }: { id: number; target: number | null }) =>
      moveMaterial(id, target),
    onSuccess: () => refreshMaterials(),
    onError: (error: Error) => setNotice(error.message),
  })
  const copyMaterialMutation = useMutation({
    mutationFn: ({ id, target }: { id: number; target: number | null }) =>
      copyMaterial(id, target),
    onSuccess: () => refreshMaterials(),
    onError: (error: Error) => setNotice(error.message),
  })
  const moveFolderMutation = useMutation({
    mutationFn: ({ id, parentId }: { id: number; parentId: number | null }) =>
      moveFolder(id, parentId),
    onSuccess: () => void refreshFolders(),
    onError: (error: Error) => setNotice(error.message),
  })
  const assignMutation = useMutation({
    mutationFn: async ({ nodeId, materialIds }: { nodeId: number; materialIds: number[] }) => {
      for (const materialId of materialIds) {
        await allocateMaterial(nodeId, materialId)
      }
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['tree'] })
      await queryClient.invalidateQueries({ queryKey: ['node-workspace'] })
      await queryClient.invalidateQueries({ queryKey: ['materials'] })
      setNotice(t('library.assignedToNode'))
    },
    onError: (error: Error) => setNotice(error.message),
  })
  const assignFoldersMutation = useMutation({
    mutationFn: async ({ nodeId, folderIds }: { nodeId: number; folderIds: number[] }) => {
      for (const folderId of folderIds) {
        await allocateNodeFolder(nodeId, folderId)
      }
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['tree'] })
      await queryClient.invalidateQueries({ queryKey: ['node-workspace'] })
      setNotice(t('library.assignedToNode'))
    },
    onError: (error: Error) => setNotice(error.message),
  })

  const clipboardIds = () => {
    const item = useClipboardStore.getState().item
    return item !== null && item.kind === 'library' ? item : null
  }

  const liveSelection = useRef(selection.selected)
  liveSelection.current = selection.selected

  const liveSelectedIds = () => {
    const folderIds: number[] = []
    const materialIds: number[] = []
    for (const key of liveSelection.current) {
      if (key.startsWith('f')) {
        folderIds.push(Number(key.slice(1)))
      } else if (key.startsWith('m')) {
        materialIds.push(Number(key.slice(1)))
      }
    }
    return { folderIds, materialIds }
  }

  const cutSelection = () => {
    const { folderIds, materialIds } = liveSelectedIds()
    if (folderIds.length === 0 && materialIds.length === 0) {
      return
    }
    useClipboardStore.getState().set({
      kind: 'library',
      courseId: courseId as number,
      folderIds,
      materialIds,
      mode: 'cut',
    })
  }

  const copySelection = () => {
    const { materialIds } = liveSelectedIds()
    if (materialIds.length === 0) {
      return
    }
    useClipboardStore.getState().set({
      kind: 'library',
      courseId: courseId as number,
      folderIds: [],
      materialIds,
      mode: 'copy',
    })
  }

  const pasteInto = async (target: number | null) => {
    const item = clipboardIds()
    if (item === null || item.courseId !== courseId) {
      return
    }
    try {
      if (item.mode === 'cut') {
        for (const id of item.folderIds) {
          await moveFolderMutation.mutateAsync({ id, parentId: target })
        }
        for (const id of item.materialIds) {
          await moveMaterialMutation.mutateAsync({ id, target })
        }
        useClipboardStore.getState().clear()
      } else {
        for (const id of item.materialIds) {
          await copyMaterialMutation.mutateAsync({ id, target })
        }
      }
      selection.clear()
    } catch {
      // per-mutation onError surfaces the message
    }
  }

  const deleteSelection = async () => {
    const { folderIds, materialIds } = liveSelectedIds()
    if (folderIds.length === 0 && materialIds.length === 0) {
      return
    }
    const ok = await confirm({
      title: t('common.remove'),
      description: t('library.confirmDeleteSelection'),
      confirmLabel: t('common.remove'),
      cancelLabel: t('common.cancel'),
      destructive: true,
    })
    if (!ok) {
      return
    }
    for (const id of materialIds) {
      deleteMaterialMutation.mutate(id)
    }
    for (const id of folderIds) {
      deleteFolderMutation.mutate({ id, force: false })
    }
    selection.clear()
  }

  const requestFolderDelete = async (folder: Folder) => {
    try {
      const info = await getFolderDeleteInfo(folder.id)
      setFolderDeleteTarget({ folder, info })
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error))
    }
  }

  const hasSelection =
    selectedFolderIds.length > 0 || selectedMaterialIds.length > 0

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (
        menu !== null ||
        textDialog !== null ||
        linkPicker ||
        relinkSourceId !== null ||
        assignOpen ||
        folderDeleteTarget !== null
      ) {
        return
      }
      const target = event.target
      if (
        target instanceof Element &&
        target.closest('input, textarea, select, [contenteditable="true"]') !== null
      ) {
        return
      }
      if (event.key === 'Escape') {
        selection.clear()
        return
      }
      if (!hasSelection && !clipboardIds()) {
        return
      }
      if (searching || courseId === null || inLink) {
        return
      }
      const mod = event.ctrlKey || event.metaKey
      const key = event.key.toLowerCase()
      if (!mod && event.key === 'Enter' && selection.selected.size === 1) {
        const selectedKey = [...selection.selected][0]
        if (selectedKey.startsWith('f')) {
          const folder = allFolders.find((entry) => entry.id === Number(selectedKey.slice(1)))
          if (folder !== undefined) {
            event.preventDefault()
            openLinkFolder(folder)
          }
        } else if (selectedKey.startsWith('m')) {
          event.preventDefault()
          void navigate({
            to: '/library/$materialId',
            search: { from },
            params: { materialId: selectedKey.slice(1) },
          })
        }
        return
      }
      if (mod && key === 'x') {
        event.preventDefault()
        cutSelection()
      } else if (mod && key === 'c') {
        event.preventDefault()
        copySelection()
      } else if (mod && key === 'v') {
        event.preventDefault()
        void pasteInto(folderId)
      } else if (!mod && (event.key === 'Delete' || event.key === 'Backspace')) {
        event.preventDefault()
        void deleteSelection()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  useEffect(() => {
    if (!hasSelection) {
      return
    }
    const valid = new Set(order)
    const stale = [...selection.selected].filter((key) => !valid.has(key))
    if (stale.length > 0) {
      selection.set([...selection.selected].filter((key) => valid.has(key)))
    }
    // selection invalidation on data refresh; full deps intentionally
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [order.join(',')])

  const linkFolder = useMemo(
    () =>
      linkState === null
        ? null
        : allFolders.find((entry) => entry.id === linkState.folderId) ?? null,
    [allFolders, linkState]
  )

  const crumbs: Crumb[] = useMemo(() => {
    const items: Crumb[] = [
      { key: 'home', label: t('library.home'), onClick: () => goToCourse(null) },
    ]
    if (course !== null) {
      items.push({ key: 'course', label: course.title, onClick: () => goToFolder(null) })
      const chain: Folder[] = []
      let walker: Folder | null | undefined = currentFolder
      while (walker != null) {
        chain.unshift(walker)
        walker = allFolders.find((entry) => entry.id === walker?.parent_id) ?? null
      }
      for (const entry of chain) {
        items.push({
          key: `folder-${entry.id}`,
          label: entry.name,
          onClick: () => goToFolder(entry.id),
        })
      }
    }
    if (linkState !== null && linkFolder !== null) {
      if (!items.some((item) => item.key === `folder-${linkFolder.id}`)) {
        items.push({
          key: `folder-${linkFolder.id}`,
          label: linkFolder.name,
          onClick: () => setLinkState({ ...linkState, subdir: '' }),
        })
      }
      const parts = linkState.subdir ? linkState.subdir.split('/') : []
      parts.forEach((part, index) => {
        items.push({
          key: `sub-${index}-${part}`,
          label: part,
          onClick: () =>
            setLinkState({ ...linkState, subdir: parts.slice(0, index + 1).join('/') }),
        })
      })
    }
    return items
  }, [course, currentFolder, allFolders, t, goToCourse, goToFolder, linkState, linkFolder])

  const openLinkFolder = (entry: Folder) => {
    if (entry.source_id === null) {
      goToFolder(entry.id)
      return
    }
    setLinkState({ folderId: entry.id, sourceId: entry.source_id, subdir: '' })
  }


  const folderMenu = (entry: Folder): ContextMenuItem[] => {
    const selectionKeys = [...selection.selected]
    if (!selectionKeys.includes(`f${entry.id}`)) {
      selection.set([`f${entry.id}`])
    }
    const pasteable =
      clipboardItem !== null &&
      clipboardItem.kind === 'library' &&
      clipboardItem.courseId === courseId
    if (entry.source_id !== null) {
      return [
        { key: 'open', label: t('library.openFolder'), onSelect: () => openLinkFolder(entry) },
        {
          key: 'rescan',
          label: t('library.rescan'),
          onSelect: () => scanMutation.mutate(entry.source_id as number),
        },
        {
          key: 'mirror-toggle',
          label: t('sources.mirrorToggleOn'),
          onSelect: () =>
            toggleMirrorMutation.mutate({
              sourceId: entry.source_id as number,
              mirror: true,
            }),
        },
        {
          key: 'mirror-now',
          label: t('sources.mirrorNow'),
          onSelect: () => mirrorBackfillMutation.mutate(entry.source_id as number),
        },
        {
          key: 'reveal',
          label: t('library.revealOnDisk'),
          onSelect: () => revealMutation.mutate(entry.source_id as number),
        },
        {
          key: 'assign',
          label: t('library.assignFolderToNode'),
          onSelect: () => setAssignFoldersOpen(true),
        },
        {
          key: 'linked-locations',
          label: t('library.linkedLocationsMenu'),
          onSelect: () =>
            setLinkedTarget({ kind: 'folder', id: entry.id, title: entry.name }),
        },
        {
          key: 'rename',
          label: t('library.renameFolder'),
          onSelect: () => {
            setRenamingId(entry.id)
            setRenameDraft(entry.name)
          },
        },
        {
          key: 'unlink',
          label: t('library.unlinkFolder'),
          danger: true,
          onSelect: async () => {
            const ok = await confirm({
              title: t('library.unlinkFolder'),
              description: t('library.confirmUnlink'),
              confirmLabel: t('library.unlinkFolder'),
              cancelLabel: t('common.cancel'),
              destructive: true,
            })
            if (ok) unlinkMutation.mutate(entry.id)
          },
        },
      ]
    }
    return [
      { key: 'open', label: t('library.openFolder'), onSelect: () => goToFolder(entry.id) },
      {
        key: 'cut',
        label: t('library.cut'),
        onSelect: cutSelection,
      },
      {
        key: 'copy',
        label: t('library.copyFolder'),
        disabled: true,
        hint: t('library.copyFolderUnsupported'),
      },
      {
        key: 'assign',
        label: t('library.assignFolderToNode'),
        onSelect: () => setAssignFoldersOpen(true),
      },
      {
        key: 'linked-locations',
        label: t('library.linkedLocationsMenu'),
        onSelect: () =>
          setLinkedTarget({ kind: 'folder', id: entry.id, title: entry.name }),
      },
      {
        key: 'paste-into',
        label: t('library.pasteInto'),
        disabled: !pasteable,
        onSelect: () => void pasteInto(entry.id),
      },
      {
        key: 'rename',
        label: t('library.renameFolder'),
        onSelect: () => {
          setRenamingId(entry.id)
          setRenameDraft(entry.name)
        },
      },
      {
        key: 'delete',
        label: t('library.deleteFolder'),
        danger: true,
        onSelect: () => {
          void requestFolderDelete(entry)
        },
      },
    ]
  }

  const hasFailedJobs = (materialId: number): boolean => {
    const cached = queryClient.getQueryData<JobInfo[]>(['jobs-list', 'failed'])
    if (cached === undefined) {
      return false
    }
    return cached.some((job) => job.status === 'failed' && job.retriable && job.material_id === materialId)
  }

  const materialMenu = (id: number, title: string): ContextMenuItem[] => {
    const wasSelected = selection.selected.has(`m${id}`)
    const keys = wasSelected ? [...selection.selected] : [`m${id}`]
    if (!wasSelected) {
      selection.set([`m${id}`])
    }
    const multi = keys.length > 1
    const effectiveIds = keys
      .filter((key) => key.startsWith('m'))
      .map((key) => Number(key.slice(1)))
    const selected = effectiveIds.map((mid) =>
      (materials.data ?? []).find((entry) => entry.id === mid)
    )
    const fileBacked = selected.filter(
      (entry) => entry !== undefined && fileBackedKind(entry),
    )
    const derivable = selected.flatMap((entry) =>
      entry !== undefined && entry.has_extraction ? [entry.id] : []
    )
    const items: ContextMenuItem[] = []
    const askTargets = selected.flatMap((entry) => (entry !== undefined ? [entry] : []))
    if (askTargets.length > 0) {
      items.push({
        key: 'ask-ai',
        label:
          askTargets.length === 1
            ? t('library.askAiMenuOne')
            : t('library.askAiMenuMany', { count: askTargets.length }),
        onSelect: () => setAskMaterialsOpen(askTargets),
      })
    }
    if (!multi) {
      items.push({
        key: 'open',
        label: t('library.openMaterial'),
        onSelect: () =>
          void navigate({
            to: '/library/$materialId',
            search: { from },
            params: { materialId: String(id) },
          }),
      })
      items.push({
        key: 'linked-locations',
        label: t('library.linkedLocationsMenu'),
        onSelect: () =>
          setLinkedTarget({
            kind: 'material',
            id,
            title: (materials.data ?? []).find((entry) => entry.id === id)?.title ?? title,
          }),
      })
    }
    if (fileBacked.length > 0) {
      const singleModeTarget =
        !multi &&
        fileBacked.length === 1 &&
        fileBacked[0] !== undefined &&
        selectableModes(fileBacked[0]) > 1
          ? fileBacked[0]
          : null
      items.push({
        key: 'reingest',
        label: singleModeTarget
          ? t('reextract.menuEntry')
          : fileBacked.length === 1
            ? t('jobs.reingestOne')
            : t('jobs.reingestMany', { count: fileBacked.length }),
        disabled: reingestMutation.isPending,
        onSelect: () => {
          if (singleModeTarget) {
            setReExtractTarget(singleModeTarget.id)
            return
          }
          const ids = fileBacked.flatMap((entry) =>
            entry !== undefined ? [entry.id] : []
          )
          if (ids.length > 0) {
            reingestMutation.mutate(ids)
          }
        },
      })
      if (!multi && hasFailedJobs(id)) {
        items.push({
          key: 'retry-failed-jobs',
          label: t('jobs.retryFailedForMaterial'),
          disabled: jobRetryMutation.isPending,
          onSelect: () => jobRetryMutation.mutate({ materialId: id }),
        })
      }
    }
    if (derivable.length > 0) {
      items.push({
        key: 'derive',
        label: multi
          ? t('library.deriveMany', { count: derivable.length })
          : t('library.deriveMaterial'),
        disabled: deriveMutation.isPending,
        onSelect: () => deriveMutation.mutate(derivable),
      })
    }
    if (effectiveIds.length > 0) {
      const allStarred = effectiveIds.every(
        (mid) => (materials.data ?? []).find((entry) => entry.id === mid)?.starred
      )
      items.push({
        key: 'star',
        label: allStarred
          ? multi
            ? t('library.unstarMany', { count: effectiveIds.length })
            : t('library.unstarOne')
          : multi
            ? t('library.starMany', { count: effectiveIds.length })
            : t('library.starOne'),
        disabled: starMutation.isPending,
        onSelect: () => starMutation.mutate({ ids: effectiveIds, starred: !allStarred }),
      })
    }
    items.push(
      {
        key: 'cut',
        label: t('library.cut'),
        onSelect: cutSelection,
      },
      {
        key: 'copy',
        label: t('library.copy'),
        onSelect: copySelection,
      },
      {
        key: 'assign',
        label: t('library.assignToNode'),
        onSelect: () => setAssignOpen(true),
      },
      {
        key: 'rename',
        label: t('library.renameMaterial'),
        disabled: multi,
        onSelect: () => {
          setRenamingMaterialId(id)
          setMaterialDraft(title)
        },
      },
      {
        key: 'delete',
        label: t('library.deleteMaterial'),
        danger: true,
        onSelect: async () => {
          const ok = await confirm({
            title: t('library.deleteMaterial'),
            description: t('library.confirmDeleteMaterial'),
            confirmLabel: t('library.deleteMaterial'),
            cancelLabel: t('common.cancel'),
            destructive: true,
          })
          if (ok) deleteMaterialMutation.mutate(id)
        },
      }
    )
    return items
  }

  const pasteable =
    clipboardItem !== null &&
    clipboardItem.kind === 'library' &&
    clipboardItem.courseId === courseId
  const createMenu = useCreateMaterialMenu({
    upload,
    onNewText: (kind) => setTextDialog(kind),
    onNewFolder: () => setCreating(true),
    onDiscover: () => setDiscoverOpen(true),
    prepend: pasteable
      ? [
          {
            key: 'paste',
            label: t('library.paste'),
            onSelect: () => void pasteInto(folderId),
          },
        ]
      : [],
    append: [
      {
        key: 'import-url',
        label: t('importUrl.title'),
        icon: Link2,
        onSelect: () => useImportUrlStore.getState().openImport(),
      },
      {
        key: 'add-link',
        label: t('library.addLinkedFolder'),
        onSelect: () => setLinkPicker(true),
      },
    ],
  })

  const paneMenu = (): ContextMenuItem[] => {
    if (courseId === null) {
      return [
        {
          key: 'new-course',
          label: t('library.newCourse'),
          onSelect: () => void navigate({ to: '/courses' }),
        },
      ]
    }
    if (linkState !== null) {
      return [
        {
          key: 'refresh',
          label: t('library.refresh'),
          onSelect: () => void refreshBrowse(),
        },
      ]
    }
    return createMenu.items
  }

  const searching = submittedQuery.length > 0
  const courseList = (courses.data ?? [])
    .slice()
    .sort((a, b) => a.title.localeCompare(b.title))
  const inLink = linkState !== null
  const browseData = browse.data
  const linkFolderSpecs: MaterialFolderSpec[] = (browseData?.subdirs ?? []).map(
    (entry) => ({
      key: `sub-${entry.name}`,
      name: entry.name,
      onOpen: () => {
        if (linkState === null) {
          return
        }
        setLinkState({
          ...linkState,
          subdir: linkState?.subdir ? `${linkState.subdir}/${entry.name}` : entry.name,
        })
      },
    })
  )
  const pendingCount = browseData?.uningested.length ?? 0

  const ingestAll = () => {
    if (!browseData) {
      return
    }
    for (const pending of browseData.uningested) {
      ingestMutation.mutate({
        sourceId: browseData.source_id,
        relpath: pending.relpath,
      })
    }
  }

  const tileBase = folderTileClass

  const rowBase = folderRowClass

  const stateFor = (key: string): 'none' | 'selected' | 'cut' => {
    if (
      clipboardItem !== null &&
      clipboardItem.mode === 'cut' &&
      clipboardItem.kind === 'library'
    ) {
      const inClipboard =
        (key.startsWith('f') &&
          clipboardItem.folderIds.includes(Number(key.slice(1)))) ||
        (key.startsWith('m') &&
          clipboardItem.materialIds.includes(Number(key.slice(1))))
      if (inClipboard) {
        return 'cut'
      }
    }
    return selection.selected.has(key) ? 'selected' : 'none'
  }

  const buildDragPayload = (event: React.DragEvent, kind: 'f' | 'm', id: number) => {
    const key = `${kind}${id}`
    buildDragPayloadShared(event, {
      key,
      id,
      kind: kind === 'f' ? 'folder' : 'material',
      selected: selection.selected,
      selectedPayload: {
        folderIds: selectedFolderIds,
        materialIds: selectedMaterialIds,
        noteIds: [],
      },
      setSelection: (keys) => selection.set(keys),
      countLabel: (count) => t('drag.items', { count }),
    })
  }

  const dropPayload = (
    event: React.DragEvent
  ): { folderIds: number[]; materialIds: number[] } | null => {
    const payload = parseDragPayload(event)
    if (payload === null) {
      return null
    }
    return { folderIds: payload.folderIds, materialIds: payload.materialIds }
  }

  const moveSelectionTo = async (
    event: React.DragEvent,
    targetFolderId: number | null,
    linked: boolean
  ) => {
    const payload = dropPayload(event)
    if (payload === null) {
      return
    }
    if (linked) {
      setNotice(t('library.cannotMoveIntoLinked'))
      return
    }
    if (targetFolderId !== null && payload.folderIds.includes(targetFolderId)) {
      return
    }
    try {
      for (const id of payload.folderIds) {
        await moveFolderMutation.mutateAsync({ id, parentId: targetFolderId })
      }
      for (const id of payload.materialIds) {
        await moveMaterialMutation.mutateAsync({ id, target: targetFolderId })
      }
      selection.clear()
    } catch {
      // per-mutation onError surfaces the message
    }
  }

  const folderSpecs: MaterialFolderSpec[] = childFolders.map((entry) =>
    renamingId === entry.id
      ? {
          key: `f${entry.id}`,
          name: entry.name,
          onOpen: () => goToFolder(entry.id),
          render: (
            <form
              className={view === 'grid' ? 'col-span-1 p-2' : 'px-2 py-1'}
              onSubmit={(event) => {
                event.preventDefault()
                const name = normalizeName(renameDraft)
                if (name) {
                  renameFolderMutation.mutate({ id: entry.id, name })
                }
                setRenamingId(null)
              }}
            >
              <NameEditor
                ariaLabel={t('library.renameEditor')}
                value={renameDraft}
                onChange={setRenameDraft}
                onCancel={() => setRenamingId(null)}
              />
            </form>
          ),
        }
      : {
          key: `f${entry.id}`,
          name: entry.name,
          linked: entry.source_id !== null,
          selectionState: stateFor(`f${entry.id}`),
          onPointerDown: (event) => selection.pointerDown(`f${entry.id}`, event),
          onOpen: () => openLinkFolder(entry),
          onContextMenu: (event) => {
            event.preventDefault()
            setMenu({
              x: event.clientX,
              y: event.clientY,
              items: folderMenu(entry),
            })
          },
          badge: <LinkRefBadge count={entry.node_link_count} />,
          dragProps: {
            draggable: entry.source_id === null,
            onDragStart: (event) => buildDragPayload(event, 'f', entry.id),
            onDragOver: (event) => {
              if (
                event.dataTransfer.types.includes(ITEM_MIME) &&
                entry.source_id === null
              ) {
                event.preventDefault()
                setDropTarget(entry.id)
              }
            },
            onDragLeave: () =>
              setDropTarget((current) => (current === entry.id ? null : current)),
            onDrop: (event) => {
              event.preventDefault()
              setDropTarget(null)
              void moveSelectionTo(event, entry.id, entry.source_id !== null)
            },
          },
          dropHighlighted: dropTarget === entry.id,
        }
  )

  const { band } = useMarquee({
    enabled: !searching && courseId !== null && linkState === null,
    containerRef: paneRef,
    getBaseSelection: () => selection.selected,
    onSelect: (ids) => selection.set(ids),
  })

  const upTarget = () => {
    if (linkState !== null) {
      if (linkState.subdir) {
        const parts = linkState.subdir.split('/')
        setLinkState({ ...linkState, subdir: parts.slice(0, -1).join('/') })
      } else {
        goToFolder(linkFolder?.parent_id ?? null)
      }
      return
    }
    if (currentFolder?.parent_id !== null && currentFolder?.parent_id !== undefined) {
      goToFolder(currentFolder.parent_id)
    } else if (folderId !== null) {
      goToFolder(null)
    } else if (courseId !== null) {
      goToCourse(null)
    }
  }

  return (
    <WorkspaceGate>
      <div className="mx-auto flex h-full max-w-6xl flex-col gap-3 p-6">
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="ghost"
            size="icon"
            title={t('library.goUp')}
            disabled={courseId === null || (folderId === null && !inLink)}
            onClick={upTarget}
          >
            <ArrowUp aria-hidden />
          </Button>
          <LibraryBreadcrumbs
            items={
              searching
                ? [
                    { key: 'home', label: t('library.home') },
                    {
                      key: 'search',
                      label: t('library.searchResults', {
                        count: searchResults.data?.hits.length ?? 0,
                      }),
                    },
                  ]
                : crumbs
            }
          />
          <div className="ml-auto flex items-center gap-2">
            {createMenu.inputs}
            {courseId !== null && !inLink ? (
              <Button
                variant="ghost"
                size="icon"
                title={t('library.create')}
                aria-haspopup="menu"
                onClick={(event) => {
                  const rect = event.currentTarget.getBoundingClientRect()
                  setMenu({
                    x: rect.left,
                    y: rect.bottom + 4,
                    items: paneMenu(),
                  })
                }}
              >
                <Plus aria-hidden />
              </Button>
            ) : null}
            {inLink ? (
              <>
                {pendingCount > 0 ? (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={ingestMutation.isPending}
                    onClick={ingestAll}
                  >
                    {t('library.ingestAll', { count: pendingCount })}
                  </Button>
                ) : null}
                <Button
                  variant="ghost"
                  size="icon"
                  title={t('library.rescan')}
                  disabled={scanMutation.isPending}
                  onClick={() =>
                    linkState && scanMutation.mutate(linkState.sourceId)
                  }
                >
                  <RefreshCw aria-hidden />
                </Button>
              </>
            ) : null}
            <ExpandableSearch
              value={searchQuery}
              onChange={setSearchQuery}
              onClear={() => {
                setSearchQuery('')
                setSubmittedQuery('')
              }}
              placeholder={t('library.searchPlaceholder')}
              ariaLabel={t('library.searchPlaceholder')}
              clearLabel={t('library.clearSearch')}
              onSubmit={() => setSubmittedQuery(searchQuery.trim())}
            />
            <button
              type="button"
              title={t('library.starredFilter')}
              aria-pressed={starredOnly}
              className={cn(
                'rounded-md border p-2 transition-colors',
                starredOnly
                  ? 'border-warning/50 bg-warning/10 text-warning'
                  : 'border-border text-muted-foreground hover:text-foreground'
              )}
              onClick={() => setStarredOnly((value) => !value)}
            >
              <Star className={cn('size-4', starredOnly && 'fill-current')} aria-hidden />
            </button>
            <ViewToggle view={view} onChange={setView} />
          </div>
        </div>

        {allTags.length > 0 ? (
          <div className="flex flex-wrap items-center gap-1.5">
            {allTags.map((tag) => (
              <button
                key={tag}
                type="button"
                aria-pressed={tagFilter === tag}
                className={cn(
                  'rounded-full border px-2.5 py-0.5 text-[11px] transition-colors',
                  tagFilter === tag
                    ? 'border-primary/50 bg-primary/10 text-primary'
                    : 'border-border text-muted-foreground hover:text-foreground'
                )}
                onClick={() => setTagFilter((current) => (current === tag ? null : tag))}
              >
                {tag}
              </button>
            ))}
            {tagFilter !== null ? (
              <button
                type="button"
                className="text-muted-foreground text-[11px] underline"
                onClick={() => setTagFilter(null)}
              >
                {t('library.clearTagFilter')}
              </button>
            ) : null}
          </div>
        ) : null}
        {job ? (
          <div className="bg-subtle rounded-md border border-dashed p-3 text-xs">
            <p className="mb-1 flex justify-between">
              <span>{job.stage}</span>
              <span>{job.progress}%</span>
            </p>
            <div className="bg-border h-1.5 overflow-hidden rounded-full">
              <div
                className={cn(
                  'h-full transition-all',
                  job.status === 'failed' ? 'bg-danger' : 'bg-primary'
                )}
                style={{ width: `${job.progress}%` }}
              />
            </div>
          </div>
        ) : null}
        {notice ? (
          <p className="text-muted-foreground flex items-center justify-between text-xs">
            <span>{notice}</span>
            <button type="button" onClick={() => setNotice(null)}>
              <X className="size-3" aria-hidden />
            </button>
          </p>
        ) : null}
        {courseId !== null && !inLink && (unassigned.data?.count ?? 0) > 0 ? (
          <div className="text-warning w-full rounded-md border border-dashed p-2 text-xs">
            <p className="flex w-full items-center">
              {t('library.needsPlacement', { count: unassigned.data?.count ?? 0 })}
            </p>
            <ul className="text-warning/90 mt-1 w-full space-y-0.5">
              {(unassigned.data?.materials ?? []).map((entry) => (
                <li key={entry.id} className="flex w-full items-center justify-between">
                  <Button
                    size="sm"
                    variant="ghost"
                    data-testid={`library-needs-placement-${entry.id}`}
                    className="text-warning h-5 justify-start px-1"
                    onClick={() => {
                      setUnassignedTarget(entry.id)
                    }}
                  >
                    <ChevronRight className="size-3 shrink-0" aria-hidden />
                    {entry.title}
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <div
          ref={paneRef}
          data-marquee-surface=""
          className="min-h-0 flex-1 overflow-y-auto"
          onContextMenu={(event) => {
            if (event.target === event.currentTarget) {
              event.preventDefault()
              setMenu({ x: event.clientX, y: event.clientY, items: paneMenu() })
            }
          }}
        >
          {searching ? (
            searchResults.isLoading ? (
              <MaterialBrowserSkeleton view="list" count={6} className="gap-1 p-0" />
            ) : (
            <div className="flex flex-col gap-1">
              {(searchResults.data?.hits ?? []).map((hit) => (
                <button
                  key={hit.material_id}
                  type="button"
                  className="hover:bg-subtle w-full rounded-md px-2 py-1.5 text-left text-xs"
                  onClick={() =>
                    void navigate({
                      to: '/library/$materialId',
                      search: { from },
                      params: { materialId: String(hit.material_id) },
                    })
                  }
                >
                  <span className="font-medium">{hit.title}</span>
                  <span className="text-muted-foreground block truncate">{hit.snippet}</span>
                </button>
              ))}
              {searchResults.data && searchResults.data.hits.length === 0 ? (
                <p className="text-muted-foreground px-2 text-sm">{t('library.noResults')}</p>
              ) : null}
            </div>
            )
          ) : courseId === null ? (
            courses.isLoading ? (
              <MaterialBrowserSkeleton view={view} />
            ) : (
            <div
className={cn(
                view === 'grid'
                  ? 'grid grid-cols-[repeat(auto-fill,minmax(140px,1fr))] gap-4 p-2'
                  : 'flex flex-col gap-2 p-2'
              )}
            >
              {courseList.map((entry) => (
                <button
                  key={entry.id}
                  type="button"
                  className={view === 'grid' ? tileBase : rowBase}
                  onClick={() => goToCourse(entry.id)}
                >
                  <GraduationCap className="text-primary size-8 shrink-0" aria-hidden />
                  <span className={view === 'grid' ? 'line-clamp-2 text-xs' : 'flex-1 truncate'}>
                    {entry.title}
                  </span>
                  {view === 'list' ? (
                    <span className="text-muted-foreground shrink-0 text-xs">
                      {t('library.materialCount', { count: entry.material_count })}
                    </span>
                  ) : null}
                </button>
              ))}
              {courses.data && courseList.length === 0 ? (
                <p className="text-muted-foreground col-span-full p-4 text-sm">
                  {t('library.noCourses')}
                </p>
              ) : null}
            </div>
            )
          ) : inLink ? (
            browse.isLoading || !browseData ? (
              <MaterialBrowserSkeleton view={view} />
            ) : (
            <MaterialBrowser
              view={view}
              folders={linkFolderSpecs}
              className={view === 'grid' ? 'gap-2 p-0' : 'gap-1 p-0'}
            >
              {browseData.missing_target ? (
                <p className="text-danger col-span-full flex flex-wrap items-center gap-2 p-2 text-xs">
                  <span>{t('library.targetMissing', { path: browseData.path })}</span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setRelinkSourceId(browseData.source_id)}
                  >
                    <Link2 aria-hidden />
                    {t('library.relink')}
                  </Button>
                </p>
              ) : null}
              {browseData.last_scan_error ? (
                <p
                  className="text-warning col-span-full p-2 text-xs"
                  title={browseData.last_scan_error}
                >
                  {t('library.scanError', { message: browseData.last_scan_error })}
                </p>
              ) : null}
              {browseData.materials.map((entry) =>
                view === 'grid' ? (
                  <MaterialTile
                    key={entry.id}
                    material={entry}
                    onClick={(event) => {
                      if (!isKeyboardClick(event)) {
                        return
                      }
                      void navigate({
                        to: '/library/$materialId',
                        search: { from },
                        params: { materialId: String(entry.id) },
                      })
                    }}
                    onDoubleClick={() =>
                      void navigate({
                        to: '/library/$materialId',
                        search: { from },
                        params: { materialId: String(entry.id) },
                      })
                    }
                  />
                ) : (
                  <MaterialRow
                    key={entry.id}
                    material={{ ...entry, kind: entry.kind }}
                    className="cursor-pointer px-3 py-2"
                    onOpen={() =>
                      void navigate({
                        to: '/library/$materialId',
                        search: { from },
                        params: { materialId: String(entry.id) },
                      })
                    }
                    action={<span className="text-muted-foreground shrink-0 text-xs">{entry.kind}</span>}
                  />
                )
              )}
              {browseData.uningested.map((entry) => (
                <button
                  key={entry.relpath}
                  type="button"
                  className={cn(tileBase, 'border-border border-dashed')}
                  title={t('library.ingestHint')}
                  onClick={() =>
                    ingestMutation.mutate({
                      sourceId: browseData.source_id,
                      relpath: entry.relpath,
                    })
                  }
                >
                  <KindIcon kind="doc" className="text-muted-foreground/60 size-8 shrink-0" />
                  <span className="line-clamp-2 text-xs">{entry.name}</span>
                  <span className="bg-warning/15 text-warning rounded-full px-2 py-0.5 text-[10px]">
                    {t('library.pendingIngest')}
                  </span>
                </button>
              ))}
              {!browseData.missing_target &&
              browseData.subdirs.length === 0 &&
              browseData.materials.length === 0 &&
              browseData.uningested.length === 0 ? (
                <EmptyState
                  className="col-span-full"
                  compact
                  title={t('library.emptyLink')}
                />
              ) : null}
            </MaterialBrowser>
            )
          ) : folders.isLoading || materials.isLoading ? (
            <MaterialBrowserSkeleton view={view} />
          ) : (
            <MaterialBrowser
              view={view}
              folders={folderSpecs}
              className={view === 'grid' ? 'gap-2 p-0' : 'gap-1 p-0'}
              containerProps={{
                'data-marquee-surface': '',
                onDragOver: (event) => {
                  if (Array.from(event.dataTransfer.types).includes('Files')) {
                    return
                  }
                  if (
                    event.dataTransfer.types.includes(ITEM_MIME) &&
                    event.target === event.currentTarget
                  ) {
                    event.preventDefault()
                  }
                },
                onDrop: (event) => {
                  if (Array.from(event.dataTransfer.types).includes('Files')) {
                    return
                  }
                  if (event.target !== event.currentTarget) {
                    return
                  }
                  event.preventDefault()
                  void moveSelectionTo(event, folderId, false)
                },
                onContextMenu: (event) => {
                  const target = event.target as HTMLElement
                  if (
                    target.closest(
                      'button, input, textarea, select, a, [data-selectable-id], [data-no-marquee]'
                    ) !== null
                  ) {
                    return
                  }
                  event.preventDefault()
                  setMenu({ x: event.clientX, y: event.clientY, items: paneMenu() })
                },
              }}
            >
              {creating ? (
                <form
                  className={view === 'grid' ? 'col-span-1 p-2' : 'px-2 py-1'}
                  onSubmit={(event) => {
                    event.preventDefault()
                    if (newName.trim()) {
                      createFolderMutation.mutate()
                    }
                  }}
                >
                  <input
                    autoFocus
                    className="bg-surface border-border w-full rounded-md border px-2 py-1 text-sm"
                    placeholder={t('library.folderName')}
                    value={newName}
                    onChange={(event) => setNewName(event.target.value)}
                    onBlur={() => setCreating(false)}
                  />
                </form>
              ) : null}
              {(shownMaterials ?? []).map((entry) =>
                renamingMaterialId === entry.id ? (
                  <form
                    key={entry.id}
                    className={view === 'grid' ? 'col-span-1 p-2' : 'px-2 py-1'}
                    onSubmit={(event) => {
                      event.preventDefault()
                      const title = normalizeName(materialDraft)
                      if (title) {
                        renameMaterialMutation.mutate({ id: entry.id, title })
                      }
                      setRenamingMaterialId(null)
                    }}
                  >
                    <NameEditor
                      ariaLabel={t('library.renameEditor')}
                      value={materialDraft}
                      onChange={setMaterialDraft}
                      onCancel={() => setRenamingMaterialId(null)}
                    />
                  </form>
                ) : (
                  <div
                    key={entry.id}
                    data-selectable-id={`m${entry.id}`}
                    draggable
                    onDragStart={(event) => buildDragPayload(event, 'm', entry.id)}
                  >
                    {view === 'grid' ? (
                      <MaterialTile
                        material={{
                          id: entry.id,
                          title: entry.title,
                          kind: entry.kind,
                          status: entry.status,
                          aiComposed: entry.provenance?.source === 'ai-composed',
                          linkCount: entry.link_count,
                        }}
                        selectionState={stateFor(`m${entry.id}`)}
                        className="w-full"
                        onMouseDown={(event) => selection.pointerDown(`m${entry.id}`, event)}
                        onClick={(event) => {
                          if (!isKeyboardClick(event)) {
                            return
                          }
                          void navigate({
                            to: '/library/$materialId',
                            search: { from },
                            params: { materialId: String(entry.id) },
                          })
                        }}
                        onDoubleClick={() =>
                          void navigate({
                            to: '/library/$materialId',
                            search: { from },
                            params: { materialId: String(entry.id) },
                          })
                        }
                        onContextMenu={(event) => {
                          event.preventDefault()
                          setMenu({
                            x: event.clientX,
                            y: event.clientY,
                            items: materialMenu(entry.id, entry.title),
                          })
                        }}
                      />
                    ) : (
                      <MaterialRow
                        material={{
                          id: entry.id,
                          title: entry.title,
                          kind: entry.kind,
                          status: entry.status,
                          aiComposed: entry.provenance?.source === 'ai-composed',
                          linkCount: entry.link_count,
                        }}
                        className="cursor-pointer px-3 py-2"
                        selectionState={stateFor(`m${entry.id}`)}
                        onMouseDown={(event) => selection.pointerDown(`m${entry.id}`, event)}
                        onOpen={() =>
                          void navigate({
                            to: '/library/$materialId',
                            search: { from },
                            params: { materialId: String(entry.id) },
                          })
                        }
                        action={
                          <span className="text-muted-foreground shrink-0 text-xs">{entry.kind}</span>
                        }
                        onContextMenu={(event) => {
                          event.preventDefault()
                          setMenu({
                            x: event.clientX,
                            y: event.clientY,
                            items: materialMenu(entry.id, entry.title),
                          })
                        }}
                      />
                    )}
                  </div>
                )
              )}
              {materials.data &&
              childFolders.length === 0 &&
              materials.data.length === 0 &&
              !creating ? (
                <EmptyState
                  className="col-span-full"
                  compact
                  title={t('library.empty')}
                />
              ) : null}
            </MaterialBrowser>
          )}
        </div>

        <footer className="text-muted-foreground flex items-center justify-between text-[11px]">
          <span className="flex items-center gap-2">
            {hasSelection ? (
              <button
                type="button"
                className="text-primary hover:underline"
                onClick={() => selection.clear()}
              >
                {t('library.selectedCount', { count: selection.selected.size })}
              </button>
            ) : null}
            {searching
              ? t('library.searchResults', { count: searchResults.data?.hits.length ?? 0 })
              : courseId === null
                ? t('library.courseCount', { count: courseList.length })
                : inLink && browseData
                  ? t('library.linkCounts', {
                      folders: browseData.subdirs.length,
                      materials: browseData.materials.length,
                      pending: browseData.uningested.length,
                    })
                  : t('library.itemsCount', {
                      folders: childFolders.length,
                      materials: materials.data?.length ?? 0,
                    })}
          </span>
          <span className="text-muted-foreground/70">{t('library.paneHint')}</span>
        </footer>
      </div>
      {menu ? (
        <ContextMenu x={menu.x} y={menu.y} items={menu.items} onClose={() => setMenu(null)} />
      ) : null}
      <MarqueeBand band={band} />
      {askMaterialsOpen !== null && askMaterialsOpen.length > 0 ? (
        <AskMaterialsDialog
          materials={askMaterialsOpen}
          onClose={() => setAskMaterialsOpen(null)}
        />
      ) : null}
      {reExtractTarget !== null ? (
        <ReExtractDialog
          materialId={reExtractTarget}
          open
          onClose={() => setReExtractTarget(null)}
        />
      ) : null}
      <DiscoverDialog
        open={discoverOpen}
        onClose={() => setDiscoverOpen(false)}
        courseId={courseId}
      />
      {linkedTarget !== null ? (
        <LinkedLocationsDialog
          target={linkedTarget}
          onClose={() => setLinkedTarget(null)}
        />
      ) : null}
      {assignOpen && courseId !== null ? (
        <AssignToNodeDialog
          courseId={courseId}
          title={t('assignToNode.title')}
          countText={t('assignToNode.materialCount', {
            count: selectedMaterialIds.length,
          })}
          confirmLabel={t('assignToNode.assign')}
          onDone={async (nodeId) => {
            setAssignOpen(false)
            await assignMutation.mutateAsync({
              nodeId,
              materialIds: selectedMaterialIds,
            })
          }}
          onClose={() => setAssignOpen(false)}
        />
      ) : null}
      {unassignedTarget !== null && courseId !== null ? (
        <AssignToNodeDialog
          courseId={courseId}
          title={t('library.needsPlacementTitle')}
          countText={
            (unassigned.data?.materials ?? []).find((entry) => entry.id === unassignedTarget)
              ?.title ?? ''
          }
          confirmLabel={t('assignToNode.assign')}
          onDone={async (nodeId) => {
            setUnassignedTarget(null)
            await assignMutation.mutateAsync({ nodeId, materialIds: [unassignedTarget] })
          }}
          onClose={() => setUnassignedTarget(null)}
        />
      ) : null}
      {assignFoldersOpen && courseId !== null ? (
        <AssignToNodeDialog
          courseId={courseId}
          title={t('assignToNode.folderTitle')}
          countText={t('assignToNode.folderCount', {
            count: liveSelectedIds().folderIds.length,
          })}
          confirmLabel={t('assignToNode.assign')}
          onDone={async (nodeId) => {
            setAssignFoldersOpen(false)
            await assignFoldersMutation.mutateAsync({
              nodeId,
              folderIds: liveSelectedIds().folderIds,
            })
          }}
          onClose={() => setAssignFoldersOpen(false)}
        />
      ) : null}
      {textDialog !== null ? (
        <NewTextFileDialog
          defaultKind={textDialog}
          courseId={courseId ?? undefined}
          onCreate={onCreateText}
          onSave={onSaveText}
          onCancel={() => setTextDialog(null)}
        />
      ) : null}
      {linkPicker ? (
        <FolderPickerDialog
          title={t('library.addLinkedFolder')}
          onChoose={(path) => addSourceMutation.mutate(path)}
          onCancel={() => setLinkPicker(false)}
        />
      ) : null}
      {relinkSourceId !== null ? (
        <FolderPickerDialog
          title={t('library.relinkTitle')}
          onChoose={(path) =>
            relinkMutation.mutate({ id: relinkSourceId, path })
          }
          onCancel={() => setRelinkSourceId(null)}
        />
      ) : null}
      {folderDeleteTarget !== null ? (
        <FolderDeleteDialog
          folder={folderDeleteTarget.folder}
          info={folderDeleteTarget.info}
          onConfirm={() => {
            const folder = folderDeleteTarget.folder
            setFolderDeleteTarget(null)
            deleteFolderMutation.mutate({ id: folder.id, force: true })
          }}
          onCancel={() => setFolderDeleteTarget(null)}
        />
      ) : null}
      {confirmElement}
    </WorkspaceGate>
  )
}
