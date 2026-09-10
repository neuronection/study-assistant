import { afterEach, describe, expect, it, vi } from 'vitest'

async function loadBeacon() {
  vi.resetModules()
  return await import('./render-beacon')
}

function stubFramesAndFetch() {
  const fetchMock = vi.fn().mockResolvedValue(undefined)
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
    cb(0)
    return 0
  })
  return fetchMock
}

describe('signalShellRendered', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('posts once after two animation frames', async () => {
    const fetchMock = stubFramesAndFetch()
    const { signalShellRendered } = await loadBeacon()
    signalShellRendered()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/shell/rendered', { method: 'POST' })
  })

  it('signals only once per page load', async () => {
    const fetchMock = stubFramesAndFetch()
    const { signalShellRendered } = await loadBeacon()
    signalShellRendered()
    signalShellRendered()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('does not post before frames fire', async () => {
    const fetchMock = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('fetch', fetchMock)
    const frames: FrameRequestCallback[] = []
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      frames.push(cb)
      return frames.length
    })
    const { signalShellRendered } = await loadBeacon()
    signalShellRendered()
    expect(fetchMock).not.toHaveBeenCalled()
    frames[0](0)
    frames[1](0)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
