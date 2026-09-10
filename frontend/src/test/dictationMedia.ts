import { vi } from 'vitest'

export class FakeMediaRecorder {
  static instances: FakeMediaRecorder[] = []

  state: 'inactive' | 'recording' = 'inactive'
  mimeType = 'audio/webm;codecs=opus'
  ondataavailable: ((event: { data: Blob }) => void) | null = null
  onstop: (() => void) | null = null

  constructor(public stream: MediaStream) {
    FakeMediaRecorder.instances.push(this)
  }

  start(): void {
    this.state = 'recording'
  }

  stop(): void {
    if (this.state === 'inactive') {
      return
    }
    this.state = 'inactive'
    this.ondataavailable?.({ data: new Blob(['final-audio'], { type: this.mimeType }) })
    queueMicrotask(() => this.onstop?.())
  }

  static isTypeSupported(mimeType: string): boolean {
    return mimeType.startsWith('audio/webm') || mimeType === 'audio/mp4'
  }
}

export function installDictationMediaStub(options?: { getUserMedia?: () => Promise<MediaStream> }) {
  FakeMediaRecorder.instances = []
  const tracks = [{ stop: vi.fn() }]
  const stream = { getTracks: () => tracks } as unknown as MediaStream
  const getUserMedia =
    options?.getUserMedia ?? vi.fn().mockResolvedValue(stream)

  class FakeAnalyser {
    fftSize = 2048
    getByteTimeDomainData(buffer: Uint8Array): void {
      buffer.fill(128)
    }
  }

  class FakeAudioContext {
    createAnalyser(): FakeAnalyser {
      return new FakeAnalyser()
    }
    createMediaStreamSource(): { connect: () => void } {
      return { connect: () => undefined }
    }
    close(): Promise<void> {
      return Promise.resolve()
    }
  }

  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia },
  })
  vi.stubGlobal('MediaRecorder', FakeMediaRecorder)
  vi.stubGlobal('AudioContext', FakeAudioContext)

  return { getUserMedia, tracks, stream }
}

export function removeMediaSupport(): void {
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: undefined,
  })
  vi.stubGlobal('MediaRecorder', undefined)
}
