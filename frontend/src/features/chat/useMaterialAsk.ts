import {
  createChatSession,
  updateChatSessionQuizme,
} from '@/lib/api'
import { useChatStore, type ChatSessionRef, type PendingAskAttachment } from '@/lib/chat-store'

export interface AskMaterialTarget {
  id: number
  course_id: number | null
  title: string
}

export interface AskMaterialInput {
  material: AskMaterialTarget
  scopeNodeId?: number | null
  content: string
  attachments?: PendingAskAttachment[]
  selection?: string | null
  mode: 'prefill' | 'send'
  quizMe?: boolean
}

const SELECTION_CAP = 1500

export function quoteSelection(selection: string): string {
  const text = selection.trim()
  const capped =
    text.length > SELECTION_CAP ? `${text.slice(0, SELECTION_CAP)}\n[…]` : text
  return capped
    .split('\n')
    .map((line) => `> ${line}`.trimEnd())
    .join('\n')
}

export async function askMaterial(input: AskMaterialInput): Promise<ChatSessionRef> {
  const existing = useChatStore.getState().viewerAsks[input.material.id]
  let session: ChatSessionRef
  if (existing !== undefined) {
    session = existing
  } else {
    const created = await createChatSession(
      input.material.course_id,
      input.scopeNodeId ?? null,
      input.material.title,
    )
    session = { id: created.id, publicId: created.public_id }
    useChatStore.getState().setViewerAsk(input.material.id, session)
  }
  if (input.quizMe === true) {
    await updateChatSessionQuizme(session.id, true)
  }
  const content =
    input.selection !== undefined && input.selection !== null && input.selection.trim() !== ''
      ? `${quoteSelection(input.selection)}\n\n${input.content}`
      : input.content
  const store = useChatStore.getState()
  store.openSession(session)
  store.queueSend({ content, attachments: input.attachments, mode: input.mode })
  return session
}

export interface AskMaterialsInput {
  materials: AskMaterialTarget[]
  title: string
  content: string
  quizMe?: boolean
}

export function selectionAskKey(materialIds: number[]): string {
  return [...materialIds].sort((a, b) => a - b).join('-')
}

export async function askMaterials(input: AskMaterialsInput): Promise<ChatSessionRef> {
  const first = input.materials[0]
  if (first === undefined) {
    throw new Error('askMaterials requires at least one material')
  }
  const key = selectionAskKey(input.materials.map((material) => material.id))
  let session = useChatStore.getState().selectionAsks[key]
  if (session === undefined) {
    const created = await createChatSession(first.course_id, null, input.title)
    session = { id: created.id, publicId: created.public_id }
    useChatStore.getState().setSelectionAsk(key, session)
  }
  if (input.quizMe === true) {
    await updateChatSessionQuizme(session.id, true)
  }
  const store = useChatStore.getState()
  store.openSession(session)
  store.queueSend({
    content: input.content,
    attachments: input.materials.map(({ id, title }) => ({
      kind: 'material',
      id,
      title,
    })),
    mode: 'send',
  })
  return session
}
