import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { ApiError, transcribeAudio } from '@/lib/api'
import {
  FakeMediaRecorder,
  installDictationMediaStub,
  removeMediaSupport,
} from '@/test/dictationMedia'

import { useDictation } from './useDictation'

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    transcribeAudio: vi.fn(),
  }
})

const transcribeMock = vi.mocked(transcribeAudio)

afterEach(() => {
  vi.unstubAllGlobals()
  transcribeMock.mockReset()
})

describe('useDictation', () => {
  test('records, transcribes and delivers the result text', async () => {
    installDictationMediaStub()
    transcribeMock.mockResolvedValue({ text: 'hello world', model: 'whisper-1' })
    const onResult = vi.fn()
    const { result } = renderHook(() => useDictation({ onResult }))

    await act(async () => {
      await result.current.start()
    })
    expect(result.current.status).toBe('recording')
    expect(FakeMediaRecorder.instances).toHaveLength(1)
    expect(FakeMediaRecorder.instances[0].state).toBe('recording')

    await act(async () => {
      await result.current.stop()
    })
    expect(result.current.status).toBe('idle')
    expect(result.current.error).toBeNull()
    expect(onResult).toHaveBeenCalledWith('hello world')
    expect(transcribeMock).toHaveBeenCalledTimes(1)
    const blob = transcribeMock.mock.calls[0][0] as Blob
    expect(blob).toBeInstanceOf(Blob)
    expect(blob.type).toBe('audio/webm;codecs=opus')
  })

  test('cancel stops the tracks and never calls the API', async () => {
    const stub = installDictationMediaStub()
    const onResult = vi.fn()
    const { result } = renderHook(() => useDictation({ onResult }))

    await act(async () => {
      await result.current.start()
    })
    act(() => {
      result.current.cancel()
    })
    expect(result.current.status).toBe('idle')
    expect(stub.tracks[0].stop).toHaveBeenCalled()
    expect(transcribeMock).not.toHaveBeenCalled()
    expect(onResult).not.toHaveBeenCalled()
  })

  test('reports unsupported when MediaRecorder is unavailable', async () => {
    removeMediaSupport()
    const { result } = renderHook(() => useDictation({ onResult: vi.fn() }))

    await act(async () => {
      await result.current.start()
    })
    expect(result.current.status).toBe('idle')
    expect(result.current.error?.kind).toBe('unsupported')
  })

  test('reports denied when the microphone is rejected', async () => {
    installDictationMediaStub({
      getUserMedia: () =>
        Promise.reject(new DOMException('denied', 'NotAllowedError')),
    })
    const { result } = renderHook(() => useDictation({ onResult: vi.fn() }))

    await act(async () => {
      await result.current.start()
    })
    expect(result.current.error?.kind).toBe('denied')
  })

  test('maps a 409 from the API to the unassigned error', async () => {
    installDictationMediaStub()
    transcribeMock.mockRejectedValue(
      new ApiError('task unassigned', 409),
    )
    const { result } = renderHook(() => useDictation({ onResult: vi.fn() }))

    await act(async () => {
      await result.current.start()
    })
    await act(async () => {
      await result.current.stop()
    })
    await waitFor(() => {
      expect(result.current.error?.kind).toBe('unassigned')
    })
    expect(result.current.status).toBe('idle')
  })

  test('maps other API failures to the failed error with detail', async () => {
    installDictationMediaStub()
    transcribeMock.mockRejectedValue(new ApiError('provider exploded', 502))
    const { result } = renderHook(() => useDictation({ onResult: vi.fn() }))

    await act(async () => {
      await result.current.start()
    })
    await act(async () => {
      await result.current.stop()
    })
    await waitFor(() => {
      expect(result.current.error?.kind).toBe('failed')
    })
    expect(result.current.error?.detail).toContain('provider exploded')
  })
})
