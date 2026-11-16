import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { MediaPlayer } from './MediaPlayer'
import { AudioPlayerProvider } from '@/lib/audio-player'

const getMaterialMedia = vi.fn()
const listMaterialAnchors = vi.fn()
const createMaterialAnchor = vi.fn()
const deleteAnchor = vi.fn()
const patchMediaSegment = vi.fn()
const createFlashcard = vi.fn()
const createNote = vi.fn()
const createPlanItem = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getMaterialMedia: (id: string) => getMaterialMedia(id),
    listMaterialAnchors: (id: string) => listMaterialAnchors(id),
    createMaterialAnchor: (id: string, body: unknown) => createMaterialAnchor(id, body),
    deleteAnchor: (id: string) => deleteAnchor(id),
    patchMediaSegment: (id: string, body: unknown) => patchMediaSegment(id, body),
    createFlashcard: (body: unknown) => createFlashcard(body),
    createNote: (body: unknown) => createNote(body),
    createPlanItem: (courseId: string, body: unknown) => createPlanItem(courseId, body),
  }
})

const MEDIA = {
  material_id: 'm1',
  title: 'Lecture recording',
  blob_sha: 'a'.repeat(64),
  mime: 'audio/mpeg',
  duration_ms: 12500,
  segments: [
    { id: 's1', material_id: 'm1', start_ms: 0, end_ms: 5000, text: 'First point.', speaker: null, confidence: null, order_idx: 0, source: 'import' },
    { id: 's2', material_id: 'm1', start_ms: 6000, end_ms: 12500, text: 'Dr Chen explains.', speaker: 'Dr Chen', confidence: null, order_idx: 1, source: 'import' },
  ],
}

function renderPlayer() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <AudioPlayerProvider scope="u:test:p:default">
        <MediaPlayer materialId="m1" />
      </AudioPlayerProvider>
    </QueryClientProvider>,
  )
}

describe('MediaPlayer', () => {
  beforeEach(() => {
    getMaterialMedia.mockReset().mockResolvedValue(MEDIA)
    listMaterialAnchors.mockReset().mockResolvedValue([])
    createMaterialAnchor.mockReset().mockResolvedValue({})
    deleteAnchor.mockReset().mockResolvedValue(undefined)
    patchMediaSegment.mockReset().mockResolvedValue({})
    createFlashcard.mockReset().mockResolvedValue({ id: 'card-1' })
    createNote.mockReset().mockResolvedValue({ id: 'note-1' })
    createPlanItem.mockReset().mockResolvedValue({ id: 'plan-1' })
    Object.defineProperty(HTMLMediaElement.prototype, 'play', {
      configurable: true,
      value: vi.fn().mockResolvedValue(undefined),
    })
  })

  test('renders the transcript and seeks to a segment', async () => {
    renderPlayer()
    expect(await screen.findByText('First point.')).toBeInTheDocument()
    expect(screen.getByText('Dr Chen explains.')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Dr Chen explains/ }))
    await waitFor(() => expect(HTMLMediaElement.prototype.play).toHaveBeenCalled())
  })

  test('edits a transcript segment', async () => {
    renderPlayer()
    await screen.findByText('First point.')
    fireEvent.click(screen.getByRole('button', { name: 'Edit segment at 0:00' }))
    fireEvent.change(screen.getByLabelText('Edit transcript segment'), {
      target: { value: 'Corrected point.' },
    })
    fireEvent.change(screen.getByLabelText('Edit speaker'), {
      target: { value: 'Dr Chen' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }))
    await waitFor(() =>
      expect(patchMediaSegment).toHaveBeenCalledWith('s1', {
        text: 'Corrected point.',
        speaker: 'Dr Chen',
      }),
    )
  })

  test('marks a moment at the current timestamp', async () => {
    renderPlayer()
    await screen.findByText('First point.')
    fireEvent.click(screen.getByRole('button', { name: 'Mark moment' }))
    fireEvent.change(screen.getByLabelText('Moment note'), {
      target: { value: 'Ask about this' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save moment' }))
    await waitFor(() => expect(createMaterialAnchor).toHaveBeenCalled())
    expect(createMaterialAnchor).toHaveBeenCalledWith(
      'm1',
      expect.objectContaining({
        anchor_kind: 'time_range',
        note_md: 'Ask about this',
        source: 'user',
      }),
    )
  })

  test('turns a moment into a card, note and plan item', async () => {
    listMaterialAnchors.mockResolvedValue([
      {
        id: 'moment-1',
        anchor_kind: 'time_range',
        payload: { start_ms: 1000, end_ms: 11000 },
        quote: 'A key quote.',
        note_md: 'Review this.',
        color: 'primary',
      },
    ])
    renderPlayer()
    await screen.findByText('Moments (1)')
    fireEvent.click(screen.getByRole('button', { name: 'Make card' }))
    await waitFor(() => expect(createFlashcard).toHaveBeenCalled())
    expect(createFlashcard).toHaveBeenCalledWith(
      expect.objectContaining({ front_md: 'A key quote.', back_md: 'Review this.' }),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Quote into note' }))
    await waitFor(() => expect(createNote).toHaveBeenCalled())
    fireEvent.click(screen.getByRole('button', { name: 'Add to plan' }))
    await waitFor(() => expect(createPlanItem).toHaveBeenCalled())

    fireEvent.click(screen.getByRole('checkbox', { name: /Select moment/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Make 1 cards' }))
    await waitFor(() => expect(createFlashcard).toHaveBeenCalledTimes(2))
  })

  test('filters transcript segments', async () => {
    renderPlayer()
    await screen.findByText('First point.')
    fireEvent.change(screen.getByLabelText('Search transcript'), {
      target: { value: 'chen' },
    })
    expect(screen.queryByText('First point.')).not.toBeInTheDocument()
    expect(screen.getByText('Dr Chen explains.')).toBeInTheDocument()
  })
})
