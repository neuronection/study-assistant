import type { ChatStreamEvent, ChatStreamTransport } from '@/components/ui/chat-core'
import {
  editChatMessage,
  regenerateChatMessage,
  sendChatMessage,
  stopChatTurn,
  type ChatAttachmentInput,
} from '@/lib/api'

export interface StudyWsEvent {
  type: string
  delta?: string
  kind?: string
  phase?: string
  name?: string
  argument?: string
  result?: string | null
  title?: string | null
  status?: string | null
  start_ms?: number | null
  duration_ms?: number | null
  detail?: string
  message?: string
  trace?: unknown
}

export interface MapStudyEventOptions {
  phaseLabel: (phase: string) => string
  runId?: string
}

export function mapStudyEvent(
  event: StudyWsEvent,
  options: MapStudyEventOptions,
): ChatStreamEvent | null {
  const runId = options.runId
  switch (event.type) {
    case 'stream_start':
      return { event: 'flow_started', flow: 'chat', run_id: runId }
    case 'phase': {
      const phase = event.phase ?? 'thinking'
      return {
        event: 'node_started',
        node: phase,
        label: options.phaseLabel(phase),
        run_id: runId,
      }
    }
    case 'stream_delta': {
      if (!event.delta) {
        return null
      }
      if (event.kind === 'reasoning') {
        return { event: 'delta', kind: 'reasoning', text: event.delta, run_id: runId }
      }
      return { event: 'delta', kind: 'text', text: event.delta, run_id: runId }
    }
    case 'tool_call': {
      const name = event.name ?? ''
      const id = `${name}@${event.start_ms ?? 0}`
      const explicit = event.status
      const status =
        explicit === 'running' || explicit === 'failed'
          ? explicit
          : explicit === 'done'
            ? 'done'
            : event.result != null
              ? 'done'
              : 'running'
      return {
        event: 'tool_call',
        id,
        name,
        title: event.title ?? undefined,
        status,
        args: event.argument,
        result: event.result ?? undefined,
        durationMs: event.duration_ms ?? undefined,
        run_id: runId,
      }
    }
    case 'assistant_message':
      return { event: 'flow_finished', run_id: runId }
    case 'stream_interrupted':
      return { event: 'flow_finished', run_id: runId }
    case 'turn_error':
      return {
        event: 'flow_failed',
        code: 'turn_error',
        message: event.detail || event.message || 'turn_error',
        retryable: true,
        run_id: runId,
      }
    default:
      return null
  }
}

export interface StudyChatTransportDeps {
  getSessionId: () => number | null
  phaseLabel: (phase: string) => string
}

export interface StudyChatTransport extends ChatStreamTransport {
  push: (payload: unknown) => void
  setAttachments: (items: ChatAttachmentInput[]) => void
  /** Route the next `send` through the edit-branch endpoint. */
  beginEdit: (messageId: number) => void
  /** Route the next `send` through the regenerate endpoint. */
  beginRegenerate: (messageId: number) => void
}

type SendIntent =
  | { kind: 'send' }
  | { kind: 'edit'; messageId: number }
  | { kind: 'regenerate'; messageId: number }

/**
 * App-side WS adapter (family plan 11 §3 / ADR-0006): feeds the session
 * topic `chat:<id>` through `mapStudyEvent` into the library's family
 * vocabulary. A per-turn epoch arms on `send` and gates stragglers from a
 * previous turn: nothing but `stream_start` passes before the turn's own
 * start, and every mapped event carries `turn-<epoch>` as `run_id` so the
 * reducer also drops cross-turn leakage.
 */
export function createStudyChatTransport(
  deps: StudyChatTransportDeps,
): StudyChatTransport {
  let onEvent: ((event: ChatStreamEvent) => void) | null = null
  let epoch = 0
  let armed = false
  let attachments: ChatAttachmentInput[] = []
  let intent: SendIntent = { kind: 'send' }

  const runId = () => `turn-${epoch}`

  const deliver = (event: ChatStreamEvent | null) => {
    if (event !== null) {
      onEvent?.(event)
    }
  }

  return {
    subscribe: (handlers) => {
      onEvent = handlers.onEvent
      return () => {
        onEvent = null
      }
    },
    push: (payload) => {
      const event = payload as StudyWsEvent
      if (!event || typeof event.type !== 'string') {
        return
      }
      if (event.type === 'stream_start') {
        armed = false
        deliver(mapStudyEvent(event, { phaseLabel: deps.phaseLabel, runId: runId() }))
        return
      }
      if (armed) {
        return
      }
      deliver(mapStudyEvent(event, { phaseLabel: deps.phaseLabel, runId: runId() }))
    },
    setAttachments: (items) => {
      attachments = items
    },
    beginEdit: (messageId) => {
      intent = { kind: 'edit', messageId }
    },
    beginRegenerate: (messageId) => {
      intent = { kind: 'regenerate', messageId }
    },
    send: async ({ text }) => {
      const sessionId = deps.getSessionId()
      if (sessionId === null) {
        throw new Error('No active chat session')
      }
      epoch += 1
      armed = true
      const payload = attachments
      attachments = []
      const current = intent
      intent = { kind: 'send' }
      if (current.kind === 'edit') {
        await editChatMessage(current.messageId, text)
        return
      }
      if (current.kind === 'regenerate') {
        await regenerateChatMessage(current.messageId)
        return
      }
      await sendChatMessage(sessionId, text, payload)
    },
    stop: async () => {
      const sessionId = deps.getSessionId()
      if (sessionId === null) {
        return
      }
      await stopChatTurn(sessionId)
    },
  }
}
