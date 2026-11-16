import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { StudioPage } from './StudioPage'
import { useWorkspaceStore } from '@/lib/workspace-store'

const listStudioArtifacts = vi.fn()
const listMaterials = vi.fn()
const createStudioArtifact = vi.fn()
const deleteStudioArtifact = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listStudioArtifacts: (courseId?: string) => listStudioArtifacts(courseId),
    listMaterials: (_folderId?: string, courseId?: string) => listMaterials(courseId),
    createStudioArtifact: (body: unknown) => createStudioArtifact(body),
    deleteStudioArtifact: (id: string) => deleteStudioArtifact(id),
  }
})

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children, ...props }: { children: React.ReactNode }) => (
    <a {...props}>{children}</a>
  ),
  useNavigate: () => vi.fn(),
}))

vi.mock('@/lib/ui-overlays', () => ({ useCloseFloatings: () => {} }))

const ARTIFACT = {
  id: 'artifact-1',
  course_id: 'c1',
  kind: 'slide_deck',
  title: 'Cell deck',
  source_material_id: 'source-1',
  material_id: 'material-1',
  created_at: '2026-11-11T10:00:00Z',
  spec: {
    kind: 'slide_deck',
    title: 'Cell deck',
    slides: [
      { layout: 'title', title: 'Cell deck', bullets: [] },
      { layout: 'bullets', title: 'Membranes', bullets: ['A lipid bilayer controls entry.'] },
    ],
  },
}

const SOURCE = {
  id: 'source-1',
  title: 'Chapter 1',
  kind: 'md',
  has_extraction: true,
  course_id: 'c1',
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <StudioPage />
    </QueryClientProvider>,
  )
}

describe('StudioPage', () => {
  beforeEach(() => {
    useWorkspaceStore.setState({ courseId: 'c1', hydrated: true })
    listStudioArtifacts.mockReset().mockResolvedValue([ARTIFACT])
    listMaterials.mockReset().mockResolvedValue([SOURCE])
    createStudioArtifact.mockReset().mockResolvedValue(ARTIFACT)
    deleteStudioArtifact.mockReset().mockResolvedValue(undefined)
  })

  test('lists artifacts and prints a deck', async () => {
    const print = vi.spyOn(window, 'print').mockImplementation(() => {})
    renderPage()
    expect(await screen.findByText('Cell deck')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Open' }))
    expect(screen.getByText('Membranes')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Print / PDF' }))
    expect(print).toHaveBeenCalled()
    print.mockRestore()
  })

  test('creates an artifact from a source material', async () => {
    renderPage()
    await screen.findByText('Cell deck')
    fireEvent.click(screen.getByRole('button', { name: 'New artifact' }))
    expect(screen.getByRole('dialog', { name: 'Create from material' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Artifact title'), {
      target: { value: 'My deck' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    await waitFor(() => expect(createStudioArtifact).toHaveBeenCalled())
    expect(createStudioArtifact).toHaveBeenCalledWith({
      material_id: 'source-1',
      kind: 'slide_deck',
      title: 'My deck',
    })
  })

  test('asks for a course when none is selected', async () => {
    useWorkspaceStore.setState({ courseId: null, hydrated: true })
    renderPage()
    expect(await screen.findByText('Choose a course first.')).toBeInTheDocument()
  })
})
