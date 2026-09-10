import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { GenesisDialog } from './GenesisDialog'

const draftGenesis = vi.fn()
const createGenesisCourse = vi.fn()
const getSearchProvider = vi.fn()
const navigate = vi.fn()

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigate,
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    draftGenesis: (...args: unknown[]) => draftGenesis(...(args as [])),
    createGenesisCourse: (...args: unknown[]) => createGenesisCourse(...(args as [])),
    getSearchProvider: () => getSearchProvider(),
  }
})

const DRAFT = {
  title: 'Linear Algebra for Economists',
  description: 'Foundations.',
  subject: 'Mathematics',
  level: 'university-intro',
  goals: ['Master matrices'],
  chapters: [
    {
      title: 'Vectors',
      summary: 'Vector basics.',
      sections: [
        { title: 'Vector spaces', objectives: ['Define a vector space'] },
      ],
    },
    {
      title: 'Matrices',
      summary: 'Matrix algebra.',
      sections: [{ title: 'Multiplication', objectives: ['Multiply matrices'] }],
    },
  ],
}

function renderDialog(onClose: () => void = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <GenesisDialog onClose={onClose} />
    </QueryClientProvider>
  )
}

describe('GenesisDialog', () => {
  test('web-grounding toggle appears only with a provider and passes ground', async () => {
    draftGenesis.mockResolvedValue(DRAFT)
    getSearchProvider.mockResolvedValue({
      assigned: true,
      base_url: 'https://api.tavily.com',
      flavor: 'tavily',
      key_set: true,
    })
    renderDialog()
    fireEvent.change(await screen.findByPlaceholderText(/Linear algebra/), {
      target: { value: 'Topic' },
    })
    const toggle = screen.getByLabelText(/web sources/i)
    fireEvent.click(toggle)
    fireEvent.click(screen.getByRole('button', { name: 'Draft outline' }))
    await waitFor(() => expect(draftGenesis).toHaveBeenCalledWith({
      topic: 'Topic',
      level: null,
      ground: true,
    }))

    getSearchProvider.mockResolvedValue({
      assigned: false,
      base_url: null,
      flavor: null,
      key_set: false,
    })
    draftGenesis.mockClear()
    renderDialog()
    fireEvent.change(await screen.findByPlaceholderText(/Linear algebra/), {
      target: { value: 'Topic' },
    })
    expect(screen.queryByLabelText(/web sources/i)).not.toBeInTheDocument()
  })

  test('drafts, reviews, edits a chapter and commits with options', async () => {
    draftGenesis.mockResolvedValue(DRAFT)
    getSearchProvider.mockResolvedValue({
      assigned: false,
      base_url: null,
      flavor: null,
      key_set: false,
    })
    createGenesisCourse.mockResolvedValue({
      course: { id: 42, title: 'Linear Algebra for Economists' },
      job_id: 7,
      estimated_tasks: 2,
      task_cap: 60,
    })
    renderDialog()

    fireEvent.change(screen.getByPlaceholderText(/Linear algebra/), {
      target: { value: 'Linear algebra for economists' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Draft outline' }))
    await waitFor(() =>
      expect(draftGenesis).toHaveBeenCalledWith({
        topic: 'Linear algebra for economists',
        level: null,
        ground: false,
      })
    )

    const chapterInput = await screen.findByLabelText('Chapter 1 title')
    expect(chapterInput).toHaveValue('Vectors')
    expect(screen.getByLabelText('Chapter 2 title')).toHaveValue('Matrices')

    fireEvent.change(screen.getByLabelText('Chapter 2 title'), {
      target: { value: 'Matrix algebra' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))

    fireEvent.click(await screen.findByLabelText(/short quiz per chapter/i))
    expect(screen.getByText(/≈4 generation tasks/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Create course' }))
    await waitFor(() =>
      expect(createGenesisCourse).toHaveBeenCalledWith({
        draft: {
          ...DRAFT,
          chapters: [
            DRAFT.chapters[0],
            { ...DRAFT.chapters[1], title: 'Matrix algebra' },
          ],
        },
        lessons: true,
        quizzes: true,
        flashcards: false,
        sources: [],
      })
    )
    await waitFor(() => expect(navigate).toHaveBeenCalled())
  })

  test('draft requires a topic and the create button needs at least one option', async () => {
    draftGenesis.mockResolvedValue(DRAFT)
    getSearchProvider.mockResolvedValue({
      assigned: false,
      base_url: null,
      flavor: null,
      key_set: false,
    })
    renderDialog()

    expect(screen.getByRole('button', { name: 'Draft outline' })).toBeDisabled()
    fireEvent.change(screen.getByPlaceholderText(/Linear algebra/), {
      target: { value: 'Topic' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Draft outline' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Next' }))

    await screen.findByLabelText(/lesson per chapter/i)
    expect(screen.getByRole('button', { name: 'Create course' })).toBeEnabled()
  })
})
