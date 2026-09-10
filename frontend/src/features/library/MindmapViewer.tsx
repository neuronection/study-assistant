import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { Maximize2, MoreHorizontal, Plus, Wand2 } from 'lucide-react'
import { useCallback, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { EntityActionMenu } from '@/components/entity-menu/EntityActionMenu'
import { buildEntityActions } from '@/components/entity-menu/buildEntityActions'
import type { EntityActionHandlers, GenerateTask } from '@/components/entity-menu/types'
import { Button } from '@/components/ui/button'
import { GenerateDialog } from '@/features/ai/GenerateDialog'
import { NoteComposeDialog } from '@/features/ai/NoteComposeDialog'
import { useEntityActionHandlers } from '@/features/ai/useEntityActionHandlers'
import { addNode, createChatSession, editExtraction } from '@/lib/api'
import { useCurrentOrigin } from '@/lib/origin'
import { useConfirm } from '@/lib/use-confirm'
import { MindmapEditDialog } from './mindmap/MindmapEditDialog'
import { MindmapHistoryDialog } from './mindmap/MindmapHistoryDialog'
import { addRootNode, parseMindmap, serialize, type MindmapNode } from './mindmap/mindmapTree'
import { createMindmapSource, mindmapLlmHint } from './mindmap/mindmapSource'
import { MindmapCanvas, type MindmapCanvasHandle } from './mindmap/MindmapCanvas'

interface GenerateState {
  task: GenerateTask
  topic: string
  hint: string | null
}

export function MindmapViewer({
  markdown,
  materialId,
  materialTitle,
  courseId,
  scopeNodeId,
}: {
  markdown: string
  materialId: number
  materialTitle: string
  courseId: number
  scopeNodeId: number | null
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const from = useCurrentOrigin()
  const queryClient = useQueryClient()
  const canvasApiRef = useRef<MindmapCanvasHandle | null>(null)
  const [selected, setSelected] = useState<MindmapNode | null>(null)
  const [generate, setGenerate] = useState<GenerateState | null>(null)
  const [noteDialog, setNoteDialog] = useState<{ focus: string; hint: string | null } | null>(
    null
  )
  const [editFocus, setEditFocus] = useState<string | null | undefined>(undefined)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [confirm, confirmElement] = useConfirm()

  const parsed = useMemo(() => parseMindmap(markdown), [markdown])
  const byLine = useMemo(() => {
    const map = new Map<number, MindmapNode>()
    const walk = (nodes: MindmapNode[]) => {
      for (const node of nodes) {
        map.set(node.startLine, node)
        walk(node.children)
      }
    }
    walk(parsed.roots)
    return map
  }, [parsed])

  const save = useCallback(
    (md: string) => {
      void editExtraction(materialId, md).then(async () => {
        await queryClient.invalidateQueries({ queryKey: ['material', materialId] })
        await queryClient.invalidateQueries({ queryKey: ['materials'] })
      })
      setSelected(null)
    },
    [materialId, queryClient]
  )

  const source = useMemo(
    () => createMindmapSource({ markdown, courseId, scopeNodeId, save }),
    [markdown, courseId, scopeNodeId, save]
  )

  const sharedHandlers = useEntityActionHandlers({
    onGenerate: (prompt) => setGenerate(prompt),
    onWriteNote: (entry) => {
      if (scopeNodeId == null) return
      setNoteDialog(entry)
    },
  })

  const handlers = useMemo<EntityActionHandlers>(
    () => ({
      ...sharedHandlers,
      aiEdit: (entity) => {
        setSelected(null)
        setEditFocus(entity.label)
      },
      addAsSection: (entity, context) => {
        if (context.scopeNodeId == null) return
        void addNode(context.courseId, context.scopeNodeId, entity.label)
      },
      editNode: () => {
        if (!selected) return
        const label = window.prompt(t('entityMenu.editPrompt'), selected.label)
        if (label?.trim()) {
          source.edit?.(selected, label.trim())
          setSelected(null)
        }
      },
      addChild: () => {
        if (!selected) return
        const label = window.prompt(t('entityMenu.addChildPrompt'))
        if (label?.trim()) {
          source.addChild?.(selected, label.trim())
          setSelected(null)
        }
      },
      removeNode: async () => {
        if (!selected) return
        const ok = await confirm({
          title: t('entityMenu.remove'),
          description: t('entityMenu.removeConfirm'),
          confirmLabel: t('entityMenu.remove'),
          cancelLabel: t('common.cancel'),
          destructive: true,
        })
        if (ok) {
          source.remove?.(selected)
          setSelected(null)
        }
      },
    }),
    [sharedHandlers, source, selected, t, confirm]
  )

  const groups = selected ? buildEntityActions(source, selected, handlers, t) : []

  const closeGenerate = () => setGenerate(null)
  const closeNote = () => setNoteDialog(null)

  const menuEntry = (
    icon: React.ReactNode,
    label: string,
    onSelect: () => void,
    key: string
  ) => (
    <button
      key={key}
      type="button"
      role="menuitem"
      className="hover:bg-subtle flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs"
      onClick={() => {
        setMenuOpen(false)
        onSelect()
      }}
    >
      {icon}
      {label}
    </button>
  )

  return (
    <div className="border-border relative h-[70vh] w-full overflow-hidden rounded-md border">
      <MindmapCanvas
        markdown={markdown}
        ariaLabel={t('launcher.mindmap')}
        className="h-full w-full"
        apiRef={canvasApiRef}
        onNodeClick={(startLine) => {
          const node = byLine.get(startLine)
          if (node) setSelected(node)
        }}
      />
      <div className="absolute right-2 top-2 flex gap-1">
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            canvasApiRef.current?.fit()
          }}
        >
          <Maximize2 className="size-4" aria-hidden />
          {t('blocks.mindmapFit')}
        </Button>
        <div className="relative">
          <Button
            variant="outline"
            size="sm"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            aria-label={t('mindmapEdit.title')}
            onClick={() => setMenuOpen((value) => !value)}
          >
            <MoreHorizontal className="size-4" aria-hidden />
          </Button>
          {menuOpen ? (
            <>
              <div className="fixed inset-0 z-20" onClick={() => setMenuOpen(false)} />
              <div
                role="menu"
                className="bg-surface border-border absolute top-full right-0 z-30 mt-1 w-52 rounded-md border p-1 shadow-lg"
              >
                {menuEntry(
                  <Wand2 className="text-muted-foreground size-4" aria-hidden />,
                  t('entityMenu.aiEditMindmap'),
                  () => setEditFocus(null),
                  'aiEdit'
                )}
                {menuEntry(
                  <Plus className="text-muted-foreground size-4" aria-hidden />,
                  t('mindmapEdit.addRoot'),
                  () => {
                    const label = window.prompt(t('mindmapEdit.addRootPrompt'))
                    if (label?.trim()) {
                      save(serialize(addRootNode(parsed.lines, label.trim())))
                    }
                  },
                  'addRoot'
                )}
                {menuEntry(
                  <Wand2 className="text-muted-foreground size-4" aria-hidden />,
                  t('mindmapEdit.quizOnMap'),
                  () =>
                    setGenerate({
                      task: 'quiz',
                      topic: materialTitle,
                      hint: mindmapLlmHint(markdown, null),
                    }),
                  'quizMap'
                )}
                {menuEntry(
                  <Wand2 className="text-muted-foreground size-4" aria-hidden />,
                  t('mindmapEdit.askAboutMap'),
                  () =>
                    void createChatSession(courseId, scopeNodeId, materialTitle).then(
                      (session) =>
                        void navigate({
                          to: '/chat/$chatId',
                          params: { chatId: session.public_id },
                        })
                    ),
                  'askMap'
                )}
                {menuEntry(
                  <Wand2 className="text-muted-foreground size-4" aria-hidden />,
                  t('mindmapEdit.history'),
                  () => setHistoryOpen(true),
                  'history'
                )}
              </div>
            </>
          ) : null}
        </div>
      </div>
      {selected ? (
        <EntityActionMenu title={selected.label} groups={groups} onClose={() => setSelected(null)} />
      ) : null}
      {generate ? (
        generate.task === 'study_guide' ? (
          <GenerateDialog
            task="compose"
            courseId={courseId}
            scopeNodeId={scopeNodeId ?? undefined}
            initial={{ composeKind: 'study_guide', topic: generate.topic, hint: generate.hint }}
            onClose={closeGenerate}
            onSuccess={closeGenerate}
          />
        ) : (
          <GenerateDialog
            task={generate.task}
            courseId={courseId}
            scopeNodeId={scopeNodeId ?? undefined}
            initial={{
              topic: generate.task === 'flashcards' ? undefined : generate.topic,
              hint: generate.hint,
            }}
            onClose={closeGenerate}
            onSuccess={(result) => {
              if ('id' in result && 'question_count' in result) {
                void navigate({
                  to: '/quiz/$activityId',
                  params: { activityId: String(result.id) },
                  search: { from },
                })
              } else {
                closeGenerate()
              }
            }}
          />
        )
      ) : null}
      {noteDialog && scopeNodeId != null ? (
        <NoteComposeDialog
          courseId={courseId}
          nodeId={scopeNodeId}
          initialFocus={noteDialog.focus}
          initialHint={noteDialog.hint ?? undefined}
          onClose={closeNote}
          onSuccess={(noteId) => {
            closeNote()
            void navigate({ to: '/note/$noteId', params: { noteId: String(noteId) } })
          }}
        />
      ) : null}
      {editFocus !== undefined ? (
        <MindmapEditDialog
          materialId={materialId}
          focusNode={editFocus ?? undefined}
          onClose={() => setEditFocus(undefined)}
          onApplied={() => setEditFocus(undefined)}
        />
      ) : null}
      {historyOpen ? (
        <MindmapHistoryDialog
          materialId={materialId}
          onClose={() => setHistoryOpen(false)}
        />
      ) : null}
      {confirmElement}
    </div>
  )
}
