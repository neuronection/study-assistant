import type { ChatMessageView } from '@/components/ui/chat-core'
import type { Block } from '@/components/blocks/types'
import type { ChatMessage as ChatMessageRow } from '@/lib/api'

const STRUCTURED_BLOCK_TYPES = new Set<Block['type']>([
  'chart',
  'geo',
  'widget',
  'image',
  'image_ref',
  'drawing',
  'mention',
  'table',
])

export function hasStructuredBlocks(message: ChatMessageRow): boolean {
  const blocks = message.blocks
  if (blocks === undefined || blocks.length === 0) {
    return false
  }
  return (blocks as Block[]).some((block) => STRUCTURED_BLOCK_TYPES.has(block.type))
}

export function toChatMessageView(message: ChatMessageRow): ChatMessageView {
  const count = message.variant_count ?? 1
  return {
    id: String(message.id),
    role: message.role === 'user' || message.role === 'system' ? message.role : 'assistant',
    content: message.markdown,
    status: 'done',
    parentId: message.parent_id != null ? String(message.parent_id) : null,
    variants:
      count > 1
        ? {
            index: message.variant_index ?? 1,
            count,
            siblingIds: (message.sibling_ids ?? []).map(String),
          }
        : undefined,
  }
}
