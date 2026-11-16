import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { SolvePage } from './SolvePage'

const solveHistory = vi.fn()
const solveProblem = vi.fn()
const solveVariants = vi.fn()
const checkSolveVariant = vi.fn()
const saveSolveNote = vi.fn()
const deleteSolve = vi.fn()
const recognizeSolve = vi.fn()
const navigate = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    solveHistory: () => solveHistory(),
    solveProblem: (body: unknown) => solveProblem(body),
    solveVariants: (id: string) => solveVariants(id),
    checkSolveVariant: (id: string, index: number, response: string) =>
      checkSolveVariant(id, index, response),
    saveSolveNote: (id: string) => saveSolveNote(id),
    deleteSolve: (id: string) => deleteSolve(id),
    recognizeSolve: (file: File) => recognizeSolve(file),
  }
})

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigate,
}))

const ENTRY = {
  id: 'entry-1',
  input_kind: 'pasted',
  input_text: 'x^2 - 5x + 6 = 0',
  intent: 'solve',
  verified: true,
  note_id: null,
  created_at: '2026-11-11T10:00:00Z',
  result: {
    input: 'x^2 - 5x + 6 = 0',
    normalized: 'x^2 - 5x + 6 = 0',
    intent: 'solve',
    title: 'Solve equation',
    answer_latex: 'x = 2, x = 3',
    answer_text: 'x = 2, x = 3',
    steps: [
      {
        op: 'factor',
        title: 'Factor the quadratic',
        before: 'x^{2} - 5 x + 6 = 0',
        after: '(x - 3)(x - 2) = 0',
        check: 'equivalence',
        verified: true,
      },
      {
        op: 'solve',
        title: 'Apply the zero-product rule',
        before: '(x - 3)(x - 2) = 0',
        after: 'x = 2, x = 3',
        check: 'substitution',
        verified: true,
      },
    ],
    assumptions: [],
    verified: true,
    message: null,
  },
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SolvePage />
    </QueryClientProvider>,
  )
}

describe('SolvePage', () => {
  beforeEach(() => {
    solveHistory.mockReset().mockResolvedValue([])
    solveProblem.mockReset().mockResolvedValue(ENTRY)
    solveVariants.mockReset().mockResolvedValue([
      { index: 0, prompt: 'Solve: $x^{2} - 9x + 20 = 0$', kind: 'equation' },
      { index: 1, prompt: 'Solve: $x^{2} - 11x + 30 = 0$', kind: 'equation' },
      { index: 2, prompt: 'Solve: $x^{2} - 13x + 42 = 0$', kind: 'equation' },
    ])
    checkSolveVariant.mockReset().mockResolvedValue({ correct: true, expected: 'x = 4, x = 5' })
    saveSolveNote.mockReset().mockResolvedValue({ note_id: 'note-1' })
    deleteSolve.mockReset().mockResolvedValue(undefined)
    recognizeSolve.mockReset()
    navigate.mockReset()
  })

  test('pastes a problem, solves it and shows verified steps', async () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Paste' }))
    fireEvent.change(screen.getByLabelText('Problem text'), {
      target: { value: 'x^2 - 5x + 6 = 0' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Solve' }))

    await waitFor(() => expect(solveProblem).toHaveBeenCalled())
    expect(solveProblem).toHaveBeenCalledWith({
      input_text: 'x^2 - 5x + 6 = 0',
      input_kind: 'pasted',
    })
    expect(await screen.findByText('Factor the quadratic')).toBeInTheDocument()
    expect(screen.getAllByText('Verified').length).toBeGreaterThan(0)
    expect(screen.getAllByText('(x - 3)(x - 2) = 0').length).toBeGreaterThan(0)
  })

  test('generates and checks three similar problems', async () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Paste' }))
    fireEvent.change(screen.getByLabelText('Problem text'), {
      target: { value: 'x^2 - 5x + 6 = 0' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Solve' }))
    await screen.findByText('Factor the quadratic')

    fireEvent.click(screen.getByRole('button', { name: 'Practise this' }))
    await waitFor(() => expect(solveVariants).toHaveBeenCalledWith('entry-1'))
    expect(await screen.findByText('Three similar problems')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Answer for variant 1'), {
      target: { value: '4, 5' },
    })
    fireEvent.click(screen.getAllByRole('button', { name: 'Check' })[0])
    await waitFor(() =>
      expect(checkSolveVariant).toHaveBeenCalledWith('entry-1', 0, '4, 5'),
    )
    expect(await screen.findByText('Correct')).toBeInTheDocument()
  })

  test('keeps a verified solve as a note and opens it', async () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Paste' }))
    fireEvent.change(screen.getByLabelText('Problem text'), {
      target: { value: 'x^2 - 5x + 6 = 0' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Solve' }))
    await screen.findByText('Factor the quadratic')

    fireEvent.click(screen.getByRole('button', { name: 'Keep as note' }))
    await waitFor(() => expect(saveSolveNote).toHaveBeenCalledWith('entry-1'))
    expect(await screen.findByText('Saved to the scratchpad.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Open note' }))
    expect(navigate).toHaveBeenCalledWith({
      to: '/note/$noteId',
      params: { noteId: 'note-1' },
    })
  })
})
