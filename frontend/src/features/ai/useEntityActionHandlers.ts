import { useNavigate } from '@tanstack/react-router'
import { useCallback } from 'react'

import type {
  EntityActionHandlers,
  EntityContext,
  EntityNode,
  GenerateTask,
} from '@/components/entity-menu/types'
import { createChatSession, createNote } from '@/lib/api'
import { useChatStore } from '@/lib/chat-store'

export interface GeneratePrompt {
  task: GenerateTask
  topic: string
  hint: string | null
}

export function useEntityActionHandlers(options: {
  onGenerate: (prompt: GeneratePrompt) => void
  onWriteNote: (focus: { focus: string; hint: string | null } | null) => void
}): EntityActionHandlers {
  const navigate = useNavigate()

  const openChatSession = useChatStore((state) => state.openSession)

  const ask = useCallback(
    (entity: EntityNode, context: EntityContext) => {
      void createChatSession(context.courseId, context.scopeNodeId, entity.label).then((session) =>
        openChatSession({ id: session.id, publicId: session.public_id })
      )
    },
    [openChatSession]
  )

  const generate = useCallback(
    (task: GenerateTask, entity: EntityNode, _context: EntityContext, hint: string | null) => {
      options.onGenerate({ task, topic: entity.label, hint })
    },
    [options]
  )

  const writeNote = useCallback(
    (entity: EntityNode, _context: EntityContext, hint: string | null) => {
      options.onWriteNote({ focus: entity.label, hint })
    },
    [options]
  )

  const addNote = useCallback(
    (entity: EntityNode, context: EntityContext) => {
      void createNote({
        title: entity.label,
        course_id: context.courseId,
        node_id: context.scopeNodeId,
      }).then((note) => {
        void navigate({ to: '/note/$noteId', params: { noteId: String(note.id) } })
      })
    },
    [navigate]
  )

  return { ask, generate, writeNote, addNote }
}
