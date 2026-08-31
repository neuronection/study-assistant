import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowUp,
  Bot,
  Camera,
  ChevronDown,
  Copy,
  History,
  Maximize2,
  MessageSquare,
  Minimize2,
  Pencil,
  PenTool,
  Plus,
  RotateCcw,
  Sigma,
  Sparkles,
  Square,
  Wrench,
  X,
} from 'lucide-react'
import {
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import { useTranslation } from 'react-i18next'

import { BlockRenderer } from '@/components/blocks/BlockRenderer'
import type { Block, WidgetBlock } from '@/components/blocks/types'
import { DictationMicButton, DictationStrip } from '@/components/dictation/DictationStrip'
import { useDictation } from '@/components/dictation/useDictation'
import { Button } from '@/components/ui/button'
import { Popover } from '@/components/ui/popover'
import { EntityMention } from '@/features/ai/EntityMention'
import { ContextPanel, ReadIndicator } from '@/features/ai/ContextPanel'
import { GenerateDialog } from '@/features/ai/GenerateDialog'
import { ProposalCard, type GenerateRequest } from '@/features/ai/ProposalCard'
import { AttachMenu, CHAT_UPLOADS_FOLDER, ATTACH_KIND_ICONS, type PendingAttachment } from '@/features/chat/AttachMenu'
import { BranchTreeButton } from '@/features/chat/BranchTreePanel'
import { DrawingDialog, EquationDialog, ScreenshotDialog } from '@/features/chat/ComposerExtras'
import { ChatSessionList } from '@/features/chat/ChatSessionList'
import { StreamingBubble } from '@/features/chat/StreamingBubble'
import { ReasoningBubble } from '@/features/chat/ReasoningBubble'
import { ToolCallCard } from '@/features/chat/ToolCallCard'
import { TraceTimeline } from '@/features/chat/TraceTimeline'
import { TurnTraceStatus } from '@/features/chat/TurnTraceStatus'
import { useStreamBuffer } from '@/features/chat/useStreamBuffer'
import { chatUploadFolderName, chatUploadFolderPattern, resolveUploadCourse } from '@/features/chat/uploadCourse'
import { ToolsDialog } from '@/features/chat/ToolsDialog'
import { useMaterialUpload, type UploadItem } from '@/components/materials/materialUpload'
import {
  createChatSession,
  createFolder,
  editChatMessage,
  getChatContext,
  getProfilePreferences,
  listChatMessages,
  listChatSessions,
  listCourses,
  listFolders,
  listMaterials,
  patchChatMessageState,
  regenerateChatMessage,
  renameFolder,
  selectChatVariant,
  sendChatMessage,
  stopChatTurn,
  updateChatSessionEmbeddings,
  type ChatMessage,
  type ChatSession,
  type ChatToolCall,
  type ChatTrace,
} from '@/lib/api'
import { diffState } from '@/lib/state'
import { useWorkspaceStore } from '@/lib/workspace-store'
import { getWsClient } from '@/lib/ws-client'

import { cn } from '@/lib/utils'
import { storageKeys, WsTopic } from '@/lib/constants'

const CHAT_WIDTH_KEY = storageKeys.chatWidth
const CHAT_MIN_WIDTH = 320
const CHAT_MAX_WIDTH = 720
const CHAT_DEFAULT_WIDTH = 384

function readChatWidth(): number {
  try {
    const raw = window.localStorage.getItem(CHAT_WIDTH_KEY)
    if (raw) {
      const value = Number(raw)
      if (Number.isFinite(value) && value >= CHAT_MIN_WIDTH && value <= CHAT_MAX_WIDTH) {
        return value
      }
    }
  } catch {
    // persistence is best-effort
  }
  return CHAT_DEFAULT_WIDTH
}

function saveChatWidth(width: number): void {
  try {
    window.localStorage.setItem(CHAT_WIDTH_KEY, String(width))
  } catch {
    // persistence is best-effort
  }
}

function Citations({ message }: { message: ChatMessage }) {  if (message.citations.length === 0) {
    return null
  }
  return (
    <div className="mt-2 flex flex-wrap gap-1">
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

const MessageBubble = memo(function MessageBubble({
  message,
  onOpenGenerate,
  onEditResend,
  onRegenerate,
  onSwitchVariant,
  actionPending,
}: {
  message: ChatMessage
  onOpenGenerate?: (request: GenerateRequest) => void
  onEditResend?: (messageId: number, content: string) => void
  onRegenerate?: (userMessageId: number) => void
  onSwitchVariant?: (messageId: number) => void
  actionPending?: boolean
}) {
  const { t } = useTranslation()
  const isUser = message.role === 'user'
  const [editing, setEditing] = useState(false)
  const [editDraft, setEditDraft] = useState('')
  const [copied, setCopied] = useState(false)
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
  const variantCount = message.variant_count ?? 1
  const variantIndex = message.variant_index ?? 1
  const siblingIds = message.sibling_ids ?? []
  return (
    <div
      className={cn(
        'group flex animate-in fade-in slide-in-from-bottom-1 flex-col duration-200',
        isUser ? 'items-end' : 'items-start',
      )}
    >
      <div
        className={cn(
          'max-w-[92%] min-w-0 rounded-xl px-3 py-2 text-sm',
          isUser ? 'bg-primary text-primary-foreground' : 'bg-subtle',
          editing && 'w-[92%]',
        )}
      >
        {editing ? (
          <div className="flex flex-col gap-2">
            <textarea
              aria-label={t('chat.msg.edit')}
              autoFocus
              rows={Math.min(8, Math.max(2, editDraft.split('\n').length))}
              className="text-foreground placeholder:text-muted-foreground w-full resize-none rounded-md border border-border bg-surface px-2 py-1.5 text-sm outline-none focus:border-ring"
              value={editDraft}
              onChange={(event) => setEditDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
                  event.preventDefault()
                  submitEdit()
                } else if (event.key === 'Escape') {
                  event.preventDefault()
                  setEditing(false)
                }
              }}
            />
            <div className="flex justify-end gap-1.5">
              <Button
                size="sm"
                variant="ghost"
                disabled={actionPending}
                onClick={() => setEditing(false)}
                title={t('chat.msg.cancelEdit')}
              >
                {t('chat.msg.cancelEdit')}
              </Button>
              <Button
                size="sm"
                disabled={actionPending || editDraft.trim().length === 0}
                onClick={submitEdit}
                title={t('chat.msg.saveAndResend')}
              >
                {t('chat.msg.saveAndResend')}
              </Button>
            </div>
          </div>
        ) : (
          <>
            {!isUser && message.grounded === false ? (
              <p className="text-muted-foreground mb-2 flex items-center gap-1 text-[11px] italic">
                <AlertTriangle className="size-3" aria-hidden />
                {t('chat.notGrounded')}
              </p>
            ) : null}
            <BlockRenderer
              blocks={blocks}
              onWidgetStateChange={handleWidgetState}
            />
          </>
        )}
      </div>
      {isUser && (message.mentions ?? []).length > 0 ? (
        <div className="mt-1 flex max-w-[92%] flex-wrap justify-end gap-1">
          {(message.mentions ?? []).map((mention) => (
            <EntityMention key={mention.ref} mention={mention} />
          ))}
        </div>
      ) : null}
      {(message.warnings ?? []).length > 0 ? (
        <div className="mt-1 flex w-full max-w-[92%] flex-col gap-1">
          {(message.warnings ?? []).map((warning, index) => (
            <p
              key={index}
              className="text-warning flex items-start gap-1 text-[11px]"
            >
              <AlertTriangle className="mt-0.5 size-3 shrink-0" aria-hidden />
              {warning}
            </p>
          ))}
        </div>
      ) : null}
      {!isUser ? (
        <div className="mt-1 flex flex-wrap items-center gap-1.5">
          {(message.reads ?? []).map((read) => (
            <ReadIndicator key={read.ref} read={read} />
          ))}
        </div>
      ) : null}
      {!isUser && (message.tool_calls ?? []).length > 0 ? (
        <div className="mt-1 flex w-full max-w-[92%] flex-col gap-1">
          {(message.tool_calls ?? []).map((tool, index) => (
            <ToolCallCard key={`${tool.name}-${tool.argument}-${index}`} tool={tool} />
          ))}
        </div>
      ) : null}
      {!isUser
        ? (message.proposals ?? []).map((proposal) => (
            <ProposalCard
              key={proposal.id}
              proposal={proposal}
              onOpenGenerate={onOpenGenerate}
            />
          ))
        : null}
      {!isUser ? <Citations message={message} /> : null}
      {!isUser && message.trace ? (
        <TraceTimeline trace={message.trace} toolCalls={message.tool_calls ?? []} />
      ) : null}
      {editing ? null : (
        <div
          className={cn(
            'opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100',
            'mt-1 flex items-center gap-1',
            variantCount > 1 ? '' : '',
          )}
        >
          <button
            type="button"
            aria-label={copied ? t('chat.msg.copied') : t('chat.msg.copy')}
            title={copied ? t('chat.msg.copied') : t('chat.msg.copy')}
            className="text-muted-foreground hover:text-foreground rounded p-1 transition-colors"
            onClick={() => void copyMessage()}
          >
            <Copy className={cn('size-3.5', copied && 'text-success')} aria-hidden />
          </button>
          {isUser && onEditResend ? (
            <button
              type="button"
              aria-label={t('chat.msg.edit')}
              title={t('chat.msg.edit')}
              disabled={actionPending}
              className="text-muted-foreground hover:text-foreground rounded p-1 transition-colors disabled:opacity-40"
              onClick={startEdit}
            >
              <Pencil className="size-3.5" aria-hidden />
            </button>
          ) : null}
          {!isUser && onRegenerate && message.parent_id != null ? (
            <button
              type="button"
              aria-label={t('chat.msg.retry')}
              title={t('chat.msg.retry')}
              disabled={actionPending}
              className="text-muted-foreground hover:text-foreground rounded p-1 transition-colors disabled:opacity-40"
              onClick={() => onRegenerate(message.parent_id as number)}
            >
              <RotateCcw className="size-3.5" aria-hidden />
            </button>
          ) : null}
        </div>
      )}
      {variantCount > 1 && !editing ? (
        <div className="text-muted-foreground mt-0.5 flex items-center gap-1 text-[11px]">
          <button
            type="button"
            aria-label={t('chat.msg.previousVariant')}
            title={t('chat.msg.previousVariant')}
            disabled={
              actionPending || variantIndex <= 1 || siblingIds[variantIndex - 2] == null
            }
            className="hover:text-foreground rounded px-1 transition-colors disabled:opacity-40"
            onClick={() => {
              const target = siblingIds[variantIndex - 2]
              if (target != null && onSwitchVariant) onSwitchVariant(target)
            }}
          >
            ‹
          </button>
          <span title={t('chat.msg.variantOf', { index: variantIndex, count: variantCount })}>
            {variantIndex}/{variantCount}
          </span>
          <button
            type="button"
            aria-label={t('chat.msg.nextVariant')}
            title={t('chat.msg.nextVariant')}
            disabled={
              actionPending ||
              variantIndex >= variantCount ||
              siblingIds[variantIndex] == null
            }
            className="hover:text-foreground rounded px-1 transition-colors disabled:opacity-40"
            onClick={() => {
              const target = siblingIds[variantIndex]
              if (target != null && onSwitchVariant) onSwitchVariant(target)
            }}
          >
            ›
          </button>
        </div>
      ) : null}
    </div>
  )
})

function ThinkingDots({ label }: { label: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={label}
      className="bg-subtle flex items-center gap-2 rounded-xl px-3 py-2.5"
    >
      <span className="flex items-center gap-1" aria-hidden>
        {[0, 1, 2].map((index) => (
          <span
            key={index}
            className="chat-dot bg-muted-foreground size-1.5 rounded-full"
            style={{ animationDelay: `${index * 0.16}s` }}
          />
        ))}
      </span>
      <span className="text-muted-foreground text-xs">{label}</span>
    </div>
  )
}

function AttachChip({
  item,
  onRemove,
}: {
  item: PendingAttachment
  onRemove: () => void
}) {
  const { t } = useTranslation()
  const Icon = ATTACH_KIND_ICONS[item.kind].icon
  const removeLabel = t('chat.attach.remove', { title: item.title })
  return (
    <span
      className="border-border bg-subtle inline-flex max-w-full items-center gap-1 rounded-full border py-0.5 pl-2 pr-1 text-[11px] font-medium"
      title={item.title}
    >
      <Icon className="text-muted-foreground size-3 shrink-0" aria-hidden />
      <span className="max-w-[10rem] truncate">{item.title}</span>
      <button
        type="button"
        onClick={onRemove}
        aria-label={removeLabel}
        title={removeLabel}
        className="text-muted-foreground hover:text-foreground rounded-full p-0.5 transition-colors"
      >
        <X className="size-3" aria-hidden />
      </button>
    </span>
  )
}

export function ChatPanel({
  sessionId,
  onSessionCreated,
  onSelectSession,
  onNewChat,
  onClose,
  onExpand,
  onCollapse,
  variant = 'sidebar',
}: {
  sessionId: number | null
  onSessionCreated: (session: ChatSession) => void
  onSelectSession?: (session: ChatSession) => void
  onNewChat?: () => void
  onClose?: () => void
  onExpand?: () => void
  onCollapse?: () => void
  variant?: 'sidebar' | 'page'
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const activeSession = sessionId
  const courseId = useWorkspaceStore((state) => state.courseId)
  const [draft, setDraft] = useState('')
  const [pending, setPending] = useState(false)
  const { text: streamText, append: appendDelta, reset: resetStream } = useStreamBuffer()
  const {
    text: reasoningText,
    append: appendReasoning,
    reset: resetReasoning,
  } = useStreamBuffer()
  const [liveToolCalls, setLiveToolCalls] = useState<ChatToolCall[]>([])
  const [livePhase, setLivePhase] = useState('thinking')
  const [turnStartedAt, setTurnStartedAt] = useState<number | null>(null)
  const [turnError, setTurnError] = useState<string | null>(null)
  const [showTools, setShowTools] = useState(false)
  const [attachments, setAttachments] = useState<PendingAttachment[]>([])
  const [attachClose, setAttachClose] = useState(0)
  const [generateRequest, setGenerateRequest] = useState<GenerateRequest | null>(
    null,
  )
  const [composerDialog, setComposerDialog] = useState<
    'equation' | 'draw' | 'screenshot' | null
  >(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const sentCountRef = useRef(0)
  const sendingRef = useRef(false)
  const adoptingRef = useRef<number | null>(null)
  const ensureSessionRef = useRef<Promise<number | null> | null>(null)
  const createdSessionIdRef = useRef<number | null>(null)
  const [showScrollPill, setShowScrollPill] = useState(false)
  const isPage = variant === 'page'
  const [width, setWidth] = useState(readChatWidth)
  const dragRef = useRef<{ startX: number; startWidth: number; width: number } | null>(null)

  const onResizeStart = (event: ReactPointerEvent<HTMLDivElement>) => {
    dragRef.current = { startX: event.clientX, startWidth: width, width }
    if (typeof event.currentTarget.setPointerCapture === 'function') {
      event.currentTarget.setPointerCapture(event.pointerId)
    }
  }

  const onResizeMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current
    if (!drag) return
    const next = Math.min(
      CHAT_MAX_WIDTH,
      Math.max(CHAT_MIN_WIDTH, drag.startWidth + (drag.startX - event.clientX)),
    )
    drag.width = next
    setWidth(next)
  }

  const onResizeEnd = () => {
    const drag = dragRef.current
    if (!drag) return
    dragRef.current = null
    saveChatWidth(drag.width)
  }

  const sessionContext = useQuery({
    queryKey: ['chat-context', activeSession],
    queryFn: () => getChatContext(activeSession!),
    enabled: activeSession !== null,
  })
  const sessionCourseId = sessionContext.data?.course_id ?? null
  const coursesQuery = useQuery({
    queryKey: ['courses'],
    queryFn: listCourses,
    enabled: sessionCourseId === null,
  })
  const fallbackCourse = useMemo(
    () => (sessionCourseId === null ? resolveUploadCourse(coursesQuery.data ?? []) : null),
    [sessionCourseId, coursesQuery.data],
  )
  const uploadCourseId = sessionCourseId ?? fallbackCourse?.id ?? null

  const sessions = useQuery({ queryKey: ['chat-sessions'], queryFn: () => listChatSessions() })
  const preferences = useQuery({
    queryKey: ['profile-preferences'],
    queryFn: getProfilePreferences,
    enabled: activeSession !== null,
  })
  const activeChatSession =
    sessions.data?.find((session) => session.id === activeSession) ?? null
  const semanticSearchOn =
    activeChatSession?.use_embeddings ?? (preferences.data?.use_embeddings ?? true)
  const toggleEmbeddings = useMutation({
    mutationFn: () => updateChatSessionEmbeddings(activeSession!, !semanticSearchOn),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['chat-sessions'] })
    },
  })
  const messages = useQuery({
    queryKey: ['chat-messages', activeSession],
    queryFn: () => listChatMessages(activeSession!),
    enabled: activeSession !== null,
    refetchInterval: pending ? 2000 : false,
  })

  const branchEdit = useMutation({
    mutationFn: ({ messageId, content }: { messageId: number; content: string }) =>
      editChatMessage(messageId, content),
    onSuccess: () => {
      setPending(true)
      void queryClient.invalidateQueries({
        queryKey: ['chat-messages', activeSession],
      })
    },
  })
  const branchRegenerate = useMutation({
    mutationFn: (messageId: number) => regenerateChatMessage(messageId),
    onSuccess: () => {
      setPending(true)
      void queryClient.invalidateQueries({
        queryKey: ['chat-messages', activeSession],
      })
    },
  })
  const branchSelect = useMutation({
    mutationFn: (messageId: number) => selectChatVariant(messageId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ['chat-messages', activeSession],
      })
    },
  })

  const stopTurn = useMutation({
    mutationFn: () => stopChatTurn(activeSession!),
  })

  const canSend = draft.trim().length > 0 && !pending

  const send = useMutation({
    mutationFn: async (): Promise<{ sessionId: number }> => {
      const content = draft.trim()
      const attachmentPayload = attachments.map(({ kind, id }) => ({ kind, id }))
      let sessionId = activeSession
      if (sessionId === null) {
        const created = await createChatSession(
          courseId,
          undefined,
          content.slice(0, 60),
        )
        sessionId = created.id
        adoptingRef.current = created.id
        onSessionCreated(created)
        await queryClient.invalidateQueries({ queryKey: ['chat-sessions'] })
      }
      await sendChatMessage(sessionId, content, attachmentPayload)
      return { sessionId }
    },
    onMutate: () => {
      sendingRef.current = true
      sentCountRef.current = messages.data?.length ?? 0
      setPending(true)
      setTurnError(null)
    },
    onSuccess: async ({ sessionId }) => {
      setDraft('')
      setAttachments([])
      await queryClient.invalidateQueries({
        queryKey: ['chat-messages', sessionId],
      })
    },
    onError: () => setPending(false),
    onSettled: () => {
      sendingRef.current = false
    },
  })

  useEffect(() => {
    if (activeSession === null) {
      return
    }
    const unsubscribe = getWsClient().subscribe(WsTopic.chat(Number(activeSession)), (_payload) => {
      const event = _payload as
        | {
            type: string
            delta?: string
            kind?: string
            name?: string
            argument?: string
            result?: string
            title?: string
            phase?: string
            detail?: string
            status?: string
            start_ms?: number
            duration_ms?: number
            elapsed_ms?: number
            trace?: ChatTrace
          }
        | null
        | undefined
      if (!event || typeof event.type !== 'string') {
        return
      }
      if (event.type === 'stream_start') {
        setPending(true)
        resetStream()
        resetReasoning()
        setLiveToolCalls([])
        setLivePhase('thinking')
        setTurnStartedAt(Date.now())
      } else if (event.type === 'phase') {
        setLivePhase(event.phase ?? 'thinking')
      } else if (event.type === 'stream_delta' && event.delta) {
        if (event.kind === 'reasoning') {
          appendReasoning(event.delta)
        } else {
          appendDelta(event.delta)
        }
      } else if (event.type === 'tool_call') {
        resetStream()
        setLiveToolCalls((current) => [
          ...current,
          {
            name: event.name ?? '',
            argument: event.argument ?? '',
            result: event.result ?? null,
            title: event.title ?? null,
            phase: event.phase ?? null,
            status: event.status ?? null,
            start_ms: event.start_ms ?? null,
            duration_ms: event.duration_ms ?? null,
          },
        ])
      } else if (event.type === 'assistant_message') {
        setPending(false)
        resetStream()
        resetReasoning()
        setLiveToolCalls([])
        setTurnStartedAt(null)
        void queryClient.invalidateQueries({
          queryKey: ['chat-messages', activeSession],
        })
      } else if (event.type === 'stream_interrupted') {
        setPending(false)
        resetStream()
        resetReasoning()
        setLiveToolCalls([])
        setTurnStartedAt(null)
        void queryClient.invalidateQueries({
          queryKey: ['chat-messages', activeSession],
        })
      } else if (event.type === 'turn_error') {
        setPending(false)
        resetStream()
        resetReasoning()
        setLiveToolCalls([])
        setTurnStartedAt(null)
        setTurnError(event.detail || t('chat.turnFailed'))
      }
    })
    return unsubscribe
  }, [activeSession, queryClient, t, appendDelta, resetStream, appendReasoning, resetReasoning])

  useEffect(() => {
    const element = scrollRef.current
    if (!element) {
      return
    }
    if (typeof requestAnimationFrame !== 'function') {
      element.scrollTop = element.scrollHeight
      return
    }
    const id = requestAnimationFrame(() => {
      element.scrollTop = element.scrollHeight
    })
    return () => cancelAnimationFrame(id)
  }, [messages.data, streamText, reasoningText, pending])

  useEffect(() => {
    const list = messages.data
    if (
      pending &&
      list !== undefined &&
      list.length > sentCountRef.current &&
      list[list.length - 1].role === 'assistant'
    ) {
      setPending(false)
      resetStream()
      resetReasoning()
      setLiveToolCalls([])
    }
  }, [messages.data, pending, resetStream, resetReasoning])

  useEffect(() => {
    if (!pending) {
      return undefined
    }
    const timer = window.setTimeout(() => {
      setPending(false)
      resetStream()
      resetReasoning()
      setLiveToolCalls([])
      setTurnError(t('chat.timeout'))
    }, 90_000)
    return () => window.clearTimeout(timer)
  }, [pending, t, resetStream, resetReasoning])

  useEffect(() => {
    const element = textareaRef.current
    if (element) {
      element.style.height = 'auto'
      element.style.height = `${Math.min(element.scrollHeight, 144)}px`
    }
  }, [draft])

  const handleAttach = (item: PendingAttachment) => {
    setAttachments((current) =>
      current.some((entry) => entry.kind === item.kind && entry.id === item.id)
        ? current
        : [...current, item],
    )
    setAttachClose((current) => current + 1)
  }

  const ensureUploadSession = useCallback((): Promise<number | null> => {
    const known = activeSession ?? createdSessionIdRef.current
    if (known !== null) {
      return Promise.resolve(known)
    }
    if (uploadCourseId === null) {
      return Promise.resolve(null)
    }
    if (ensureSessionRef.current === null) {
      const created = (async () => {
        const session = await createChatSession(uploadCourseId, undefined, t('chat.newSession'))
        createdSessionIdRef.current = session.id
        adoptingRef.current = session.id
        onSessionCreated(session)
        await queryClient.invalidateQueries({ queryKey: ['chat-sessions'] })
        return session.id
      })()
      ensureSessionRef.current = created
      void created.catch(() => {
        if (ensureSessionRef.current === created) {
          ensureSessionRef.current = null
        }
      })
    }
    return ensureSessionRef.current
  }, [activeSession, uploadCourseId, t, onSessionCreated, queryClient])

  const ensureChatUploadFolder = useCallback(async (): Promise<number | null> => {
    if (uploadCourseId === null) {
      return null
    }
    const folders = await listFolders(uploadCourseId)
    const root =
      folders.find((folder) => folder.name === CHAT_UPLOADS_FOLDER && folder.parent_id === null) ??
      folders.find((folder) => folder.name === CHAT_UPLOADS_FOLDER) ??
      (await createFolder(CHAT_UPLOADS_FOLDER, null, uploadCourseId))
    const sessionId = await ensureUploadSession()
    if (sessionId === null) {
      return root.id
    }
    const title =
      sessions.data?.find((session) => session.id === sessionId)?.title ?? t('chat.newSession')
    const expected = chatUploadFolderName(title, sessionId)
    const existing = folders.find((folder) => folder.parent_id === root.id && folder.name === expected)
    if (existing !== undefined) {
      return existing.id
    }
    const pattern = chatUploadFolderPattern(sessionId)
    const legacy = folders.find((folder) => folder.parent_id === root.id && pattern.test(folder.name))
    if (legacy !== undefined) {
      return (await renameFolder(legacy.id, expected)).id
    }
    return (await createFolder(expected, root.id, uploadCourseId)).id
  }, [uploadCourseId, ensureUploadSession, sessions.data, t])

  const nameChatUpload = useCallback(
    async (item: UploadItem, folderId: number | null): Promise<string> => {
      if (item.label === undefined || folderId === null || uploadCourseId === null) {
        return item.file.name
      }
      const existing = await listMaterials(folderId, uploadCourseId)
      const pattern = new RegExp(`^${item.label} (\\d+)(\\.[^.]+)?$`)
      let max = 0
      for (const material of existing) {
        const match = pattern.exec(material.title)
        if (match !== null) {
          max = Math.max(max, Number(match[1]))
        }
      }
      const dot = item.file.name.lastIndexOf('.')
      const ext = dot > 0 ? item.file.name.slice(dot) : ''
      return `${item.label} ${max + 1}${ext}`
    },
    [uploadCourseId],
  )

  const chatUpload = useMaterialUpload({
    courseId: uploadCourseId,
    getFolderId: ensureChatUploadFolder,
    nameFile: nameChatUpload,
    onUploaded: async (result) => {
      handleAttach({
        kind: 'material',
        id: result.material.id,
        title: result.material.title,
      })
    },
  })

  const fallbackUploadHint =
    sessionCourseId === null && fallbackCourse !== null
      ? {
          attach: t('chat.attach.uploadHintFallback', { course: fallbackCourse.title }),
          draw: t('chat.composer.drawHintFallback', { course: fallbackCourse.title }),
          screenshot: t('chat.composer.screenshotHintFallback', {
            course: fallbackCourse.title,
          }),
        }
      : null

  const insertIntoDraft = (text: string) => {
    const element = textareaRef.current
    if (!element) {
      setDraft((current) => `${current}${text}`)
      return
    }
    const start = element.selectionStart ?? draft.length
    const end = element.selectionEnd ?? draft.length
    setDraft((current) => `${current.slice(0, start)}${text}${current.slice(end)}`)
    const caret = start + text.length
    requestAnimationFrame(() => {
      element.focus()
      element.setSelectionRange(caret, caret)
    })
  }

  const dictation = useDictation({
    onResult: (text) => insertIntoDraft(`${text} `),
  })

  const [historyClose, setHistoryClose] = useState(0)

  const activeTitle = activeSession === null
    ? t('chat.newSession')
    : (sessions.data?.find((session) => session.id === activeSession)?.title ??
      t('chat.newSession'))

  useEffect(() => {
    if (activeSession !== null && adoptingRef.current === activeSession) {
      adoptingRef.current = null
      return
    }
    if (sendingRef.current) {
      return
    }
    setPending(false)
    resetStream()
    resetReasoning()
    setLiveToolCalls([])
    setTurnError(null)
    setDraft('')
    setAttachments([])
  }, [activeSession, resetStream, resetReasoning])

  const suggestions = [t('chat.suggest1'), t('chat.suggest2'), t('chat.suggest3')]

  return (
    <aside
      className={cn(
        'bg-surface flex flex-col border-border',
        isPage ? 'relative h-full w-full' : 'relative h-full shrink-0 border-l',
      )}
      style={isPage ? undefined : { width }}
    >
      {!isPage ? (
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label={t('chat.resize')}
          title={t('chat.resize')}
          className="hover:bg-primary/40 active:bg-primary/60 absolute top-0 -left-0.5 z-10 h-full w-1 cursor-col-resize transition-colors"
          onPointerDown={onResizeStart}
          onPointerMove={onResizeMove}
          onPointerUp={onResizeEnd}
          onPointerCancel={onResizeEnd}
        />
      ) : null}
      <header className="border-border flex items-center justify-between border-b px-4 py-3">
        <span className="flex items-center gap-2 text-sm font-semibold">
          <MessageSquare className="size-4" aria-hidden />
          {t('chat.title')}
        </span>
        <div className="flex items-center gap-1">
          {activeSession !== null ? <BranchTreeButton sessionId={activeSession} /> : null}
          <Button
            variant="ghost"
            size="icon"
            onClick={() => toggleEmbeddings.mutate()}
            disabled={activeSession === null || toggleEmbeddings.isPending}
            title={semanticSearchOn ? t('chat.searchOn') : t('chat.searchOff')}
            aria-pressed={semanticSearchOn}
          >
            <Sparkles className="size-4" aria-hidden />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setShowTools(true)}
            title={t('chat.tools.buttonTitle')}
          >
            <Wrench className="size-4" aria-hidden />
          </Button>
          {isPage ? (
            <Button
              variant="ghost"
              size="icon"
              onClick={onCollapse}
              title={t('chat.collapse')}
              aria-label={t('chat.collapse')}
            >
              <Minimize2 className="size-4" aria-hidden />
            </Button>
          ) : (
            <>
              <Button
                variant="ghost"
                size="icon"
                onClick={onExpand}
                title={t('chat.expand')}
                aria-label={t('chat.expand')}
              >
                <Maximize2 className="size-4" aria-hidden />
              </Button>
              {onClose ? (
                <Button variant="ghost" size="icon" onClick={onClose} title={t('chat.close')}>
                  <X className="size-4" aria-hidden />
                </Button>
              ) : null}
            </>
          )}
        </div>
      </header>

      {!isPage ? (
        <div className="border-border flex items-center gap-2 border-b px-3 py-2">
          <Popover
            label={t('chat.history')}
            side="bottom"
            align="start"
            closeSignal={historyClose}
            triggerClassName="min-w-0 flex-1 justify-start gap-2 rounded-md px-2 py-1.5 text-xs"
            panelClassName="w-72 p-0"
            trigger={
              <span className="flex min-w-0 flex-1 items-center gap-2">
                <History className="text-muted-foreground size-3.5 shrink-0" aria-hidden />
                <span className="min-w-0 flex-1 truncate">{activeTitle}</span>
                <ChevronDown className="text-muted-foreground size-3.5 shrink-0" aria-hidden />
              </span>
            }
          >
            <div className="h-[26rem]">
              <ChatSessionList
                onSelect={() => setHistoryClose((current) => current + 1)}
                onSelectSession={onSelectSession}
                onNewChat={onNewChat}
                activeSessionId={activeSession}
              />
            </div>
          </Popover>
        </div>
      ) : null}

      {activeSession !== null ? <ContextPanel sessionId={activeSession} /> : null}

      <div
        ref={scrollRef}
        className="relative flex-1 space-y-3 overflow-y-auto p-3"
        onScroll={(event) => {
          const element = event.currentTarget
          setShowScrollPill(
            element.scrollHeight - element.scrollTop - element.clientHeight > 120,
          )
        }}
      >
        {(messages.data ?? []).length === 0 && !pending && streamText === null ? (
          <div className="flex animate-in fade-in flex-col items-center gap-3 pt-10 text-center duration-300">
            <span className="bg-subtle flex size-10 items-center justify-center rounded-full">
              <Bot className="text-muted-foreground size-5" aria-hidden />
            </span>
            <p className="text-muted-foreground max-w-[16rem] text-xs">
              {t('chat.emptyHint')}
            </p>
            <div className="flex flex-col gap-1.5">
              {suggestions.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() => setDraft(suggestion)}
                  className="border-border hover:bg-subtle rounded-full border px-3 py-1.5 text-xs transition-colors"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        ) : null}
        {(messages.data ?? []).map((message) => (
          <MessageBubble
            key={message.id}
            message={message}
            onOpenGenerate={setGenerateRequest}
            onEditResend={(messageId, content) =>
              branchEdit.mutate({ messageId, content })
            }
            onRegenerate={(userMessageId) => branchRegenerate.mutate(userMessageId)}
            onSwitchVariant={(messageId) => branchSelect.mutate(messageId)}
            actionPending={
              pending || branchEdit.isPending || branchRegenerate.isPending
            }
          />
        ))}
        {reasoningText !== null ? <ReasoningBubble text={reasoningText} /> : null}
        {streamText !== null ? (
          <div className="flex flex-col items-start">
            <StreamingBubble text={streamText} />
            {turnStartedAt !== null ? (
              <TurnTraceStatus phase={livePhase} startedAt={turnStartedAt} />
            ) : null}
          </div>
        ) : null}
        {liveToolCalls.length > 0 ? (
          <div className="flex w-full max-w-[92%] animate-in fade-in flex-col gap-1 duration-200">
            {liveToolCalls.map((tool, index) => (
              <ToolCallCard key={`${tool.name}-${tool.argument}-${index}`} tool={tool} />
            ))}
          </div>
        ) : null}
        {pending && streamText === null && reasoningText === null ? (
          <ThinkingDots label={t('chat.thinking')} />
        ) : null}
        {showScrollPill ? (
          <button
            type="button"
            title={t('chat.scrollToBottom')}
            aria-label={t('chat.scrollToBottom')}
            className="bg-surface border-border text-muted-foreground hover:text-foreground sticky bottom-0 left-1/2 flex size-8 -translate-x-1/2 items-center justify-center rounded-full border shadow-md transition-colors"
            onClick={() => {
              const element = scrollRef.current
              if (element) {
                element.scrollTop = element.scrollHeight
                setShowScrollPill(false)
              }
            }}
          >
            <ChevronDown className="size-4" aria-hidden />
          </button>
        ) : null}
      </div>

      {turnError !== null ? (
        <div
          role="alert"
          className="border-border text-danger mx-3 mb-2 flex items-start gap-2 rounded-lg border border-dashed px-3 py-2 text-xs"
        >
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          <span className="min-w-0 flex-1 break-words">
            {t('chat.turnFailed')}
            {turnError ? ` (${turnError})` : ''}
          </span>
          <button
            type="button"
            aria-label={t('chat.dismissError')}
            title={t('chat.dismissError')}
            onClick={() => setTurnError(null)}
            className="text-danger rounded-full p-0.5 transition-colors hover:opacity-70"
          >
            <X className="size-3.5" aria-hidden />
          </button>
        </div>
      ) : null}
      <form
        className="border-border border-t p-3"
        onSubmit={(event) => {
          event.preventDefault()
          if (canSend) {
            send.mutate()
          }
        }}
      >
        <div className="border-border focus-within:border-ring bg-surface flex flex-col rounded-xl border transition-colors">
          {attachments.length > 0 ? (
            <div className="flex flex-wrap gap-1 p-2 pb-0">
              {attachments.map((item) => (
                <AttachChip
                  key={`${item.kind}-${item.id}`}
                  item={item}
                  onRemove={() =>
                    setAttachments((current) =>
                      current.filter(
                        (entry) => !(entry.kind === item.kind && entry.id === item.id),
                      ),
                    )
                  }
                />
              ))}
            </div>
          ) : null}
          {dictation.status !== 'idle' || dictation.error !== null ? (
            <div className="px-2 pt-2">
              <DictationStrip
                status={dictation.status}
                seconds={dictation.seconds}
                levelRef={dictation.levelRef}
                error={dictation.error}
                stopLabel={t('dictation.stop')}
                cancelLabel={t('dictation.cancel')}
                onStop={() => void dictation.stop()}
                onCancel={dictation.cancel}
                onDismissError={dictation.dismissError}
              />
            </div>
          ) : null}
          <div className="flex items-end gap-1 p-1.5">
            <Popover
              side="top"
              align="start"
              panelClassName="w-[21rem] p-2"
              label={t('chat.attach.buttonTitle')}
              closeSignal={attachClose}
              trigger={<Plus className="size-4" aria-hidden />}
            >
              <AttachMenu
                courseId={sessionCourseId}
                uploadCourseId={uploadCourseId}
                uploadHint={fallbackUploadHint?.attach}
                resolveUploadFolder={ensureChatUploadFolder}
                attached={attachments}
                onSelect={handleAttach}
                extraActions={[
                  {
                    key: 'equation',
                    icon: Sigma,
                    label: t('chat.composer.equation'),
                    run: () => setComposerDialog('equation'),
                  },
                  ...(uploadCourseId !== null
                    ? [
                        {
                          key: 'draw' as const,
                          icon: PenTool,
                          label: t('chat.composer.draw'),
                          run: () => setComposerDialog('draw'),
                        },
                        {
                          key: 'screenshot' as const,
                          icon: Camera,
                          label: t('chat.composer.screenshot'),
                          run: () => setComposerDialog('screenshot'),
                        },
                      ]
                    : []),
                ]}
              />
            </Popover>
            <textarea
              ref={textareaRef}
              rows={1}
              className="text-foreground placeholder:text-muted-foreground max-h-36 min-h-9 flex-1 resize-none bg-transparent px-1 py-1.5 text-sm outline-none"
              placeholder={t('chat.placeholder')}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault()
                  if (canSend) {
                    send.mutate()
                  }
                }
              }}
            />
            {pending && activeSession !== null ? (
              <Button
                type="button"
                size="icon"
                className="rounded-lg"
                disabled={stopTurn.isPending}
                title={t('chat.stop')}
                aria-label={t('chat.stop')}
                onClick={() => stopTurn.mutate()}
              >
                <Square className="size-4" aria-hidden />
              </Button>
            ) : (
              <>
                <DictationMicButton
                  status={dictation.status}
                  onStart={() => void dictation.start()}
                  label={t('dictation.start')}
                  className="rounded-lg"
                />
                <Button
                  type="submit"
                  size="icon"
                  className="rounded-lg"
                  disabled={!canSend}
                  title={t('chat.send')}
                >
                  <ArrowUp className="size-4" aria-hidden />
                </Button>
              </>
            )}
          </div>
        </div>
      </form>

      {composerDialog === 'equation' ? (
        <EquationDialog
          onInsert={insertIntoDraft}
          onClose={() => setComposerDialog(null)}
        />
      ) : null}
      {composerDialog === 'draw' && uploadCourseId !== null ? (
        <DrawingDialog
          upload={chatUpload}
          hint={fallbackUploadHint?.draw}
          onClose={() => setComposerDialog(null)}
        />
      ) : null}
      {composerDialog === 'screenshot' && uploadCourseId !== null ? (
        <ScreenshotDialog
          upload={chatUpload}
          hint={fallbackUploadHint?.screenshot}
          onClose={() => setComposerDialog(null)}
        />
      ) : null}
      {showTools ? <ToolsDialog onClose={() => setShowTools(false)} /> : null}
      {generateRequest !== null ? (
        <GenerateDialog
          task={generateRequest.task}
          courseId={sessionContext.data?.course_id ?? null}
          initial={{
            topic: generateRequest.params.topic ?? undefined,
            count: generateRequest.params.count ?? undefined,
            stepCount: generateRequest.params.steps ?? undefined,
            difficulty: generateRequest.params.difficulty ?? undefined,
          }}
          onClose={() => setGenerateRequest(null)}
          onSuccess={() => setGenerateRequest(null)}
        />
      ) : null}
    </aside>
  )
}
