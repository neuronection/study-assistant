import type { ChatStreamEvent, ChatStreamTransport } from '@/components/ui/chat-core'
import {
  editChatMessage,
  regenerateChatMessage,
  sendChatMessage,
  stopChatTurn,
  type ChatAttachmentInput,
} from '@/lib/api'

/**
 * A family-vocabulary event as it arrives on the `chat:<id>` WS topic
 * (guidelines ai-features §5 payload table; plan 24 V2 — the backend emits
 * these natively, no legacy names on the wire).
 */
export interface StudyWsEvent {
  type: string
  flow?: string
  run_id?: string
  steps?: { id: string; label?: string }[]
  node?: string
  label?: string
  text?: string
  kind?: string
  id?: string
  name?: string
  title?: string | null
  status?: string | null
  args?: string
  result?: string | null
  duration_ms?: number | null
  reason?: 'user' | 'server'
  partial?: boolean
  /** Stable machine code (e.g. `ai_not_configured`) for failure events. */
  code?: string
  message?: string
  retryable?: boolean | null
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
    case 'flow_started':
      return { event: 'flow_started', flow: event.flow ?? 'chat', run_id: runId }
    case 'node_started': {
      const node = event.node ?? 'thinking'
      return {
        event: 'node_started',
        node,
        label: options.phaseLabel(node),
        run_id: runId,
      }
    }
    case 'delta': {
      if (!event.text) {
        return null
      }
      if (event.kind === 'reasoning') {
        return { event: 'delta', kind: 'reasoning', text: event.text, run_id: runId }
      }
      return { event: 'delta', kind: 'text', text: event.text, run_id: runId }
    }
    case 'tool_call': {
      const name = event.name ?? ''
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
        id: event.id ?? `${name}@0`,
        name,
        title: event.title ?? undefined,
        status,
        args: event.args,
        result: event.result ?? undefined,
        durationMs: event.duration_ms ?? undefined,
        run_id: runId,
      }
    }
    case 'flow_finished':
      return { event: 'flow_finished', run_id: runId }
    case 'flow_interrupted':
      return {
        event: 'flow_interrupted',
        reason: event.reason,
        partial: event.partial,
      }
    case 'flow_failed':
      return {
        event: 'flow_failed',
        code: event.code || 'turn_error',
        message: event.message || 'turn_error',
        retryable: event.retryable ?? true,
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
 * topic `chat:<id>` — family events straight from the backend — into the
 * library's client vocabulary. A per-turn epoch arms on `send` and gates
 * stragglers from a previous turn: nothing but `flow_started` passes
 * before the turn's own start, and every mapped event carries
 * `turn-<epoch>` as `run_id` so the reducer also drops cross-turn
 * leakage. `flow_interrupted` is the one broadcast event that keeps its
 * server shape (no run id — any mid-turn consumer must learn about the
 * stop).
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
      if (event.type === 'flow_started') {
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
