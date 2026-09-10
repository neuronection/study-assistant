import { buildChatMarkdown, chatExportFileName, downloadChatMarkdown } from '@/components/ui/chat-export'
import { listChatMessages, type ChatMessage, type ChatSession } from '@/lib/api'

/** Conversation → Markdown on the library builder (study's heading style
 *  + citation blockquotes; the download/slug live in the library now). */
export function messagesToMarkdown(
  title: string,
  messages: ChatMessage[],
): string {
  const citationLines = messages.map((message) =>
    (message.citations ?? []).map(
      (citation) => `[${citation.index}] ${citation.title} — “${citation.quote}”`,
    ),
  )
  return buildChatMarkdown(
    title,
    messages.map((message) => ({ role: message.role, content: message.markdown })),
    {
      roleStyle: 'heading',
      userLabel: '🙋 Question',
      assistantLabel: '🤖 Tutor',
      annotations: (_message, index) => citationLines[index] ?? [],
    },
  )
}

export async function exportSessionAsMarkdown(session: ChatSession): Promise<void> {
  const messages = await listChatMessages(session.id)
  const markdown = messagesToMarkdown(session.title || 'Chat', messages)
  downloadChatMarkdown(markdown, chatExportFileName(session.title || 'chat'))
}
