import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { LectureRecorderDialog } from './LectureRecorderDialog'
import { offlineJournal } from '@/lib/offline/journal'
import { clearLectureDraft, saveLectureDraft } from './lectureDraft'

const createLecture = vi.fn()
const getLecture = vi.fn()
const patchLecture = vi.fn()
const finalizeLecture = vi.fn()
const cancelLecture = vi.fn()
const uploadLectureChunk = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    createLecture: (body: unknown) => createLecture(body),
    getLecture: (id: string) => getLecture(id),
    patchLecture: (id: string, body: unknown) => patchLecture(id, body),
    finalizeLecture: (id: string) => finalizeLecture(id),
    cancelLecture: (id: string) => cancelLecture(id),
    uploadLectureChunk: (id: string, seq: number, data: ArrayBuffer, sha: string) =>
      uploadLectureChunk(id, seq, data, sha),
  }
})

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children }: { children: React.ReactNode }) => <a>{children}</a>,
}))

class FakeRecorder {
  static isTypeSupported = () => true
  ondataavailable: ((event: { data: Blob }) => void) | null = null
  onstop: (() => void) | null = null
  onerror: (() => void) | null = null
  start = vi.fn()
  pause = vi.fn()
  resume = vi.fn()
  stop = vi.fn()
}

describe('LectureRecorderDialog', () => {
  beforeEach(async () => {
    getLecture.mockReset().mockResolvedValue({
      id: 'lecture-1',
      course_id: 'c1',
      status: 'recording',
      mime: 'audio/webm',
    })
    for (const op of offlineJournal.getSnapshot().ops) {
      await offlineJournal.remove(op.id)
    }
    createLecture.mockReset().mockResolvedValue({
      id: 'lecture-1',
      course_id: 'c1',
      status: 'recording',
    })
    patchLecture.mockReset().mockResolvedValue({})
    finalizeLecture.mockReset().mockResolvedValue({ material_id: 'm1', status: 'ready' })
    cancelLecture.mockReset().mockResolvedValue(undefined)
    uploadLectureChunk.mockReset().mockResolvedValue({})
    vi.stubGlobal('MediaRecorder', FakeRecorder)
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [{ stop: vi.fn() }],
        }),
      },
    })
  })

  afterEach(() => {
    clearLectureDraft()
  })

  test('requires consent before starting and creates a session', async () => {
    render(
      <LectureRecorderDialog
        courseId="c1"
        nodeId="n1"
        onClose={() => {}}
        onCreated={() => {}}
      />,
    )
    const start = screen.getByRole('button', { name: 'Start recording' })
    expect(start).toBeDisabled()
    fireEvent.click(screen.getByLabelText(/consent/i))
    expect(start).not.toBeDisabled()
    fireEvent.click(start)
    await waitFor(() => expect(createLecture).toHaveBeenCalled())
    expect(createLecture).toHaveBeenCalledWith(
      expect.objectContaining({
        course_id: 'c1',
        node_id: 'n1',
        consent_confirmed: true,
      }),
    )
    expect(await screen.findByText(/Recording/)).toBeInTheDocument()
  })

  test('resumes persisted lecture parts and finalizes the session', async () => {
    saveLectureDraft({
      sessionId: 'lecture-1',
      courseId: 'c1',
      nodeId: 'n1',
      title: 'Recovered lecture',
      mime: 'audio/webm',
      retention: 'audio_and_text',
      nextSeq: 1,
      updatedAt: Date.now(),
    })
    await offlineJournal.enqueueLectureChunk(
      'lecture-1',
      0,
      new Blob([new Uint8Array([1, 2, 3])], { type: 'audio/webm' }),
      'abc',
      'audio/webm',
    )
    render(
      <LectureRecorderDialog
        courseId="c1"
        nodeId="n1"
        onClose={() => {}}
        onCreated={() => {}}
      />,
    )
    expect(await screen.findByText('Unfinished lecture recording')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Resume upload' }))
    await waitFor(() => expect(getLecture).toHaveBeenCalledWith('lecture-1'))
    await waitFor(() => expect(uploadLectureChunk).toHaveBeenCalled())
    await waitFor(() => expect(finalizeLecture).toHaveBeenCalledWith('lecture-1'))
    expect(await screen.findByText('Recording saved.')).toBeInTheDocument()
  })
})
