import {
  listChatMessages,
  type ChatMessage,
  type ChatSession,
} from '@/lib/api'

function messageToSection(message: ChatMessage): string {
  const role = message.role === 'user' ? '🙋 Question' : '🤖 Tutor'
  const lines: string[] = [`### ${role}`, '', message.markdown]
  for (const citation of message.citations ?? []) {
    lines.push(`> [${citation.index}] ${citation.title} — “${citation.quote}”`)
  }
  return lines.join('\n')
}

export function messagesToMarkdown(
  title: string,
  messages: ChatMessage[],
): string {
  const header = [`# ${title}`, '', '']
  const body = messages.map(messageToSection)
  return [...header, body.join('\n\n'), ''].join('\n')
}

function slugify(title: string): string {
  const slug = title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return slug || 'chat'
}

export async function exportSessionAsMarkdown(session: ChatSession): Promise<void> {
  const messages = await listChatMessages(session.id)
  const markdown = messagesToMarkdown(session.title || 'Chat', messages)
  const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${slugify(session.title || 'chat')}.md`
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
