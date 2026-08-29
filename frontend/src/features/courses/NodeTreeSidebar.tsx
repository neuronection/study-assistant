import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from '@tanstack/react-router'
import { useVirtualizer } from '@tanstack/react-virtual'
import {
  BookOpen,
  Check,
  ChevronRight,
  ClipboardList,
  Dumbbell,
  FolderTree,
  Layers,
  Loader2,
  NotebookPen,
  Search,
  X,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ContextMenu, type ContextMenuItem } from '@/components/ui/ContextMenu'
import { Button } from '@/components/ui/button'
import { EntityActionMenu } from '@/components/entity-menu/EntityActionMenu'
import { buildEntityActions } from '@/components/entity-menu/buildEntityActions'
import type { GenerateTask } from '@/components/entity-menu/types'
import { GenerateDialog } from '@/features/ai/GenerateDialog'
import { NoteComposeDialog } from '@/features/ai/NoteComposeDialog'
import { useEntityActionHandlers } from '@/features/ai/useEntityActionHandlers'
import { createCourseNodeSource } from './courseNodeSource'
import {
  addNode,
  allocateMaterial,
  courseTree,
  deleteNode,
  moveNode,
  moveNote,
  renameNode,
  restoreNode,
  type NodeCounts,
  type NodeInfo,
} from '@/lib/api'
import { fuzzyFilter } from '@/lib/fuzzy'
import { ITEM_MIME, parseDragPayload } from '@/lib/dragPayload'
import { useCurrentOrigin } from '@/lib/origin'
import { useConfirm } from '@/lib/use-confirm'
import { cn } from '@/lib/utils'

const VIRTUALIZE_THRESHOLD = 40
const DRAG_MIME = 'application/x-ca-node'
const MATERIAL_DRAG_MIME = 'application/x-ca-material'
const expandedKey = (courseId: string) => `ca-tree-expanded-${courseId}`

type FlatRow = { node: NodeInfo; depth: number; hasChildren: boolean }
type EditState = { kind: 'add' | 'rename'; nodeId: number } | null
type DropEdge = 'into' | 'before' | 'after'
type DropTarget = { id: number; edge: DropEdge }
type TreeActions = {
  addPending: boolean
  renamePending: boolean
  addChild: (parentId: number, title: string) => void
  rename: (id: number, title: string) => void
}

const COUNT_ITEMS: { key: keyof NodeCounts; label: string; icon: typeof BookOpen }[] = [
  { key: 'materials', label: 'materials', icon: BookOpen },
  { key: 'quizzes', label: 'quizzes', icon: ClipboardList },
  { key: 'exercises', label: 'exercises', icon: Dumbbell },
  { key: 'notes', label: 'notes', icon: NotebookPen },
]

function readStoredExpanded(courseId: string): Record<number, boolean> | null {
  try {
    const raw = window.localStorage.getItem(expandedKey(courseId))
    if (raw === null) {
      return null
    }
    const parsed = JSON.parse(raw) as number[]
    const map: Record<number, boolean> = {}
    for (const id of parsed) {
      map[id] = true
    }
    return map
  } catch {
    return null
  }
}

function storeExpanded(courseId: string, expanded: Record<number, boolean>) {
  try {
    window.localStorage.setItem(
      expandedKey(courseId),
      JSON.stringify(Object.keys(expanded).filter((id) => expanded[Number(id)]))
    )
  } catch {
    // preference persistence is best-effort only
  }
}

function CountBadges({ counts }: { counts: NodeCounts | undefined }) {
  const { t } = useTranslation()
  if (counts === undefined) {
    return null
  }
  const badges = COUNT_ITEMS.flatMap(({ key, label, icon: Icon }) => {
    const value = counts[key]
    if (value === 0) {
      return []
    }
    return [
      <span
        key={key}
        className="flex shrink-0 items-center gap-0.5"
        title={t(`workspace.treeCount_${label}`, { count: value })}
      >
        <Icon className="size-3" aria-hidden />
        {value}
      </span>,
    ]
  })
  if (badges.length === 0) {
    return null
  }
  return (
    <span className="text-muted-foreground flex items-center gap-1.5 text-[10px]">
      {badges}
    </span>
  )
}

function ProgressRing({ studied, total }: { studied: number; total: number }) {
  const { t } = useTranslation()
  const radius = 5.5
  const circumference = 2 * Math.PI * radius
  const filled = total > 0 ? studied / total : 0
  return (
    <svg
      className="shrink-0"
      width={16}
      height={16}
      viewBox="0 0 16 16"
      role="img"
      aria-label={t('workspace.treeProgress', { studied, total })}
    >
      <title>{t('workspace.treeProgress', { studied, total })}</title>
      <circle
        cx="8"
        cy="8"
        r={radius}
        fill="none"
        strokeWidth="2"
        className="stroke-border"
      />
      <circle
        cx="8"
        cy="8"
        r={radius}
        fill="none"
        strokeWidth="2"
        strokeLinecap="round"
        className={cn('stroke-success transition-all', filled >= 1 && 'stroke-primary')}
        strokeDasharray={circumference}
        strokeDashoffset={circumference * (1 - filled)}
        transform="rotate(-90 8 8)"
      />
    </svg>
  )
}

function DueBadge({ count }: { count: number | undefined }) {
  const { t } = useTranslation()
  if (count === undefined || count === 0) {
    return null
  }
  return (
    <span
      className="bg-warning/15 text-warning flex shrink-0 items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[10px]"
      title={t('workspace.treeDue', { count })}
    >
      <Layers className="size-3" aria-hidden />
      {count}
    </span>
  )
}

function InlineForm({
  initial,
  placeholder,
  busy,
  onSubmit,
  onCancel,
}: {
  initial: string
  placeholder: string
  busy: boolean
  onSubmit: (value: string) => void
  onCancel: () => void
}) {
  const { t } = useTranslation()
  const [value, setValue] = useState(initial)
  return (
    <form
      className="border-border bg-surface mx-1 my-0.5 flex items-center gap-1.5 rounded-md border p-1"
      onSubmit={(event) => {
        event.preventDefault()
        if (value.trim()) {
          onSubmit(value.trim())
        }
        onCancel()
      }}
    >
      <input
        autoFocus
        className="bg-surface min-w-0 flex-1 rounded px-1.5 py-0.5 text-[13px] outline-none"
        placeholder={placeholder}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Escape') {
            onCancel()
          }
        }}
        onBlur={() => onCancel()}
        aria-label={placeholder}
      />
      <button
        type="submit"
        className="text-primary shrink-0 rounded p-0.5 disabled:opacity-50"
        disabled={busy}
        onMouseDown={(event) => event.preventDefault()}
        aria-label={t('common.apply')}
      >
        <Check className="size-3.5" aria-hidden />
      </button>
    </form>
  )
}

function TreeRow({
  row,
  expanded,
  onToggle,
  courseId,
  currentId,
  tab,
  editing,
  setEditing,
  onMenu,
  dropTarget,
  materialTarget,
  focused,
  onDragStartRow,
  onDragOverRow,
  onDropRow,
  actions,
  filtering,
}: {
  row: FlatRow
  expanded: boolean
  onToggle: (nodeId: number) => void
  courseId: string
  currentId: number | undefined
  tab?: string
  editing: EditState
  setEditing: (edit: EditState) => void
  onMenu: (event: React.MouseEvent, node: NodeInfo) => void
  dropTarget: DropTarget | null
  materialTarget: number | null
  focused: boolean
  onDragStartRow: (event: React.DragEvent, node: NodeInfo) => void
  onDragOverRow: (event: React.DragEvent, node: NodeInfo) => void
  onDropRow: (event: React.DragEvent, node: NodeInfo) => void
  actions: TreeActions
  filtering: boolean
}) {
  const { t } = useTranslation()
  const node = row.node
  const active = node.id === currentId
  const search = tab !== undefined && tab !== 'overview' ? { tab } : {}
  const linkClass = cn(
    'flex min-w-0 flex-1 items-center gap-1.5 rounded py-1 text-left text-[13px] focus-visible:outline-none focus-visible:ring-2',
    active ? 'text-primary font-medium' : ''
  )
  const dropLine =
    dropTarget !== null && dropTarget.id === node.id && dropTarget.edge !== 'into'

  if (editing !== null && editing.kind === 'rename' && editing.nodeId === node.id) {
    return (
      <InlineForm
        initial={node.title}
        placeholder={t('courses.nodeTitle')}
        busy={actions.renamePending}
        onSubmit={(value) => actions.rename(node.id, value)}
        onCancel={() => setEditing(null)}
      />
    )
  }

  return (
    <>
      <div
        id={`ca-tree-row-${node.id}`}
        role="treeitem"
        aria-level={row.depth + 1}
        aria-expanded={row.hasChildren ? expanded : undefined}
        aria-selected={active}
        className={cn(
          'group relative flex items-center gap-1 rounded-md pr-1.5',
          active ? 'bg-primary/10' : 'hover:bg-subtle',
          focused && 'ring-ring ring-1',
          dropTarget !== null &&
            dropTarget.id === node.id &&
            dropTarget.edge === 'into' &&
            'ring-primary ring-2 ring-dashed',
          materialTarget === node.id && 'ring-primary ring-2 ring-dashed'
        )}
        style={{ paddingLeft: row.depth * 14 }}
        draggable={!node.is_root}
        onDragStart={(event) => onDragStartRow(event, node)}
        onDragOver={(event) => onDragOverRow(event, node)}
        onDrop={(event) => onDropRow(event, node)}
        onContextMenu={(event) => onMenu(event, node)}
      >
        {dropLine ? (
          <span
            className={cn(
              'bg-primary absolute right-1 left-1 h-0.5 rounded-full',
              dropTarget?.edge === 'before' ? '-top-0.5' : '-bottom-0.5'
            )}
            aria-hidden
          />
        ) : null}
        {row.hasChildren && !filtering ? (
          <button
            type="button"
            className="text-muted-foreground hover:text-foreground shrink-0 rounded p-0.5 focus-visible:outline-none focus-visible:ring-2"
            aria-label={t('courses.toggleNode')}
            aria-expanded={expanded}
            onClick={() => onToggle(node.id)}
          >
            <ChevronRight
              className={cn('size-3.5 transition-transform', expanded && 'rotate-90')}
              aria-hidden
            />
          </button>
        ) : (
          <span className="w-[21px] shrink-0" aria-hidden />
        )}
        {node.is_root ? (
          <Link
            to="/courses/$courseId"
            params={{ courseId }}
            search={search}
            aria-current={active ? 'page' : undefined}
            className={linkClass}
          >
            <FolderTree className="text-primary size-3.5 shrink-0" aria-hidden />
            <span className="min-w-0 flex-1 truncate">{node.title}</span>
            {node.counts !== undefined && node.counts.materials > 0 ? (
              <ProgressRing
                studied={node.counts.studied ?? 0}
                total={node.counts.materials}
              />
            ) : null}
            <DueBadge count={node.counts?.cards_due} />
            <CountBadges counts={node.counts} />
          </Link>
        ) : (
          <Link
            to="/courses/$courseId/n/$nodeId"
            params={{ courseId, nodeId: String(node.id) }}
            search={search}
            aria-current={active ? 'page' : undefined}
            className={linkClass}
          >
            <span className="min-w-0 flex-1 truncate">{node.title}</span>
            {node.counts !== undefined && node.counts.materials > 0 ? (
              <ProgressRing
                studied={node.counts.studied ?? 0}
                total={node.counts.materials}
              />
            ) : null}
            <DueBadge count={node.counts?.cards_due} />
            <CountBadges counts={node.counts} />
          </Link>
        )}
      </div>
      {!filtering &&
      editing !== null &&
      editing.kind === 'add' &&
      editing.nodeId === node.id ? (
        <InlineForm
          initial=""
          placeholder={t('courses.nodeTitle')}
          busy={actions.addPending}
          onSubmit={(value) => actions.addChild(node.id, value)}
          onCancel={() => setEditing(null)}
        />
      ) : null}
    </>
  )
}

export function NodeTreeSidebar({
  courseId,
  currentId,
  tab,
}: {
  courseId: string
  currentId: number | undefined
  tab?: string
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const from = useCurrentOrigin()
  const queryClient = useQueryClient()
  const [expanded, setExpanded] = useState<Record<number, boolean>>(() =>
    readStoredExpanded(courseId) ?? {}
  )
  const restoredRef = useRef(readStoredExpanded(courseId) !== null)
  const [menu, setMenu] = useState<{ x: number; y: number; node: NodeInfo } | null>(null)
  const [studyNode, setStudyNode] = useState<NodeInfo | null>(null)
  const [generate, setGenerate] = useState<{
    task: GenerateTask
    topic: string
    hint: string | null
  } | null>(null)
  const [noteCompose, setNoteCompose] = useState<{ focus: string; hint: string | null } | null>(
    null
  )
  const [editing, setEditing] = useState<EditState>(null)
  const [dragId, setDragId] = useState<number | null>(null)
  const [dropTarget, setDropTarget] = useState<DropTarget | null>(null)
  const [materialTarget, setMaterialTarget] = useState<number | null>(null)
  const [filter, setFilter] = useState('')
  const [focusIndex, setFocusIndex] = useState<number>(-1)
  const [undoToken, setUndoToken] = useState<string | null>(null)
  const undoTimer = useRef<number | null>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const [confirm, confirmElement] = useConfirm()

  useEffect(() => {
    return () => {
      if (undoTimer.current !== null) {
        window.clearTimeout(undoTimer.current)
      }
    }
  }, [])

  const showUndo = (token: string | null) => {
    if (undoTimer.current !== null) {
      window.clearTimeout(undoTimer.current)
    }
    setUndoToken(token)
    if (token !== null) {
      undoTimer.current = window.setTimeout(() => setUndoToken(null), 8000)
    }
  }

  useEffect(() => {
    setExpanded(readStoredExpanded(courseId) ?? {})
    restoredRef.current = readStoredExpanded(courseId) !== null
    setFilter('')
    setFocusIndex(-1)
  }, [courseId])

  useEffect(() => {
    storeExpanded(courseId, expanded)
  }, [courseId, expanded])

  const tree = useQuery({
    queryKey: ['tree', courseId],
    queryFn: () => courseTree(Number(courseId)),
  })

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['tree', courseId] })
    await queryClient.invalidateQueries({ queryKey: ['node-workspace'] })
  }

  const add = useMutation({
    mutationFn: ({ parentId, title }: { parentId: number; title: string }) =>
      addNode(Number(courseId), parentId, title),
    onSuccess: () => void refresh(),
  })
  const rename = useMutation({
    mutationFn: ({ id, title }: { id: number; title: string }) => renameNode(id, title),
    onSuccess: () => void refresh(),
  })
  const remove = useMutation({
    mutationFn: (id: number) => deleteNode(id),
    onSuccess: (token) => showUndo(token),
    onError: () => showUndo(null),
  })
  const restore = useMutation({
    mutationFn: (token: string) => restoreNode(token),
    onSuccess: async () => {
      showUndo(null)
      await refresh()
    },
  })
  const move = useMutation({
    mutationFn: ({ id, parentId, position }: { id: number; parentId: number; position: number }) =>
      moveNode(id, parentId, position),
    onSuccess: () => void refresh(),
  })
  const assignMaterial = useMutation({
    mutationFn: ({ nodeId, materialId }: { nodeId: number; materialId: number }) =>
      allocateMaterial(nodeId, materialId),
    onSuccess: () => void refresh(),
  })
  const moveNotes = useMutation({
    mutationFn: ({ nodeId, noteIds }: { nodeId: number; noteIds: number[] }) =>
      Promise.all(noteIds.map((noteId) => moveNote(noteId, nodeId))),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['notes'] })
      void refresh()
    },
  })

  const actions: TreeActions = {
    addPending: add.isPending,
    renamePending: rename.isPending,
    addChild: (parentId, title) => add.mutate({ parentId, title }),
    rename: (id, title) => rename.mutate({ id, title }),
  }

  const allNodes = useMemo(() => {
    const rows: FlatRow[] = []
    const root = tree.data?.[0]
    if (root !== undefined) {
      const walk = (node: NodeInfo, depth: number) => {
        rows.push({ node, depth, hasChildren: node.children.length > 0 })
        for (const child of node.children) {
          walk(child, depth + 1)
        }
      }
      walk(root, 0)
    }
    return rows
  }, [tree.data])

  const siblingsOf = useMemo(() => {
    const map = new Map<number, { parentId: number; index: number }>()
    const root = tree.data?.[0]
    if (root !== undefined) {
      const walk = (node: NodeInfo) => {
        node.children.forEach((child, index) => {
          map.set(child.id, { parentId: node.id, index })
          walk(child)
        })
      }
      walk(root)
    }
    return map
  }, [tree.data])

  const descendantsOf = useMemo(() => {
    const map = new Map<number, Set<number>>()
    const root = tree.data?.[0]
    if (root !== undefined) {
      const walk = (node: NodeInfo, ancestors: number[]) => {
        for (const ancestor of ancestors) {
          map.set(ancestor, (map.get(ancestor) ?? new Set()).add(node.id))
        }
        for (const child of node.children) {
          walk(child, [...ancestors, node.id])
        }
      }
      walk(root, [])
    }
    return map
  }, [tree.data])

  const ancestors = useMemo(() => {
    const chain: number[] = []
    const walk = (node: NodeInfo, path: number[]): boolean => {
      const nextPath = [...path, node.id]
      if (node.id === currentId) {
        chain.push(...nextPath)
        return true
      }
      return node.children.some((child) => walk(child, nextPath))
    }
    const root = tree.data?.[0]
    if (root !== undefined && currentId !== undefined) {
      walk(root, [])
    }
    return chain
  }, [tree.data, currentId])

  useEffect(() => {
    const root = tree.data?.[0]
    if (root === undefined || restoredRef.current) {
      return
    }
    const ensure = [root.id, ...ancestors.slice(0, -1)]
    setExpanded((current) => {
      const next = { ...current }
      let changed = false
      for (const id of ensure) {
        if (!next[id]) {
          next[id] = true
          changed = true
        }
      }
      return changed ? next : current
    })
  }, [tree.data, ancestors])

  const flat = useMemo(() => {
    const rows: FlatRow[] = []
    const walk = (node: NodeInfo, depth: number) => {
      rows.push({ node, depth, hasChildren: node.children.length > 0 })
      if (expanded[node.id]) {
        for (const child of node.children) {
          walk(child, depth + 1)
        }
      }
    }
    const root = tree.data?.[0]
    if (root !== undefined) {
      walk(root, 0)
    }
    return rows
  }, [tree.data, expanded])

  const filtering = filter.trim().length > 0
  const rows = useMemo(() => {
    if (!filtering) {
      return flat
    }
    return fuzzyFilter(allNodes, filter, (row) => row.node.title)
  }, [filtering, flat, allNodes, filter])

  useEffect(() => {
    setFocusIndex((current) => (current >= rows.length ? -1 : current))
  }, [rows.length])

  const virtualize = rows.length > VIRTUALIZE_THRESHOLD
  const virtualizer = useVirtualizer({
    count: virtualize ? rows.length : 0,
    getScrollElement: () => listRef.current,
    estimateSize: () => 28,
    overscan: 10,
  })

  const expandAll = () => {
    const next: Record<number, boolean> = {}
    for (const row of allNodes) {
      if (row.node.children.length > 0) {
        next[row.node.id] = true
      }
    }
    setExpanded(next)
  }

  const collapseAll = () =>
    setExpanded(tree.data?.[0] !== undefined ? { [tree.data[0].id]: true } : {})

  const root = tree.data?.[0]
  const nodeTotal = allNodes.length

  const menuItems = (node: NodeInfo): ContextMenuItem[] => {
    const items: ContextMenuItem[] = [
      {
        key: 'study',
        label: t('entityMenu.study'),
        onSelect: () => setStudyNode(node),
      },
      {
        key: 'add-child',
        label: t('courses.addChild'),
        onSelect: () => {
          setExpanded((current) => ({ ...current, [node.id]: true }))
          setEditing({ kind: 'add', nodeId: node.id })
        },
      },
    ]
    if (!node.is_root) {
      items.push(
        {
          key: 'rename',
          label: t('courses.renameNode'),
          onSelect: () => setEditing({ kind: 'rename', nodeId: node.id }),
        },
        {
          key: 'delete',
          label: t('courses.deleteNode'),
          danger: true,
          onSelect: async () => {
            const ok = await confirm({
              title: t('courses.deleteNode'),
              description: t('courses.confirmDeleteNode'),
              confirmLabel: t('courses.deleteNode'),
              cancelLabel: t('common.cancel'),
              destructive: true,
            })
            if (ok) remove.mutate(node.id)
          },
        }
      )
    }
    return items
  }

  const courseNodeSource = useMemo(
    () => createCourseNodeSource(Number(courseId)),
    [courseId]
  )
  const studyHandlers = useEntityActionHandlers({
    onGenerate: (prompt) => {
      setStudyNode(null)
      setGenerate(prompt)
    },
    onWriteNote: (entry) => {
      setStudyNode(null)
      if (studyNode) setNoteCompose(entry)
    },
  })
  const studyGroups =
    studyNode !== null
      ? buildEntityActions(courseNodeSource, studyNode, studyHandlers, t)
      : []

  const onDragStartRow = (event: React.DragEvent, node: NodeInfo) => {
    event.dataTransfer.setData(DRAG_MIME, String(node.id))
    setDragId(node.id)
  }

  const dropEdgeFor = (event: React.DragEvent, element: HTMLElement): DropEdge => {
    const rect = element.getBoundingClientRect()
    const y = event.clientY || rect.top + rect.height / 2
    const relative = rect.height > 0 ? (y - rect.top) / rect.height : 0.5
    if (relative < 0.3) {
      return 'before'
    }
    if (relative > 0.7) {
      return 'after'
    }
    return 'into'
  }

  const canDropNode = (node: NodeInfo, edge: DropEdge, draggedId: number | null): boolean => {
    if (draggedId === null || node.id === draggedId) {
      return false
    }
    if ((descendantsOf.get(draggedId) ?? new Set()).has(node.id)) {
      return false
    }
    if (edge !== 'into' && node.is_root) {
      return false
    }
    return true
  }

  const onDragOverRow = (event: React.DragEvent, node: NodeInfo) => {
    if (event.dataTransfer.types.includes(DRAG_MIME)) {
      const edge = dropEdgeFor(event, event.currentTarget as HTMLElement)
      if (canDropNode(node, edge, dragId)) {
        event.preventDefault()
        setDropTarget({ id: node.id, edge })
      }
      return
    }
    if (
      event.dataTransfer.types.includes(MATERIAL_DRAG_MIME) ||
      event.dataTransfer.types.includes(ITEM_MIME)
    ) {
      event.preventDefault()
      setMaterialTarget(node.id)
    }
  }

  const onDropRow = (event: React.DragEvent, node: NodeInfo) => {
    event.preventDefault()
    const payload = parseDragPayload(event)
    if (payload !== null) {
      setMaterialTarget(null)
      if (payload.noteIds.length > 0) {
        moveNotes.mutate({ nodeId: node.id, noteIds: payload.noteIds })
        return
      }
      if (payload.materialIds.length > 0) {
        for (const materialId of payload.materialIds) {
          assignMaterial.mutate({ nodeId: node.id, materialId })
        }
        return
      }
    }
    const materialId = event.dataTransfer.getData(MATERIAL_DRAG_MIME)
    if (materialId) {
      setMaterialTarget(null)
      assignMaterial.mutate({ nodeId: node.id, materialId: Number(materialId) })
      return
    }
    const dragged = Number(event.dataTransfer.getData(DRAG_MIME))
    const storedEdge = dropTarget?.id === node.id ? dropTarget.edge : null
    const edge =
      storedEdge ?? dropEdgeFor(event, event.currentTarget as HTMLElement)
    setDropTarget(null)
    setDragId(null)
    if (!dragged || !canDropNode(node, edge, dragged)) {
      return
    }
    if (edge === 'into') {
      move.mutate({ id: dragged, parentId: node.id, position: node.children.length })
      setExpanded((current) => ({ ...current, [node.id]: true }))
      return
    }
    const sibling = siblingsOf.get(node.id)
    if (sibling === undefined) {
      return
    }
    move.mutate({
      id: dragged,
      parentId: sibling.parentId,
      position: edge === 'before' ? sibling.index : sibling.index + 1,
    })
  }

  const openNode = (node: NodeInfo) => {
    const search = tab !== undefined && tab !== 'overview' ? { tab } : {}
    if (node.is_root) {
      void navigate({ to: '/courses/$courseId', params: { courseId }, search })
    } else {
      void navigate({
        to: '/courses/$courseId/n/$nodeId',
        params: { courseId, nodeId: String(node.id) },
        search,
      })
    }
  }

  const onTreeContextMenu = (event: React.MouseEvent) => {
    const target = event.target as HTMLElement
    if (
      target.closest('[role="treeitem"]') !== null ||
      target.closest('input, textarea') !== null
    ) {
      return
    }
    const node = allNodes.find((row) => row.node.id === currentId)?.node ?? root
    if (node === undefined) {
      return
    }
    event.preventDefault()
    setMenu({ x: event.clientX, y: event.clientY, node })
  }

  const onTreeKeyDown = (event: React.KeyboardEvent) => {
    if (rows.length === 0) {
      return
    }
    const current = focusIndex >= 0 && focusIndex < rows.length ? focusIndex : 0
    const row = rows[current]
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const next = event.key === 'ArrowDown' ? current + 1 : current - 1
      if (next >= 0 && next < rows.length) {
        setFocusIndex(next)
        document.getElementById(`ca-tree-row-${rows[next].node.id}`)?.scrollIntoView({
          block: 'nearest',
        })
      }
      return
    }
    if (row === undefined) {
      return
    }
    if (event.key === 'Enter') {
      event.preventDefault()
      openNode(row.node)
      return
    }
    if (filtering) {
      return
    }
    const hasChildren = row.node.children.length > 0
    const isOpen = expanded[row.node.id] ?? false
    if (event.key === 'ArrowRight') {
      event.preventDefault()
      if (hasChildren && !isOpen) {
        setExpanded((state) => ({ ...state, [row.node.id]: true }))
      } else if (hasChildren) {
        const next = current + 1
        if (next < rows.length) {
          setFocusIndex(next)
        }
      }
    }
    if (event.key === 'ArrowLeft') {
      event.preventDefault()
      if (hasChildren && isOpen) {
        setExpanded((state) => ({ ...state, [row.node.id]: false }))
        return
      }
      const sibling = siblingsOf.get(row.node.id)
      if (sibling !== undefined) {
        const parentIndex = rows.findIndex((entry) => entry.node.id === sibling.parentId)
        if (parentIndex >= 0) {
          setFocusIndex(parentIndex)
        }
      }
    }
  }

  const actionError =
    (add.error as Error | null)?.message ??
    (rename.error as Error | null)?.message ??
    (remove.error as Error | null)?.message ??
    (move.error as Error | null)?.message ??
    (assignMaterial.error as Error | null)?.message ??
    null

  const rowProps = (row: FlatRow, index: number) => ({
    row,
    expanded: expanded[row.node.id] ?? false,
    onToggle: (nodeId: number) =>
      setExpanded((current) => ({ ...current, [nodeId]: !current[nodeId] })),
    courseId,
    currentId,
    tab,
    editing,
    setEditing,
    onMenu: (event: React.MouseEvent, node: NodeInfo) => {
      event.preventDefault()
      setMenu({ x: event.clientX, y: event.clientY, node })
    },
    dropTarget,
    materialTarget,
    focused: focusIndex === index,
    onDragStartRow,
    onDragOverRow,
    onDropRow,
    actions,
    filtering,
  })

  return (
    <aside
      className="border-border bg-subtle/40 sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r md:flex"
      aria-label={t('workspace.treeSidebar')}
      onContextMenu={onTreeContextMenu}
    >
      <div className="border-border flex items-center justify-between border-b px-3 py-2.5">
        <span className="text-muted-foreground flex items-center gap-1.5 text-[11px] font-semibold tracking-wide uppercase">
          <FolderTree className="size-3.5" aria-hidden />
          {t('workspace.treeSidebarTitle')}
        </span>
        <span className="text-muted-foreground text-[10px]">
          {t('workspace.treeNodeCount', { count: nodeTotal })}
        </span>
      </div>
      <div className="border-border border-b px-2 py-1.5">
        <div className="relative">
          <Search
            className="text-muted-foreground pointer-events-none absolute top-1.5 left-2 size-3"
            aria-hidden
          />
          <input
            className="bg-surface border-border focus:border-primary w-full rounded-md border py-1 pr-6 pl-6 text-xs outline-none"
            placeholder={t('workspace.treeFilter')}
            aria-label={t('workspace.treeFilter')}
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Escape') {
                setFilter('')
              }
            }}
          />
          {filtering ? (
            <button
              type="button"
              className="text-muted-foreground hover:text-foreground absolute top-1.5 right-1.5"
              aria-label={t('library.clearSearch')}
              onClick={() => setFilter('')}
            >
              <X className="size-3" aria-hidden />
            </button>
          ) : null}
        </div>
        {!filtering ? (
          <div className="mt-1 flex items-center justify-end gap-1">
            <button
              type="button"
              className="text-muted-foreground hover:bg-subtle hover:text-foreground rounded px-1.5 py-0.5 text-[10px]"
              onClick={expandAll}
            >
              {t('workspace.treeExpandAll')}
            </button>
            <span className="text-muted-foreground/50" aria-hidden>
              ·
            </span>
            <button
              type="button"
              className="text-muted-foreground hover:bg-subtle hover:text-foreground rounded px-1.5 py-0.5 text-[10px]"
              onClick={collapseAll}
            >
              {t('workspace.treeCollapseAll')}
            </button>
          </div>
        ) : (
          <p className="text-muted-foreground mt-1 text-right text-[10px]">
            {t('workspace.treeMatches', { count: rows.length })}
          </p>
        )}
      </div>
      <div
        ref={listRef}
        role="tree"
        aria-label={t('workspace.treeSidebar')}
        aria-activedescendant={
          focusIndex >= 0 && focusIndex < rows.length
            ? `ca-tree-row-${rows[focusIndex].node.id}`
            : undefined
        }
        tabIndex={0}
        onKeyDown={onTreeKeyDown}
        onFocus={() => {
          if (focusIndex < 0) {
            const index = rows.findIndex((row) => row.node.id === currentId)
            setFocusIndex(index >= 0 ? index : 0)
          }
        }}
        className="focus:outline-none min-h-0 flex-1 space-y-0.5 overflow-y-auto p-2"
      >
        {tree.isLoading ? (
          <span className="text-muted-foreground px-2 py-2 text-xs">
            {t('library.loading')}
          </span>
        ) : null}
        {virtualize ? (
          <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
            {virtualizer.getVirtualItems().map((virtualRow) => {
              const row = rows[virtualRow.index]
              if (row === undefined) {
                return null
              }
              return (
                <div
                  key={row.node.id}
                  data-index={virtualRow.index}
                  ref={virtualizer.measureElement}
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    transform: `translateY(${virtualRow.start}px)`,
                  }}
                >
                  <TreeRow key={row.node.id} {...rowProps(row, virtualRow.index)} />
                </div>
              )
            })}
          </div>
        ) : (
          rows.map((row, index) => (
            <TreeRow key={row.node.id} {...rowProps(row, index)} />
          ))
        )}
        {root !== undefined && root.children.length === 0 && !tree.isLoading && !filtering ? (
          <p className="text-muted-foreground px-2 py-2 text-xs">
            {t('workspace.treeEmpty')}
          </p>
        ) : null}
        {filtering && rows.length === 0 && !tree.isLoading ? (
          <p className="text-muted-foreground px-2 py-2 text-xs">
            {t('workspace.treeNoMatches')}
          </p>
        ) : null}
        {actionError ? <p className="text-danger px-2 py-1 text-xs">{actionError}</p> : null}
      </div>
      {menu ? (
        <ContextMenu
          x={menu.x}
          y={menu.y}
          items={menuItems(menu.node)}
          onClose={() => setMenu(null)}
        />
      ) : null}
      {studyNode !== null ? (
        <EntityActionMenu
          title={studyNode.title}
          groups={studyGroups}
          onClose={() => setStudyNode(null)}
        />
      ) : null}
      {generate && studyNode !== null ? (
        generate.task === 'study_guide' ? (
          <GenerateDialog
            task="compose"
            courseId={Number(courseId)}
            scopeNodeId={studyNode.id}
            rootNodeId={root?.id}
            initial={{ composeKind: 'study_guide', topic: generate.topic, hint: generate.hint }}
            onClose={() => setGenerate(null)}
            onSuccess={() => setGenerate(null)}
          />
        ) : (
          <GenerateDialog
            task={generate.task}
            courseId={Number(courseId)}
            scopeNodeId={studyNode.id}
            rootNodeId={root?.id}
            initial={{
              topic: generate.task === 'flashcards' ? undefined : generate.topic,
              hint: generate.hint,
            }}
            onClose={() => setGenerate(null)}
            onSuccess={(result) => {
              if ('id' in result && 'question_count' in result) {
                void navigate({
                  to: '/quiz/$activityId',
                  params: { activityId: String(result.id) },
                  search: { from },
                })
              } else {
                setGenerate(null)
              }
            }}
          />
        )
      ) : null}
      {noteCompose && studyNode !== null ? (
        <NoteComposeDialog
          courseId={Number(courseId)}
          nodeId={studyNode.id}
          initialFocus={noteCompose.focus}
          initialHint={noteCompose.hint ?? undefined}
          onClose={() => setNoteCompose(null)}
          onSuccess={(noteId) => {
            setNoteCompose(null)
            void navigate({ to: '/note/$noteId', params: { noteId: String(noteId) } })
          }}
        />
      ) : null}
      {undoToken !== null ? (
        <div
          className="bg-surface border-border m-2 flex items-center justify-between gap-2 rounded-lg border px-3 py-2 shadow-lg"
          role="status"
        >
          <span className="text-muted-foreground text-xs">
            {restore.isError
              ? t('workspace.undoFailed')
              : t('workspace.nodeDeleted')}
          </span>
          <div className="flex items-center gap-1">
            {restore.isError ? null : (
              <Button
                variant="outline"
                size="sm"
                disabled={restore.isPending}
                onClick={() => restore.mutate(undoToken)}
              >
                {restore.isPending ? (
                  <Loader2 className="animate-spin" aria-hidden />
                ) : null}
                {t('workspace.undo')}
              </Button>
            )}
            <Button
              variant="ghost"
              size="icon"
              className="size-6"
              aria-label={t('common.close')}
              onClick={() => showUndo(null)}
            >
              <X className="size-3.5" aria-hidden />
            </Button>
          </div>
        </div>
      ) : null}
      {confirmElement}
    </aside>
  )
}
