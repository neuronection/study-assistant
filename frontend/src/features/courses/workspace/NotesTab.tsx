import {useInfiniteQuery, useMutation, useQuery, useQueryClient} from '@tanstack/react-query'
import {Loader2, NotebookPen, Plus, Sparkles} from 'lucide-react'
import {useEffect, useMemo, useRef, useState} from 'react'
import {useTranslation} from 'react-i18next'
import {Button} from '@/components/ui/button'
import {ContextMenu, type ContextMenuItem} from '@/components/ui/ContextMenu'
import {ErrorBanner} from '@/components/ErrorBanner'
import {AssignToNodeDialog} from '../AssignToNodeDialog'
import {RenameDialog} from '@/components/RenameDialog'
import {EmptyState} from '@/components/ui/empty-state'
import {ExpandableSearch} from '@/components/ui/ExpandableSearch'
import {ViewToggle} from '@/components/ui/ViewToggle'
import {useStoredView} from '@/lib/useStoredView'
import {EntityItems, type EntityItemEntry} from '@/components/entity-list/EntityItems'
import {TabActionBar} from '@/components/layout/TabActionBar'
import {UndoDeleteNotice} from '@/components/UndoDeleteNotice'
import {useSelection} from '@/lib/useSelection'
import {MarqueeSurface} from '@/components/ui/Marquee'
import {useConfirm} from '@/lib/use-confirm'
import {createNote, moveNote, deleteNote, draftNodeNote, listNoteTags, listNotes, updateNote} from '@/lib/api'
import {formatDate} from '@/lib/format'
import {cn} from '@/lib/utils'
import {buildDragPayload} from '@/lib/dragPayload'
import {storageKeys} from '@/lib/constants'
import { ScopeChip } from './shared'

export function NotesTab({
  courseId,
  currentId,
  titles,
  onOpenNote,
}: {
  courseId: string
  currentId: string
  titles: Map<string, string>
  onOpenNote: (noteId: string) => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [query, setQuery] = useState('')
  const [submitted, setSubmitted] = useState('')
  const [activeTag, setActiveTag] = useState<string | null>(null)
  const [view, setView] = useStoredView(storageKeys.notesView, 'list')
  const [renaming, setRenaming] = useState<{ id: string; title: string } | null>(null)
  const [undoItem, setUndoItem] = useState<string | null>(null)
  const [moveOpen, setMoveOpen] = useState(false)
  const [paneMenu, setPaneMenu] = useState<{ x: number; y: number } | null>(null)
  const [confirm, confirmElement] = useConfirm()
  const pageSize = 50

  useEffect(() => {
    const id = setTimeout(() => setSubmitted(query.trim()), 250)
    return () => clearTimeout(id)
  }, [query])

  const notes = useInfiniteQuery({
    queryKey: ['notes', 'node', currentId, submitted, activeTag],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      listNotes(submitted || undefined, courseId, {
        tag: activeTag ?? undefined,
        node_id: currentId,
        limit: pageSize,
        cursor: pageParam,
      }),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  })
  const tags = useQuery({
    queryKey: ['note-tags', courseId],
    queryFn: () => listNoteTags(courseId),
  })

  const create = useMutation({
    mutationFn: () =>
      createNote({
        title: t('notes.defaultTitle'),
        course_id: courseId,
        node_id: currentId,
        tags: activeTag ? [activeTag] : [],
      }),
    onSuccess: async (note) => {
      await queryClient.invalidateQueries({ queryKey: ['notes'] })
      await queryClient.invalidateQueries({ queryKey: ['note-tags'] })
      onOpenNote(note.id)
    },
  })
  const draft = useMutation({
    mutationFn: () => draftNodeNote(currentId),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ['notes'] })
      onOpenNote(result.note_id)
    },
  })
  const rename = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) =>
      updateNote(id, { title }),
    onSuccess: async () => {
      setRenaming(null)
      await queryClient.invalidateQueries({ queryKey: ['notes'] })
    },
  })
  const remove = useMutation({
    mutationFn: (noteId: string) => deleteNote(noteId),
    onSuccess: async (result) => {
      setUndoItem(result.deleted_item_id)
      await queryClient.invalidateQueries({ queryKey: ['notes'] })
      await queryClient.invalidateQueries({ queryKey: ['note-tags'] })
      await queryClient.invalidateQueries({ queryKey: ['tree'] })
    },
  })

  const flatNotes = useMemo(
    () => notes.data?.pages.flatMap((page) => page.items) ?? [],
    [notes.data]
  )
  const noteOrder = useMemo(() => flatNotes.map((note) => String(note.id)), [flatNotes])
  const selection = useSelection(noteOrder)
  const selectedNoteIds = useMemo(
    () => [...selection.selected].map((key) => key),
    [selection.selected]
  )
  const liveSelection = useRef(selection.selected)
  liveSelection.current = selection.selected

  const moveNotes = useMutation({
    mutationFn: async ({ nodeId, noteIds }: { nodeId: string; noteIds: string[] }) => {
      for (const noteId of noteIds) {
        await moveNote(noteId, nodeId)
      }
    },
    onSuccess: async () => {
      setMoveOpen(false)
      selection.clear()
      await queryClient.invalidateQueries({ queryKey: ['notes'] })
      await queryClient.invalidateQueries({ queryKey: ['tree'] })
    },
  })

  const deleteSelectedNotes = async () => {
    const noteIds = [...liveSelection.current].map((key) => key)
    if (noteIds.length === 0) {
      return
    }
    const ok = await confirm({
      title: t('workspace.deleteSelection'),
      description: t('notes.confirmDeleteSelection', { count: noteIds.length }),
      confirmLabel: t('workspace.deleteSelection'),
      cancelLabel: t('common.cancel'),
      destructive: true,
    })
    if (!ok) {
      return
    }
    for (const noteId of noteIds) {
      remove.mutate(noteId)
    }
    selection.clear()
  }

  const allTags = (tags.data ?? []).map((entry) => entry.tag)

  const noteItems: Array<EntityItemEntry & { noteId: string }> = flatNotes.map((note) => ({
    key: String(note.id),
    noteId: note.id,
    title: note.title,
    icon: NotebookPen,
    meta: formatDate(note.updated_at),
    onClick: () => onOpenNote(note.id),
    trailing: <ScopeChip nodeId={note.node_id} courseId={courseId} titles={titles} />,
  }))

  const noteMenu = (item: EntityItemEntry & { noteId: string }): ContextMenuItem[] => {
    const multi = selection.selected.size > 1 && selection.selected.has(item.key)
    const items: ContextMenuItem[] = []
    if (!multi) {
      items.push({
        key: 'open',
        label: t('common.open'),
        onSelect: () => onOpenNote(item.noteId),
      })
      items.push({
        key: 'rename',
        label: t('common.rename'),
        onSelect: () => {
          const note = flatNotes.find((entry) => entry.id === item.noteId)
          setRenaming({ id: item.noteId, title: note?.title ?? '' })
        },
      })
    }
    items.push({
      key: 'move',
      label: t('workspace.moveToNode'),
      onSelect: () => {
        if (!selection.selected.has(item.key)) {
          selection.set([item.key])
        }
        setMoveOpen(true)
      },
    })
    if (multi) {
      items.push({
        key: 'delete-selection',
        label: t('workspace.deleteSelection'),
        danger: true,
        onSelect: deleteSelectedNotes,
      })
    } else {
      items.push({
        key: 'delete',
        label: t('notes.delete'),
        danger: true,
        onSelect: async () => {
          const note = flatNotes.find((entry) => entry.id === item.noteId)
          const ok = await confirm({
            title: t('notes.delete'),
            description: t('notes.confirmDelete', { title: note?.title ?? '' }),
            confirmLabel: t('notes.delete'),
            cancelLabel: t('common.cancel'),
            destructive: true,
          })
          if (ok) remove.mutate(item.noteId)
        },
      })
    }
    return items
  }

  return (
    <MarqueeSurface
      className="min-h-0 flex-1 space-y-3"
      selection={selection}
      clearBlocked={() => moveOpen || renaming !== null || paneMenu !== null}
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
      <UndoDeleteNotice deletedItemId={undoItem} onDismiss={() => setUndoItem(null)} />
      <TabActionBar
        actions={[
          {
            label: t('workspace.newNoteHere'),
            icon: Plus,
            onAction: () => create.mutate(),
            pending: create.isPending,
            primary: true,
          },
          {
            label: t('chapter.draftNote'),
            icon: Sparkles,
            onAction: () => draft.mutate(),
            pending: draft.isPending,
            title: t('chapter.draftNoteHint'),
          },
        ]}
      />
      <ErrorBanner
        message={
          create.isError || draft.isError
            ? [create.error, draft.error]
                .filter((error) => error !== null)
                .map((error) => (error as Error).message)
                .join(' · ')
            : null
        }
      />

      <div className="flex items-center justify-end gap-2">
        <ExpandableSearch
          value={query}
          onChange={setQuery}
          onClear={() => setSubmitted('')}
          placeholder={t('notes.searchPlaceholder')}
          ariaLabel={t('notes.searchPlaceholder')}
          clearLabel={t('notes.clearSearch')}
          onSubmit={() => setSubmitted(query.trim())}
        />
        <ViewToggle view={view} onChange={setView} />
      </div>

      {allTags.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1" role="group" aria-label={t('notes.tagFilter')}>
          <button
            type="button"
            className={cn(
              'rounded-full px-2 py-0.5 text-[11px]',
              activeTag === null
                ? 'bg-primary/15 text-primary font-medium'
                : 'text-muted-foreground hover:bg-subtle'
            )}
            onClick={() => setActiveTag(null)}
          >
            {t('notes.allTags')}
          </button>
          {allTags.map((tag) => (
            <button
              key={tag}
              type="button"
              className={cn(
                'rounded-full px-2 py-0.5 text-[11px]',
                activeTag === tag
                  ? 'bg-primary/15 text-primary font-medium'
                  : 'text-muted-foreground hover:bg-subtle'
              )}
              onClick={() => setActiveTag(activeTag === tag ? null : tag)}
            >
              {tag}
            </button>
          ))}
        </div>
      ) : null}

      <div>
        {notes.data && flatNotes.length === 0 ? (
          submitted || activeTag ? (
            <p className="text-muted-foreground py-8 text-center text-sm">
              {t('workspace.noSearchResults')}
            </p>
          ) : (
            <EmptyState
              icon={NotebookPen}
              title={t('chapter.noNotes')}
              description={t('workspace.notesEmptyDesc')}
              action={
                <Button size="sm" disabled={create.isPending} onClick={() => create.mutate()}>
                  {create.isPending ? (
                    <Loader2 className="animate-spin" aria-hidden />
                  ) : (
                    <Plus aria-hidden />
                  )}
                  {t('workspace.firstNote')}
                </Button>
              }
            />
          )
        ) : (
          <EntityItems
            items={noteItems}
            layout={view}
            menuItems={noteMenu}
            selection={{
              isSelected: (key) => selection.selected.has(key),
              onPointerDown: (key, event) => selection.pointerDown(key, event),
            }}
            onDragStart={(event, item) =>
              buildDragPayload(event, {
                key: item.key,
                id: item.noteId,
                kind: 'note',
                selected: selection.selected,
                selectedPayload: { folderIds: [], materialIds: [], noteIds: selectedNoteIds },
                setSelection: (keys) => selection.set(keys),
                countLabel: (count) => t('drag.items', { count }),
              })
            }
          />
        )}
      </div>
      {moveOpen ? (
        <AssignToNodeDialog
          courseId={courseId}
          title={t('workspace.moveToNode')}
          countText={t('moveToNode.count', { count: selectedNoteIds.length })}
          confirmLabel={t('moveToNode.confirm')}
          onDone={(nodeId) =>
            moveNotes.mutateAsync({ nodeId, noteIds: selectedNoteIds })
          }
          onClose={() => setMoveOpen(false)}
        />
      ) : null}
      {renaming !== null ? (
        <RenameDialog
          title={t('notes.renameTitle')}
          initialName={renaming.title}
          onClose={() => setRenaming(null)}
          onConfirm={(title) =>
            rename.mutate({ id: renaming.id, title })
          }
        />
      ) : null}
      {notes.hasNextPage ? (
        <div className="flex justify-center">
          <Button
            variant="outline"
            size="sm"
            disabled={notes.isFetchingNextPage}
            onClick={() => void notes.fetchNextPage()}
          >
            {notes.isFetchingNextPage ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {t('notes.loadMore')}
          </Button>
        </div>
      ) : null}
      {paneMenu !== null ? (
        <ContextMenu
          x={paneMenu.x}
          y={paneMenu.y}
          items={[
            {
              key: 'new-note',
              label: t('workspace.newNoteHere'),
              onSelect: () => create.mutate(),
            },
            {
              key: 'draft-note',
              label: t('chapter.draftNote'),
              onSelect: () => draft.mutate(),
            },
          ]}
          onClose={() => setPaneMenu(null)}
        />
      ) : null}
      {confirmElement}
    </MarqueeSurface>
  )
}

