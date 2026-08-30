import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearch } from '@tanstack/react-router'
import {
  ArrowUp,
  FolderClosed,
  GraduationCap,
  Link2,
  Plus,
  RefreshCw,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { ExpandableSearch } from '@/components/ui/ExpandableSearch'
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
  getFolderDeleteInfo,
  ingestSourceFile,
  listCourses,
  listJobs,
  retryJob,
  reingestMaterial,
  listFolders,
  listMaterials,
  moveFolder,
  moveMaterial,
  relinkSource,
  renameFolder,
  renameMaterial,
  revealSource,
  scanSource,
  search,
  unlinkFolder,
  updateTextMaterial,
} from '@/lib/api'
import type {
  Folder,
  FolderDeleteInfo,
  JobInfo,
  PendingDrawing,
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
import { getWsClient } from '@/lib/ws-client'

import { Breadcrumbs, type Crumb } from './Breadcrumbs'
import { ContextMenu, type ContextMenuItem } from '@/components/ui/ContextMenu'
import { MarqueeBand, useMarquee } from '@/components/ui/Marquee'
import { FolderPickerDialog } from './FolderPickerDialog'
import { FolderDeleteDialog } from './FolderDeleteDialog'

import { KindIcon } from './KindIcon'
import { NameEditor, normalizeName } from './NameEditor'
import { NewTextFileDialog } from './NewTextFileDialog'
import { ViewToggle, type LibraryView } from '@/components/ui/ViewToggle'
import { MaterialRow } from '@/components/materials/MaterialRow'
import { MaterialTile } from '@/components/materials/MaterialTile'
import { useMaterialUpload } from '@/components/materials/materialUpload'
import { useCreateMaterialMenu } from '@/components/materials/createMaterialMenu'
import { useWindowDropRegistration } from '@/lib/window-drop-store'
import { AssignToNodeDialog } from '@/features/courses/AssignToNodeDialog'

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

const VIEW_KEY = 'ca-library-view'

const REINGESTABLE_KINDS = new Set(['pdf', 'md', 'txt', 'image'])

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
  const [menu, setMenu] = useState<MenuState | null>(null)
  const [renamingId, setRenamingId] = useState<number | null>(null)
  const [renameDraft, setRenameDraft] = useState('')
  const [renamingMaterialId, setRenamingMaterialId] = useState<number | null>(null)
  const [materialDraft, setMaterialDraft] = useState('')
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [textDialog, setTextDialog] = useState<'txt' | 'md' | null>(null)
  const [linkPicker, setLinkPicker] = useState(false)
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
    filename: string,
    content: string,
    drawings: PendingDrawing[]
  ): Promise<TextFileEditState | null> => {
    if (courseId === null) {
      throw new Error(t('library.needsCourse'))
    }
    const state = await createTextMaterial({
      course_id: courseId,
      folder_id: folderId,
      filename,
      content,
      drawings,
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
    content: string,
    drawings: PendingDrawing[],
    state: TextFileEditState
  ): Promise<TextFileEditState> => {
    const next = await updateTextMaterial({
      materialId: state.materialId,
      content,
      drawings,
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
      setNotice(
        t('sources.scanResult', {
          added: result.stats.new,
          updated: result.stats.updated,
          missing: result.stats.missing,
        })
      )
      await refreshMaterials()
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
    const unsubscribe = getWsClient().subscribe(`jobs:${uploadJobId}`, (payload) => {
      const progress = payload as JobProgress
      setJob(progress)
      if (progress.status === 'done' || progress.status === 'failed') {
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

  const visibleMaterialIds = useMemo(
    () => (materials.data ?? []).map((entry) => entry.id),
    [materials.data]
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
      (entry) =>
        entry !== undefined &&
        REINGESTABLE_KINDS.has(entry.kind) &&
        entry.blob_sha !== null
    )
    const items: ContextMenuItem[] = []
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
    }
    if (fileBacked.length > 0) {
      items.push({
        key: 'reingest',
        label:
          fileBacked.length === 1
            ? t('jobs.reingestOne')
            : t('jobs.reingestMany', { count: fileBacked.length }),
        disabled: reingestMutation.isPending,
        onSelect: () => {
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

  const tileBase =
    'group flex cursor-pointer select-none flex-col items-center gap-2 rounded-lg border border-transparent p-3 text-center transition-colors hover:border-border hover:bg-subtle'
  const rowBase =
    'hover:bg-subtle flex w-full cursor-pointer select-none items-center gap-2 rounded-md px-3 py-2 text-left text-sm'

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

  const selectedClass = (key: string): string => {
    const state = stateFor(key)
    if (state === 'cut') {
      return 'border-primary/50 bg-primary/5 opacity-50'
    }
    if (state === 'selected') {
      return 'border-primary bg-primary/10'
    }
    return ''
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
          <Breadcrumbs
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
            <ViewToggle view={view} onChange={setView} />
          </div>
        </div>

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
          ) : courseId === null ? (
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
          ) : inLink && browseData ? (
            <div
              className={cn(
                view === 'grid'
                  ? 'grid grid-cols-[repeat(auto-fill,minmax(140px,1fr))] gap-2'
                  : 'flex flex-col gap-1'
              )}
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
              {browseData.subdirs.map((entry) => (
                <button
                  key={entry.name}
                  type="button"
                  className={view === 'grid' ? tileBase : rowBase}
                  onClick={(event) => {
                    if (!isKeyboardClick(event)) {
                      return
                    }
                    setLinkState({
                      ...linkState,
                      subdir: linkState?.subdir
                        ? `${linkState.subdir}/${entry.name}`
                        : entry.name,
                    })
                  }}
                  onDoubleClick={() =>
                    setLinkState({
                      ...linkState,
                      subdir: linkState?.subdir
                        ? `${linkState.subdir}/${entry.name}`
                        : entry.name,
                    })
                  }
                >
                  <FolderClosed className="text-primary size-8 shrink-0" aria-hidden />
                  <span className={view === 'grid' ? 'line-clamp-2 text-xs' : 'flex-1 truncate'}>
                    {entry.name}
                  </span>
                </button>
              ))}
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
                <p className="text-muted-foreground col-span-full p-4 text-sm">
                  {t('library.emptyLink')}
                </p>
              ) : null}
            </div>
          ) : (
            <div
              className={cn(
                view === 'grid'
                  ? 'grid grid-cols-[repeat(auto-fill,minmax(140px,1fr))] gap-2'
                  : 'flex flex-col gap-1'
              )}
              data-marquee-surface=""
              onDragOver={(event) => {
                if (Array.from(event.dataTransfer.types).includes('Files')) {
                  return
                }
                if (
                  event.dataTransfer.types.includes(ITEM_MIME) &&
                  event.target === event.currentTarget
                ) {
                  event.preventDefault()
                }
              }}
              onDrop={(event) => {
                if (Array.from(event.dataTransfer.types).includes('Files')) {
                  return
                }
                if (event.target !== event.currentTarget) {
                  return
                }
                event.preventDefault()
                void moveSelectionTo(event, folderId, false)
              }}
              onContextMenu={(event) => {
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
              }}
            >
              {childFolders.map((entry) =>
                renamingId === entry.id ? (
                  <form
                    key={entry.id}
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
                ) : (
                  <button
                    key={entry.id}
                    type="button"
                    data-selectable-id={`f${entry.id}`}
                    className={cn(
                      view === 'grid' ? tileBase : rowBase,
                      selectedClass(`f${entry.id}`),
                      dropTarget === entry.id && 'ring-primary ring-2'
                    )}
                    onMouseDown={(event) => selection.pointerDown(`f${entry.id}`, event)}
                    onClick={(event) => {
                      if (isKeyboardClick(event)) {
                        openLinkFolder(entry)
                      }
                    }}
                    onDoubleClick={() => openLinkFolder(entry)}
                    draggable={entry.source_id === null}
                    onDragStart={(event) => buildDragPayload(event, 'f', entry.id)}
                    onDragOver={(event) => {
                      if (
                        event.dataTransfer.types.includes(ITEM_MIME) &&
                        entry.source_id === null
                      ) {
                        event.preventDefault()
                        setDropTarget(entry.id)
                      }
                    }}
                    onDragLeave={() =>
                      setDropTarget((current) => (current === entry.id ? null : current))
                    }
                    onDrop={(event) => {
                      event.preventDefault()
                      setDropTarget(null)
                      void moveSelectionTo(event, entry.id, entry.source_id !== null)
                    }}
                    onContextMenu={(event) => {
                      event.preventDefault()
                      setMenu({
                        x: event.clientX,
                        y: event.clientY,
                        items: folderMenu(entry),
                      })
                    }}
                  >
                    {entry.source_id !== null ? (
                      <span className="relative shrink-0">
                        <FolderClosed className="text-primary size-8" aria-hidden />
                        <Link2 className="text-primary absolute right-0 bottom-0 size-3.5" aria-hidden />
                      </span>
                    ) : (
                      <FolderClosed className="text-primary size-8 shrink-0" aria-hidden />
                    )}
                    <span
                      className={cn(
                        'min-w-0',
                        view === 'grid'
                          ? cn(
                              'line-clamp-3 text-xs',
                              stateFor(`f${entry.id}`) === 'selected' && 'line-clamp-4'
                            )
                          : stateFor(`f${entry.id}`) === 'selected'
                            ? 'flex-1 line-clamp-2'
                            : 'flex-1 truncate'
                      )}
                    >
                      {entry.name}
                    </span>
                  </button>
                )
              )}
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
              {(materials.data ?? []).map((entry) =>
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
                <p className="text-muted-foreground col-span-full p-4 text-sm">
                  {t('library.empty')}
                </p>
              ) : null}
            </div>
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
