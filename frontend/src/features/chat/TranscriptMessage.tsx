import { useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  mentionComponents,
  mentionUrlTransform,
  mentionsToMarkdownLinks,
  BlockRenderer,
} from '@/components/blocks/BlockRenderer'
import type { Block, WidgetBlock } from '@/components/blocks/types'
import { MarkdownSurface } from '@/components/ui/chat-markdown'
import { ChatMessage } from '@/components/ui/chat-message'
import { EntityMention } from '@/features/ai/EntityMention'
import { ProposalCard, type GenerateRequest } from '@/features/ai/ProposalCard'
import { ReadIndicator } from '@/features/ai/ContextPanel'
import { ChatToolCard } from '@/components/ui/chat-tool-card'
import { toolCardProps } from '@/features/chat/tools/registry'
import { normalizeMathFences } from '@/components/editor/markdownFidelity'
import { TraceTimeline } from '@/features/chat/TraceTimeline'
import { hasStructuredBlocks } from '@/features/chat/chatMessages'
import { ReadAloudButton } from '@/components/read-aloud/ReadAloudButton'
import { diffState } from '@/lib/state'
import { patchChatMessageState, type ChatMessage as ChatMessageRow } from '@/lib/api'
import type { ChatMessageView } from '@/components/ui/chat-core'

function MessageBlocks({ message }: { message: ChatMessageRow }) {
  const blocks = (message.blocks ?? [
    { type: 'text', md: message.markdown, mentions: message.mentions },
  ]) as Block[]
  const previousState = useRef<Map<string, Record<string, unknown>> | null>(null)
  if (previousState.current === null) {
    const seed = new Map<string, Record<string, unknown>>()
    for (const block of blocks) {
      if (block.type === 'widget') {
        const widget = block as WidgetBlock
        if (widget.id) {
          seed.set(widget.id, widget.state ?? {})
        }
      }
    }
    previousState.current = seed
  }
  const handleWidgetState = (widgetId: string, next: Record<string, unknown>) => {
    const prev = previousState.current?.get(widgetId) ?? {}
    const delta = diffState(prev, next)
    previousState.current?.set(widgetId, next)
    if (delta.length > 0) {
      void patchChatMessageState(message.id, delta)
    }
  }
  return <BlockRenderer blocks={blocks} onWidgetStateChange={handleWidgetState} />
}

function MessageContent({ message }: { message: ChatMessageRow }) {
  const mentions = useMemo(() => message.mentions ?? [], [message])
  const components = useMemo(
    () => (mentions.length > 0 ? mentionComponents(mentions) : undefined),
    [mentions],
  )
  if (hasStructuredBlocks(message)) {
    return <MessageBlocks message={message} />
  }
  const value = normalizeMathFences(
    mentions.length > 0 ? mentionsToMarkdownLinks(message.markdown, mentions) : message.markdown
  )
  return (
    <MarkdownSurface
      value={value}
      urlTransform={mentionUrlTransform}
      components={components}
    />
  )
}

function Citations({ message }: { message: ChatMessageRow }) {
  if (message.citations.length === 0) {
    return null
  }
  return (
    <div className="mt-1 flex flex-wrap gap-1">
      {message.citations.map((citation) => (
        <span
          key={citation.index}
          className="bg-subtle text-muted-foreground rounded-full px-2 py-0.5 text-[11px]"
          title={citation.quote}
        >
          [{citation.index}] {citation.title}
        </span>
      ))}
    </div>
  )
}

export function TranscriptMessage({
  message,
  view,
  actionPending,
  onOpenGenerate,
  onEditResend,
  onRegenerate,
  onSwitchVariant,
}: {
  message: ChatMessageRow
  view: ChatMessageView
  actionPending?: boolean
  onOpenGenerate?: (request: GenerateRequest) => void
  onEditResend?: (messageId: number, content: string) => void
  onRegenerate?: (userMessageId: number) => void
  onSwitchVariant?: (messageId: number) => void
}) {
  const { t } = useTranslation()
  const isUser = message.role === 'user'
  const [copied, setCopied] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editDraft, setEditDraft] = useState('')

  const copyMessage = async () => {
    try {
      await navigator.clipboard.writeText(message.markdown)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      setCopied(false)
    }
  }
  const startEdit = () => {
    setEditDraft(message.markdown)
    setEditing(true)
  }
  const submitEdit = () => {
    const content = editDraft.trim()
    if (content.length > 0 && onEditResend && !actionPending) {
      onEditResend(message.id, content)
    }
    setEditing(false)
  }

  const readAloud = !isUser ? <ReadAloudButton markdown={message.markdown} /> : null
  const meta =
    hasMessageMeta(message) || readAloud !== null ? (
      <span className="flex items-center gap-2">
        {readAloud}
        {hasMessageMeta(message) ? <TranscriptMessageMeta message={message} /> : null}
      </span>
    ) : undefined

  return (
    <ChatMessage
      role={view.role}
      status="done"
      content={<MessageContent message={message} />}
      meta={meta}
      editing={
        editing
          ? {
              value: editDraft,
              onValueChange: setEditDraft,
              onSubmit: submitEdit,
              onCancel: () => setEditing(false),
              submitDisabled: actionPending || editDraft.trim().length === 0,
            }
          : false
      }
      actions={{
        onCopy: () => void copyMessage(),
        onEdit:
          isUser && onEditResend !== undefined && !actionPending
            ? startEdit
            : undefined,
        onRegenerate:
          !isUser && onRegenerate !== undefined && message.parent_id != null && !actionPending
            ? () => onRegenerate(message.parent_id as number)
            : undefined,
      }}
      variants={view.variants}
      onSelectVariant={(id) => onSwitchVariant?.(Number(id))}
      chips={
        isUser && (message.mentions ?? []).length > 0 ? (
          <>
            {(message.mentions ?? []).map((mention) => (
              <EntityMention key={mention.ref} mention={mention} />
            ))}
          </>
        ) : undefined
      }
      labels={{
        copy: copied ? t('chat.msg.copied') : t('chat.msg.copy'),
        edit: t('chat.msg.edit'),
        regenerate: t('chat.msg.retry'),
        save: t('chat.msg.saveAndResend'),
        cancel: t('chat.msg.cancelEdit'),
        ariaLabel: t('chat.msg.edit'),
        variantOf: (index, count) => t('chat.msg.variantOf', { index, count }),
        previous: t('chat.msg.previousVariant'),
        next: t('chat.msg.nextVariant'),
      }}
    >
      {!isUser && (message.tool_calls ?? []).length > 0 ? (
        <>
          {(message.tool_calls ?? []).map((tool, index) => (
            <ChatToolCard
              key={`${tool.name}-${tool.argument}-${index}`}
              {...toolCardProps(tool, t)}
            />
          ))}
        </>
      ) : null}
      {!isUser
        ? (message.proposals ?? []).map((proposal) => (
            <ProposalCard key={proposal.id} proposal={proposal} onOpenGenerate={onOpenGenerate} />
          ))
        : null}
    </ChatMessage>
  )
}

export function hasMessageMeta(message: ChatMessageRow): boolean {
  const isUser = message.role === 'user'
  return (
    (!isUser && message.grounded === false) ||
    (message.warnings ?? []).length > 0 ||
    (!isUser && (message.reads ?? []).length > 0) ||
    (!isUser && message.citations.length > 0) ||
    (!isUser && message.trace !== null && message.trace !== undefined)
  )
}

export function TranscriptMessageMeta({ message }: { message: ChatMessageRow }) {
  const { t } = useTranslation()
  const isUser = message.role === 'user'
  const warnings = message.warnings ?? []
  const reads = isUser ? [] : (message.reads ?? [])
  const notGrounded = !isUser && message.grounded === false
  const showCitations = !isUser && message.citations.length > 0
  const showTrace = !isUser && message.trace !== null && message.trace !== undefined
  if (
    !notGrounded &&
    warnings.length === 0 &&
    reads.length === 0 &&
    !showCitations &&
    !showTrace
  ) {
    return null
  }
  return (
    <>
      {notGrounded ? (
        <p className="text-muted-foreground flex items-center gap-1 text-[11px] italic">
          {t('chat.notGrounded')}
        </p>
      ) : null}
      {warnings.length > 0 ? (
        <div className="flex flex-col gap-1">
          {warnings.map((warning, index) => (
            <p key={index} className="text-warning flex items-start gap-1 text-[11px]">
              {warning}
            </p>
          ))}
        </div>
      ) : null}
      {reads.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1.5">
          {reads.map((read) => (
            <ReadIndicator key={read.ref} read={read} />
          ))}
        </div>
      ) : null}
      {showCitations ? <Citations message={message} /> : null}
      {showTrace ? (
        <TraceTimeline trace={message.trace!} toolCalls={message.tool_calls ?? []} />
      ) : null}
    </>
  )
}
