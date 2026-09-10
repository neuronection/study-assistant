import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  Bot,
  Camera,
  ChevronDown,
  HelpCircle,
  History,
  Maximize2,
  MessageSquare,
  Minimize2,
  PenTool,
  Plus,
  Sigma,
  Sparkles,
  Wrench,
  X,
} from 'lucide-react'
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import { useTranslation } from 'react-i18next'

import {
  DictationButton,
  DictationStrip,
  useDictation,
} from '@/components/ui/dictation'
import { ChatComposer } from '@/components/ui/chat-composer'
import { ChatPanel as ChatPanelHost } from '@/components/ui/chat-panel'
import { Button } from '@/components/ui/button'
import { Popover } from '@/components/ui/popover'
import { ChatReasoning } from '@/components/ui/chat-reasoning'
import { ChatToolCard } from '@/components/ui/chat-tool-card'
import { ChatTurnStatus } from '@/components/ui/chat-turn-status'
import { MarkdownSurface } from '@/components/ui/chat-markdown'
import { normalizeMathFences } from '@/components/editor/markdownFidelity'
import { ChatMessage } from '@/components/ui/chat-message'
import { ContextPanel } from '@/features/ai/ContextPanel'
import { GenerateDialog } from '@/features/ai/GenerateDialog'
import { type GenerateRequest } from '@/features/ai/ProposalCard'
import { AttachMenu, CHAT_UPLOADS_FOLDER, ATTACH_KIND_ICONS, type PendingAttachment } from '@/features/chat/AttachMenu'
import { BranchTreeButton } from '@/features/chat/BranchTreeButton'
import { DrawingDialog, EquationDialog, ScreenshotDialog } from '@/features/chat/ComposerExtras'
import { ChatSessionList } from '@/features/chat/ChatSessionList'
import { toolCardProps } from '@/features/chat/tools/registry'
import { useReasoningOpen } from '@/features/chat/useReasoningOpen'
import { useStudyChatContext } from '@/features/chat/useStudyChat'
import { ChatTranscript } from '@/components/ui/chat-transcript'
import { toChatMessageView } from '@/features/chat/chatMessages'
import { TranscriptMessage } from '@/features/chat/TranscriptMessage'
import { chatUploadFolderName, chatUploadFolderPattern, resolveUploadCourse } from '@/features/chat/uploadCourse'
import { ToolsDialog } from '@/features/chat/ToolsDialog'
import { useMaterialUpload, type UploadItem } from '@/components/materials/materialUpload'
import {
  createChatSession,
  createFolder,
  getChatContext,
  getProfilePreferences,
  listChatMessages,
  listChatSessions,
  listCourses,
  listFolders,
  listMaterials,
  renameFolder,
  selectChatVariant,
  updateChatSessionEmbeddings,
  updateChatSessionQuizme,
  type ChatSession,
} from '@/lib/api'
import {
  transcribeViaGateway,
  classifyDictationError,
} from '@/lib/dictation'
import { useChatStore } from '@/lib/chat-store'
import { useWorkspaceStore } from '@/lib/workspace-store'

import { cn } from '@/lib/utils'

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
  onSessionCreated,
  onSelectSession,
  onNewChat,
  onClose,
  onExpand,
  onCollapse,
  variant = 'sidebar',
}: {
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
  const chat = useStudyChatContext()
  const stream = chat.stream
  const activeSession = chat.sessionId
  const courseId = useWorkspaceStore((state) => state.courseId)
  const [draft, setDraft] = useState('')
  const [showTools, setShowTools] = useState(false)
  const [attachments, setAttachments] = useState<PendingAttachment[]>([])
  const [attachClose, setAttachClose] = useState(0)
  const [generateRequest, setGenerateRequest] = useState<GenerateRequest | null>(
    null,
  )
  const [composerDialog, setComposerDialog] = useState<
    'equation' | 'draw' | 'screenshot' | null
  >(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const sentCountRef = useRef(0)
  const adoptingRef = useRef<number | null>(null)
  const ensureSessionRef = useRef<Promise<number | null> | null>(null)
  const createdSessionIdRef = useRef<number | null>(null)
  const [reasoningOpen, setReasoningOpen] = useReasoningOpen()
  const isPage = variant === 'page'
  const width = useChatStore((state) => state.width)
  const setChatWidth = useChatStore((state) => state.setChatWidth)
  const persistChatWidth = useChatStore((state) => state.persistChatWidth)
  const dragRef = useRef<{ startX: number; startWidth: number } | null>(null)

  const onResizeStart = (event: ReactPointerEvent<HTMLDivElement>) => {
    dragRef.current = { startX: event.clientX, startWidth: width }
    if (typeof event.currentTarget.setPointerCapture === 'function') {
      event.currentTarget.setPointerCapture(event.pointerId)
    }
  }

  const onResizeMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current
    if (!drag) return
    setChatWidth(drag.startWidth + (drag.startX - event.clientX))
  }

  const onResizeEnd = () => {
    if (!dragRef.current) return
    dragRef.current = null
    persistChatWidth()
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
  const quizmeOn = activeChatSession?.quizme ?? false
  const toggleQuizme = useMutation({
    mutationFn: () => updateChatSessionQuizme(activeSession!, !quizmeOn),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['chat-sessions'] })
      void queryClient.invalidateQueries({ queryKey: ['chat-messages', activeSession] })
    },
  })
  const sending = stream.status === 'pending' || stream.status === 'streaming'

  const messages = useQuery({
    queryKey: ['chat-messages', activeSession],
    queryFn: () => listChatMessages(activeSession!),
    enabled: activeSession !== null,
    refetchInterval: sending ? 2000 : false,
  })

  const branchSelect = useMutation({
    mutationFn: (messageId: number) => selectChatVariant(messageId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ['chat-messages', activeSession],
      })
    },
  })

  const submit = async () => {
    const content = draft.trim()
    if (content.length === 0 || sending) {
      return
    }
    const attachmentPayload = attachments.map(({ kind, id }) => ({ kind, id }))
    let targetSession = activeSession
    if (targetSession === null) {
      const created = await createChatSession(
        courseId,
        undefined,
        content.slice(0, 60),
      )
      targetSession = created.id
      adoptingRef.current = created.id
      chat.adoptSession(created)
      onSessionCreated(created)
      await queryClient.invalidateQueries({ queryKey: ['chat-sessions'] })
    }
    sentCountRef.current = messages.data?.length ?? 0
    const accepted = await chat.send(content, attachmentPayload)
    if (accepted) {
      setDraft('')
      setAttachments([])
    }
    await queryClient.invalidateQueries({
      queryKey: ['chat-messages', targetSession],
    })
  }

  const handleEditResend = (messageId: number, content: string) => {
    if (sending || content.length === 0) {
      return
    }
    sentCountRef.current = messages.data?.length ?? 0
    chat.beginEdit(messageId)
    void chat.send(content)
  }

  const handleRegenerate = (userMessageId: number) => {
    if (sending) {
      return
    }
    sentCountRef.current = messages.data?.length ?? 0
    chat.beginRegenerate(userMessageId)
    const parent = rawMessages.get(String(userMessageId))
    void chat.send(parent?.markdown ?? ' ')
  }

  useEffect(() => {
    const list = messages.data
    if (
      sending &&
      list !== undefined &&
      list.length > sentCountRef.current &&
      list[list.length - 1].role === 'assistant'
    ) {
      stream.reset()
    }
  }, [messages.data, sending, stream])


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
    transcribe: transcribeViaGateway,
    classifyError: classifyDictationError,
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
    if (sending) {
      return
    }
    setDraft('')
    setAttachments([])
  }, [activeSession, sending])

  const pendingSend = useChatStore((state) => state.pendingSend)
  const clearPendingSend = useChatStore((state) => state.clearPendingSend)
  const askSessionId = useChatStore((state) =>
    state.pendingSend !== null ? (state.session?.id ?? null) : null,
  )
  const chatRef = useRef(chat)
  chatRef.current = chat
  const pendingSendInFlightRef = useRef(false)

  useEffect(() => {
    if (pendingSend === null) {
      return
    }
    if (pendingSend.mode === 'prefill') {
      setDraft(pendingSend.content)
      setAttachments(
        (pendingSend.attachments ?? []).map(({ kind, id, title }) => ({
          kind,
          id,
          title: title ?? '',
        })),
      )
      const element = textareaRef.current
      if (element !== null) {
        const caret = pendingSend.content.length
        requestAnimationFrame(() => {
          element.focus()
          element.setSelectionRange(caret, caret)
        })
      }
      clearPendingSend()
      return
    }
    if (activeSession === null || sending || pendingSendInFlightRef.current) {
      return
    }
    if (askSessionId !== null && activeSession !== askSessionId) {
      return
    }
    chatRef.current.adoptSession({ id: activeSession })
    pendingSendInFlightRef.current = true
    void (async () => {
      const accepted = await chatRef.current.send(
        pendingSend.content,
        (pendingSend.attachments ?? []).map(({ kind, id }) => ({ kind, id })),
      )
      pendingSendInFlightRef.current = false
      if (accepted) {
        clearPendingSend()
      }
      await queryClient.invalidateQueries({
        queryKey: ['chat-messages', activeSession],
      })
      await queryClient.invalidateQueries({ queryKey: ['chat-sessions'] })
    })()
  }, [pendingSend, activeSession, askSessionId, sending, clearPendingSend, queryClient])

  const suggestions = [t('chat.suggest1'), t('chat.suggest2'), t('chat.suggest3')]
  const livePhase =
    stream.nodes.length > 0
      ? (stream.nodes[stream.nodes.length - 1].id ?? 'thinking')
      : 'thinking'
  const rawMessages = useMemo(
    () => new Map((messages.data ?? []).map((message) => [String(message.id), message])),
    [messages.data],
  )
  const viewMessages = useMemo(
    () => (messages.data ?? []).map(toChatMessageView),
    [messages.data],
  )

  const headerActions = (
    <>
      {activeSession !== null ? <BranchTreeButton sessionId={activeSession} /> : null}
      <Button
        variant={quizmeOn ? 'default' : 'ghost'}
        size="sm"
        onClick={() => toggleQuizme.mutate()}
        disabled={activeSession === null || toggleQuizme.isPending}
        title={quizmeOn ? t('chat.quizmeOn') : t('chat.quizmeOff')}
        aria-pressed={quizmeOn}
      >
        <HelpCircle className="size-4" aria-hidden />
        <span className="hidden lg:inline">{t('chat.quizmeToggle')}</span>
      </Button>
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
    </>
  )

  const panelBanner = (
    <>
      {!isPage ? (
        <div className="border-border -mx-3 -my-1.5 border-b px-3 py-2">
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
    </>
  )

  return (
    <aside
      className={cn(
        'bg-surface border-border',
        isPage
          ? 'relative h-full w-full'
          : 'relative flex h-full shrink-0 flex-col border-l animate-in fade-in slide-in-from-right-8 duration-200 transition-[width] ease-out motion-reduce:animate-none motion-reduce:transition-none',
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
      <ChatPanelHost
        variant={variant}
        title={
          <span className="flex items-center gap-2 text-sm font-semibold">
            <MessageSquare className="size-4" aria-hidden />
            {t('chat.title')}
          </span>
        }
        actions={headerActions}
        banner={panelBanner}
        transcript={
        <ChatTranscript
          items={viewMessages}
          renderItem={(view) => {
            const message = rawMessages.get(view.id)
            if (message === undefined) {
              return null
            }
            return (
              <TranscriptMessage
                view={view}
                message={message}
                onOpenGenerate={setGenerateRequest}
                onEditResend={handleEditResend}
                onRegenerate={handleRegenerate}
                onSwitchVariant={(messageId) => branchSelect.mutate(messageId)}
                actionPending={sending}
              />
            )
          }}
          live={
            sending ? (
              <>
                {stream.reasoning !== null ? (
                  <ChatReasoning
                    text={stream.reasoning}
                    streaming
                    open={reasoningOpen}
                    onOpenChange={setReasoningOpen}
                    labels={{ title: t('chat.reasoning'), streaming: t('chat.thinking') }}
                  />
                ) : null}
                {stream.text !== null ? (
                  <div className="flex flex-col items-start">
                    <ChatMessage
                      role="assistant"
                      status="streaming"
                      content={
                        <>
                          <MarkdownSurface value={normalizeMathFences(stream.text)} streaming />
                          <span className="chat-caret text-xs" aria-hidden />
                        </>
                      }
                    />
                    {stream.startedAt !== null ? (
                      <ChatTurnStatus
                        variant="row"
                        label={`${t(`chat.phase.${livePhase}`)}…`}
                        startedAt={stream.startedAt}
                      />
                    ) : null}
                  </div>
                ) : null}
                {stream.toolCalls.length > 0 ? (
                  <div className="flex w-full max-w-[92%] animate-in fade-in flex-col gap-1 duration-200 motion-reduce:animate-none">
                    {stream.toolCalls.map((call) => (
                      <ChatToolCard
                        key={call.id}
                        {...toolCardProps(
                          {
                            name: call.name,
                            argument: call.args ?? '',
                            result: call.result ?? null,
                            title: call.title ?? null,
                            phase: null,
                            status: call.status,
                            start_ms: null,
                            duration_ms: call.durationMs ?? null,
                          },
                          t,
                        )}
                      />
                    ))}
                  </div>
                ) : null}
                {stream.text === null && stream.reasoning === null ? (
                  <ChatTurnStatus variant="card" label={t('chat.thinking')} />
                ) : null}
              </>
            ) : undefined
          }
          emptyState={
            <div className="flex animate-in fade-in flex-col items-center gap-3 pt-10 text-center duration-300 motion-reduce:animate-none">
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
          }
          labels={{
            log: t('chat.transcriptLog'),
            scrollToBottom: t('chat.scrollToBottom'),
            replied: t('chat.replied'),
          }}
        />
        }
        composer={
          <ChatComposer
          value={draft}
          onValueChange={setDraft}
          onSubmit={() => void submit()}
          sending={sending}
          onStop={() => void stream.stop()}
          maxRows={6}
          placeholder={t('chat.placeholder')}
          ariaLabel={t('chat.composerLabel')}
          labels={{ send: t('chat.send'), stop: t('chat.stop') }}
          textareaRef={textareaRef}
          toolbarStart={
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
          }
          toolbarEnd={
            <DictationButton
              status={dictation.status}
              onStart={() => void dictation.start()}
              label={t('dictation.start')}
            />
          }
          attachments={
            attachments.length > 0 ? (
              <div className="flex flex-wrap gap-1">
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
            ) : undefined
          }
          suggestions={
            dictation.status !== 'idle' || dictation.error !== null ? (
              <DictationStrip
                status={dictation.status}
                seconds={dictation.seconds}
                levelRef={dictation.levelRef}
                error={dictation.error}
                labels={{
                  stop: t('dictation.stop'),
                  cancel: t('dictation.cancel'),
                  recording: t('dictation.recording'),
                  transcribing: t('dictation.transcribing'),
                  unsupported: t('dictation.unsupported'),
                  denied: t('dictation.denied'),
                  unassigned: t('dictation.unassigned'),
                  failed: t('dictation.failedHint', { detail: '{detail}' }),
                }}
                onStop={() => void dictation.stop()}
                onCancel={dictation.cancel}
                onDismissError={dictation.dismissError}
              />
            ) : undefined
          }
          />
        }
        footer={
          stream.status === 'error' && stream.error !== null ? (
            <div
              role="alert"
              className="text-danger border-danger/40 flex w-full items-start gap-2 rounded-lg border border-dashed px-3 py-2 text-xs"
            >
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
              <span className="min-w-0 flex-1 break-words text-left">
                {stream.error.code === 'timeout'
                  ? t('chat.timeout')
                  : `${t('chat.turnFailed')} (${stream.error.message})`}
              </span>
              <button
                type="button"
                aria-label={t('chat.dismissError')}
                title={t('chat.dismissError')}
                onClick={() => stream.reset()}
                className="text-danger rounded-full p-0.5 transition-colors hover:opacity-70"
              >
                <X className="size-3.5" aria-hidden />
              </button>
            </div>
          ) : undefined
        }
      />

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
            materialIds: generateRequest.params.materialIds,
            noteIds: generateRequest.params.noteIds,
            instructions: generateRequest.params.instructions ?? undefined,
            questionTypes: generateRequest.params.questionTypes,
            shuffle: generateRequest.params.shuffle,
            flashcards: generateRequest.params.flashcards,
          }}
          onClose={() => setGenerateRequest(null)}
          onSuccess={() => setGenerateRequest(null)}
        />
      ) : null}
    </aside>
  )
}
