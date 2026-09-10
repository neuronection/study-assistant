import { describe, expect, test } from 'vitest'

import { WsClient } from './ws'

class FakeWebSocket {
  readonly sent: string[] = []
  readyState = 0
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null

  send(data: string): void {
    this.sent.push(data)
  }

  close(): void {
    this.onclose?.()
  }

  simulateOpen(): void {
    this.readyState = 1
    this.onopen?.()
  }

  simulateClose(): void {
    this.readyState = 3
    this.onclose?.()
  }

  emit(topic: string, payload: unknown): void {
    this.onmessage?.({ data: JSON.stringify({ topic, payload }) })
  }
}

function makeClient(): { client: WsClient; socket: FakeWebSocket } {
  const socket = new FakeWebSocket()
  const client = new WsClient('ws://test/ws', () => socket as unknown as WebSocket)
  return { client, socket }
}

describe('WsClient', () => {
  test('subscribe before connect defers frames until open', () => {
    const { client, socket } = makeClient()
    const seen: unknown[] = []
    client.subscribe('jobs:1', (payload) => seen.push(payload))
    expect(socket.sent).toEqual([])
    socket.simulateOpen()
    expect(socket.sent).toEqual([JSON.stringify({ type: 'subscribe', topic: 'jobs:1' })])
  })

  test('duplicate handlers send a single subscribe frame', () => {
    const { client, socket } = makeClient()
    client.subscribe('jobs:1', () => undefined)
    client.subscribe('jobs:1', () => undefined)
    socket.simulateOpen()
    expect(socket.sent.filter((frame) => frame.includes('subscribe'))).toHaveLength(1)
  })

  test('events route to handlers by topic', () => {
    const { client, socket } = makeClient()
    const seen: unknown[] = []
    client.subscribe('jobs:1', (payload) => seen.push(payload))
    socket.simulateOpen()
    socket.emit('jobs:1', { stage: 'ocr' })
    socket.emit('jobs:2', { stage: 'ignored' })
    expect(seen).toEqual([{ stage: 'ocr' }])
  })

  test('control frames (subscribe acks) never reach handlers', () => {
    const { client, socket } = makeClient()
    const seen: unknown[] = []
    client.subscribe('chat:5', (payload) => seen.push(payload))
    socket.simulateOpen()
    socket.onmessage?.({
      data: JSON.stringify({ type: 'subscribed', topic: 'chat:5' }),
    })
    socket.onmessage?.({
      data: JSON.stringify({ type: 'unsubscribed', topic: 'chat:5' }),
    })
    socket.onmessage?.({ data: JSON.stringify({ type: 'pong' }) })
    socket.emit('chat:5', { type: 'stream_start' })
    expect(seen).toEqual([{ type: 'stream_start' }])
  })

  test('unsubscribing the last handler sends an unsubscribe frame', () => {
    const { client, socket } = makeClient()
    const unsubscribe = client.subscribe('jobs:1', () => undefined)
    socket.simulateOpen()
    unsubscribe()
    expect(socket.sent).toContain(JSON.stringify({ type: 'unsubscribe', topic: 'jobs:1' }))
  })

  test('send is skipped when the socket is not open (no crash on closing/closed)', () => {
    const { client, socket } = makeClient()
    client.subscribe('chat:27', () => undefined)
    socket.simulateOpen()
    socket.simulateClose()
    const before = socket.sent.length
    const unsubscribe = client.subscribe('chat:28', () => undefined)
    expect(() => unsubscribe()).not.toThrow()
    expect(socket.sent.length).toBe(before)
  })
})
