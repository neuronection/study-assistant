import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { RegionCrop } from './RegionCrop'

const PNG_DATA_URL =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='

class MockImage {
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  naturalWidth = 400
  naturalHeight = 300
  private source = ''
  set src(value: string) {
    this.source = value
    queueMicrotask(() => this.onload?.())
  }
  get src() {
    return this.source
  }
}

const originalGetContext = HTMLCanvasElement.prototype.getContext
const originalToDataURL = HTMLCanvasElement.prototype.toDataURL
const originalGetBoundingClientRect =
  HTMLElement.prototype.getBoundingClientRect
const originalSetPointerCapture = Element.prototype.setPointerCapture

let drawImage: ReturnType<typeof vi.fn>
let stopTrack: ReturnType<typeof vi.fn>

function installHappyPath() {
  drawImage = vi.fn()
  stopTrack = vi.fn()
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
    { drawImage } as unknown as CanvasRenderingContext2D
  )
  vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue(
    PNG_DATA_URL
  )
  HTMLElement.prototype.getBoundingClientRect = () =>
    ({
      x: 0,
      y: 0,
      left: 0,
      top: 0,
      right: 200,
      bottom: 100,
      width: 200,
      height: 100,
      toJSON: () => ({}),
    }) as DOMRect
  Element.prototype.setPointerCapture = vi.fn()
  Object.defineProperty(HTMLMediaElement.prototype, 'srcObject', {
    configurable: true,
    set(value: MediaStream | null) {
      Object.defineProperty(this, '_srcObject', {
        configurable: true,
        value,
      })
      queueMicrotask(() =>
        this.onloadedmetadata?.(new Event('loadedmetadata'))
      )
    },
    get() {
      return (this as unknown as { _srcObject: MediaStream | null })._srcObject
    },
  })
  Object.defineProperty(HTMLMediaElement.prototype, 'play', {
    configurable: true,
    value: () => Promise.resolve(),
  })
  Object.defineProperty(HTMLVideoElement.prototype, 'videoWidth', {
    configurable: true,
    get: () => 40,
  })
  Object.defineProperty(HTMLVideoElement.prototype, 'videoHeight', {
    configurable: true,
    get: () => 30,
  })
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: {
      getDisplayMedia: async () => ({ getTracks: () => [{ stop: stopTrack }] }),
    },
  })
  vi.stubGlobal('Image', MockImage)
}

describe('RegionCrop', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    HTMLCanvasElement.prototype.getContext = originalGetContext
    HTMLCanvasElement.prototype.toDataURL = originalToDataURL
    HTMLElement.prototype.getBoundingClientRect =
      originalGetBoundingClientRect
    Element.prototype.setPointerCapture = originalSetPointerCapture
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  test('renders nothing while closed', () => {
    installHappyPath()
    render(
      <RegionCrop
        open={false}
        title="Snap a screen region"
        confirmLabel="Use screenshot"
        onCapture={() => undefined}
      />
    )
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  test('shows an honest alert when screen capture is unsupported', async () => {
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {},
    })
    render(
      <RegionCrop
        open
        title="Snap a screen region"
        confirmLabel="Use screenshot"
        onCapture={() => undefined}
      />
    )
    await screen.findByRole('alert')
    expect(screen.getByRole('alert').textContent).toContain(
      'Screen capture is unavailable here'
    )
  })

  test('a dragged region crops the frame and reports the rect', async () => {
    installHappyPath()
    const onCapture = vi.fn().mockResolvedValue(undefined)
    render(
      <RegionCrop
        open
        title="Snap a screen region"
        confirmLabel="Use screenshot"
        onCapture={onCapture}
      />
    )
    await screen.findByText('Drag on the image to select an area')
    const frame = document.querySelector('img')!
    fireEvent.pointerDown(frame, { clientX: 40, clientY: 20 })
    fireEvent.pointerMove(frame, { clientX: 200, clientY: 160 })
    fireEvent.pointerUp(frame)
    fireEvent.click(screen.getByRole('button', { name: 'Use screenshot' }))
    await waitFor(() => expect(onCapture).toHaveBeenCalledTimes(1))
    const [file, rect] = onCapture.mock.calls[0]
    expect(file.name).toBe('screenshot.png')
    expect(file.type).toBe('image/png')
    expect(rect).toEqual({ x: 20, y: 20, width: 80, height: 140 })
    expect(drawImage).toHaveBeenCalledWith(
      expect.anything(),
      80,
      60,
      320,
      420,
      0,
      0,
      320,
      420
    )
    expect(stopTrack).toHaveBeenCalled()
  })

  test('confirming without a drag hands over the full frame and a null rect', async () => {
    installHappyPath()
    const onCapture = vi.fn().mockResolvedValue(undefined)
    render(
      <RegionCrop
        open
        title="Snap a screen region"
        confirmLabel="Use screenshot"
        onCapture={onCapture}
      />
    )
    await screen.findByText('Drag on the image to select an area')
    fireEvent.click(screen.getByRole('button', { name: 'Use screenshot' }))
    await waitFor(() => expect(onCapture).toHaveBeenCalledTimes(1))
    const [file, rect] = onCapture.mock.calls[0]
    expect(rect).toBeNull()
    expect(file.size).toBeGreaterThan(0)
    expect(drawImage).toHaveBeenCalledTimes(1)
    expect(drawImage).toHaveBeenCalledWith(expect.anything(), 0, 0)
  })

  test('an in-flight onCapture disables the confirm and recapture buttons', async () => {
    installHappyPath()
    let release: (() => void) | undefined
    const onCapture = vi.fn().mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          release = resolve
        })
    )
    render(
      <RegionCrop
        open
        title="Snap a screen region"
        confirmLabel="Use screenshot"
        onCapture={onCapture}
      />
    )
    await screen.findByText('Drag on the image to select an area')
    fireEvent.click(screen.getByRole('button', { name: 'Use screenshot' }))
    await waitFor(() =>
      expect(
        (screen.getByRole('button', { name: 'Use screenshot' }) as HTMLButtonElement)
          .disabled
      ).toBe(true)
    )
    expect(
      (screen.getByRole('button', { name: 'Recapture' }) as HTMLButtonElement)
        .disabled
    ).toBe(true)
    release?.()
    await waitFor(() =>
      expect(
        (screen.getByRole('button', { name: 'Use screenshot' }) as HTMLButtonElement)
          .disabled
      ).toBe(false)
    )
  })
})
