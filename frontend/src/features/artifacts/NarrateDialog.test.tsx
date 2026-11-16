import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { NarrateDialog } from './NarrateDialog'

const createNarration = vi.fn()
const getArtifact = vi.fn()
const retryArtifact = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    createNarration: (body: unknown) => createNarration(body),
    getArtifact: (id: string) => getArtifact(id),
    retryArtifact: (id: string) => retryArtifact(id),
  }
})

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children, ...props }: { children: React.ReactNode }) => (
    <a {...props}>{children}</a>
  ),
}))

vi.mock('@/lib/ui-overlays', () => ({ useCloseFloatings: () => {} }))

const PENDING = {
  id: 'artifact-1',
  course_id: 'c1',
  node_id: 'n1',
  kind: 'audio_brief',
  title: 'Narrate: Derivatives',
  status: 'pending',
  spec: { script: 'A short script', renderer: 'pending' },
  output_material_id: null,
  job_id: 'job-1',
  model: null,
  voice: null,
  created_at: '2026-11-11T10:00:00Z',
}

const READY = {
  ...PENDING,
  status: 'ready',
  spec: {
    script: 'A short script',
    renderer: 'browser',
    chapters: [{ title: 'Today', script: 'Today is a study day.' }],
  },
  output_material_id: 'material-1',
}

function renderDialog() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <NarrateDialog courseId="c1" nodeId="n1" onClose={() => {}} />
    </QueryClientProvider>,
  )
}

describe('NarrateDialog', () => {
  beforeEach(() => {
    createNarration.mockReset().mockResolvedValue(PENDING)
    getArtifact.mockReset().mockResolvedValue(READY)
    retryArtifact.mockReset()
    const speak = vi.fn()
    vi.stubGlobal('speechSynthesis', {
      speak,
      cancel: vi.fn(),
    })
    vi.stubGlobal('SpeechSynthesisUtterance', class {
      text: string
      onend: (() => void) | null = null
      onerror: (() => void) | null = null
      constructor(text: string) {
        this.text = text
      }
    })
  })

  test('creates a brief and exposes the rendered audio material', async () => {
    renderDialog()
    fireEvent.change(screen.getByLabelText('Brief title'), {
      target: { value: 'Derivatives brief' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create audio brief' }))

    await waitFor(() =>
      expect(createNarration).toHaveBeenCalledWith({
        course_id: 'c1',
        node_id: 'n1',
        title: 'Derivatives brief',
        length_minutes: 5,
        regenerate: true,
      }),
    )
    expect(await screen.findByText(/Ready/)).toBeInTheDocument()
    expect(screen.getByText('Open audio')).toBeInTheDocument()
    expect(getArtifact).toHaveBeenCalledWith('artifact-1')
  })

  test('plays a browser-rendered brief with the device voice', async () => {
    renderDialog()
    fireEvent.click(screen.getByRole('button', { name: 'Create audio brief' }))
    expect(await screen.findByText('Device voice')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Play device voice' }))
    expect(window.speechSynthesis.speak).toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Today' })).toBeInTheDocument()
  })
})
