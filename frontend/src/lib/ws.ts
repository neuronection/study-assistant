export interface WsEvent {
  topic: string
  payload: unknown
}

const CONTROL_FRAME_TYPES = new Set(['subscribed', 'unsubscribed', 'pong', 'error'])

const OPEN_READY_STATE = 1

type EventHandler = (payload: unknown) => void

export class WsClient {
  private socket: WebSocket | null = null
  private readonly handlers = new Map<string, Set<EventHandler>>()
  private readonly subscribedTopics = new Set<string>()
  private readonly url: string
  private readonly socketFactory: (url: string) => WebSocket

  constructor(
    url: string,
    socketFactory: (url: string) => WebSocket = (address) => new WebSocket(address)
  ) {
    this.url = url
    this.socketFactory = socketFactory
  }

  static browser(): WsClient {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return new WsClient(`${protocol}//${window.location.host}/ws`)
  }

  attach(socket: WebSocket): void {
    this.socket = socket
    socket.onmessage = (message: MessageEvent<string>) => {
      const event = JSON.parse(message.data) as WsEvent & { type?: string }
      if (
        event &&
        typeof event.topic === 'string' &&
        !(event.type !== undefined && CONTROL_FRAME_TYPES.has(event.type))
      ) {
        this.handleEvent(event)
      }
    }
    socket.onopen = () => {
      for (const topic of this.subscribedTopics) {
        this.send({ type: 'subscribe', topic })
      }
    }
    socket.onclose = () => {
      if (this.socket === socket) {
        this.socket = null
      }
    }
  }

  connect(): void {
    if (this.socket) {
      return
    }
    this.attach(this.socketFactory(this.url))
  }

  private send(frame: { type: string; topic: string }): void {
    if (this.socket && this.socket.readyState === OPEN_READY_STATE) {
      this.socket.send(JSON.stringify(frame))
    }
  }

  subscribe(topic: string, handler: EventHandler): () => void {
    if (!this.handlers.has(topic)) {
      this.handlers.set(topic, new Set())
    }
    this.handlers.get(topic)!.add(handler)
    if (!this.subscribedTopics.has(topic)) {
      this.subscribedTopics.add(topic)
      this.send({ type: 'subscribe', topic })
    }
    if (!this.socket) {
      this.connect()
    }
    return () => this.unsubscribe(topic, handler)
  }

  unsubscribe(topic: string, handler: EventHandler): void {
    const topicHandlers = this.handlers.get(topic)
    if (!topicHandlers?.delete(handler)) {
      return
    }
    if (topicHandlers.size === 0) {
      this.handlers.delete(topic)
      this.subscribedTopics.delete(topic)
      this.send({ type: 'unsubscribe', topic })
    }
  }

  handleEvent(event: WsEvent): void {
    for (const handler of this.handlers.get(event.topic) ?? []) {
      handler(event.payload)
    }
  }

  close(): void {
    this.socket?.close()
    this.socket = null
  }
}
