import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import {
  deleteExercise,
  deleteQuiz,
  drillPatterns,
  dueFlashcards,
  listExercises,
  listFlashcards,
  listQuizzes,
  moveQuiz,
  reviewFlashcard,
  similarExercise,
  primeDefaults,
  renderWorkspace,
  navigateMock,
} from './harness'

describe('PracticeTab', () => {
  test('practice tab deletes a quiz from the row menu', async () => {
    primeDefaults()
    listQuizzes.mockResolvedValue([
      { id: '50', title: 'Node quiz', type: 'quiz', course_id: '3', node_id: '5', question_count: 4 },
    ])
    deleteQuiz.mockResolvedValue(undefined)
    renderWorkspace('/courses/3/n/5?tab=practice')
    await screen.findByText('Node quiz')
    fireEvent.click(screen.getByRole('button', { name: 'Actions' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Delete' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(deleteQuiz).toHaveBeenCalledWith('50'))
  })

  test('practice tab lists scoped quizzes and exercises with node chips', async () => {
    primeDefaults()
    listQuizzes.mockResolvedValue([
      { id: '50', title: 'Node quiz', type: 'quiz', course_id: '3', node_id: '5', question_count: 4 },
    ])
    listExercises.mockResolvedValue([
      { id: '60', title: 'Node exercise', course_id: '3', node_id: '11', difficulty: 2, step_count: 3 },
    ])
    renderWorkspace('/courses/3/n/5?tab=practice')
    expect(await screen.findByText('Node quiz')).toBeInTheDocument()
    expect(screen.getByText('Node exercise')).toBeInTheDocument()
    expect(screen.getAllByText('Derivatives').length).toBeGreaterThan(1)
    expect(screen.getByText('Chain rule')).toBeInTheDocument()
    expect(screen.getByText('Level 2')).toBeInTheDocument()
    expect(screen.getByText('4 questions')).toBeInTheDocument()
  })

  test('practice tab has one New practice action opening the builder', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5?tab=practice')
    expect(await screen.findByRole('button', { name: /new practice/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /generate quiz/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /generate exercise/i })).not.toBeInTheDocument()
  })

  test('practice tab rows navigate to the quiz runner and exercise player', async () => {
    primeDefaults()
    listQuizzes.mockResolvedValue([
      { id: '50', title: 'Node quiz', type: 'quiz', course_id: '3', node_id: '5', question_count: 4 },
    ])
    listExercises.mockResolvedValue([
      { id: '60', title: 'Node exercise', course_id: '3', node_id: '11', difficulty: 2, step_count: 3 },
    ])
    const first = renderWorkspace('/courses/3/n/5?tab=practice')
    fireEvent.doubleClick(await screen.findByRole('button', { name: /node quiz/i }))
    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith(
        expect.objectContaining({
          to: '/quiz/$activityId',
          params: { activityId: '50' },
          search: { from: '/courses/3/n/5?tab=practice' },
        })
      )
    )
    first.unmount()
    renderWorkspace('/courses/3/n/5?tab=practice')
    fireEvent.doubleClick(await screen.findByRole('button', { name: /node exercise/i }))
    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith(
        expect.objectContaining({
          to: '/exercises/$exerciseId',
          params: { exerciseId: '60' },
          search: { from: '/courses/3/n/5?tab=practice' },
        })
      )
    )
  })

  test('practice tab import opens the quiz import dialog course-prebound', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5?tab=practice')
    fireEvent.click(await screen.findByRole('button', { name: /^import$/i }))
    expect(await screen.findByText('Import caq quiz')).toBeInTheDocument()
    expect(screen.queryByLabelText('Course')).not.toBeInTheDocument()
  })

  test('practice tab similar action generates an isomorphic variant', async () => {
    primeDefaults()
    listExercises.mockResolvedValue([
      { id: '60', title: 'Node exercise', course_id: '3', node_id: '11', difficulty: 2, step_count: 3 },
    ])
    renderWorkspace('/courses/3/n/5?tab=practice')
    await screen.findByText('Node exercise')
    const kebabs = screen.getAllByRole('button', { name: 'Actions' })
    fireEvent.click(kebabs[kebabs.length - 1])
    fireEvent.click(
      await screen.findByRole('menuitem', { name: /generate a similar exercise/i })
    )
    await waitFor(() => expect(similarExercise).toHaveBeenCalledWith('60'))
  })

  test('practice tab drills card uses the workspace course', async () => {
    primeDefaults()
    drillPatterns.mockResolvedValue([
      {
        pattern: 'sign_slip',
        name: 'Sign slip',
        description: 'dropping a minus sign',
        source: 'seeded',
        occurrences: 2,
      },
    ])
    renderWorkspace('/courses/3/n/5?tab=practice')
    expect(await screen.findByText('Sign slip')).toBeInTheDocument()
    expect(screen.getByText('2 mistakes')).toBeInTheDocument()
  })

  test('practice tab switches to a flashcards segment with its own actions', async () => {
    primeDefaults()
    listFlashcards.mockResolvedValue([
      {
        id: '7',
        kind: 'basic',
        front: [{ type: 'text', md: 'Power rule' }],
        back: [{ type: 'text', md: 'n times x to the n minus one' }],
        source: 'note',
        source_ref: null,
        node_id: '5',
        due_at: null,
        state: null,
      },
    ])
    renderWorkspace('/courses/3/n/5?tab=practice')
    const setsSegment = await screen.findByRole('tab', { name: /quizzes & exercises/i })
    expect(setsSegment).toHaveAttribute('aria-selected', 'true')
    fireEvent.click(screen.getByRole('tab', { name: /flashcards/i }))
    expect(setsSegment).toHaveAttribute('aria-selected', 'false')
    expect(await screen.findByText('Power rule')).toBeInTheDocument()
    expect(dueFlashcards).toHaveBeenCalledWith(20, '3', '5')
  })

  test('practice tab keeps quiz actions on the sets segment only', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5?tab=practice')
    await screen.findByRole('button', { name: /new practice/i })
    fireEvent.click(await screen.findByRole('tab', { name: /flashcards/i }))
    expect(screen.getByRole('button', { name: /import \.apkg/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /new practice/i })).not.toBeInTheDocument()
  })

  test('cards tab shows the review queue scoped to the node', async () => {
    primeDefaults()
    dueFlashcards.mockResolvedValue([
      {
        id: '7',
        kind: 'basic',
        front: [{ type: 'text', md: 'Power rule for x to the n?' }],
        back: [{ type: 'text', md: 'n times x to the n minus one' }],
        source: 'note',
        source_ref: null,
        node_id: '5',
        due_at: null,
        state: null,
      },
    ])
    renderWorkspace('/courses/3/n/5?tab=cards')
    expect(await screen.findByText(/Power rule for/)).toBeInTheDocument()
    expect(dueFlashcards).toHaveBeenCalledWith(20, '3', '5')

    fireEvent.click(screen.getByRole('button', { name: /show answer/i }))
    expect(await screen.findByText('n times x to the n minus one')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /good/i }))
    await waitFor(() => expect(reviewFlashcard).toHaveBeenCalledWith('7', 3))
  })

  test('practice tab moves selected quizzes and deletes selected exercises', async () => {
    primeDefaults()
    listQuizzes.mockResolvedValue([
      { id: '50', title: 'Node quiz', type: 'quiz', course_id: '3', node_id: '5', question_count: 4 },
    ])
    listExercises.mockResolvedValue([
      { id: '60', title: 'Drill', course_id: '3', node_id: '5', step_count: 2, difficulty: null },
    ])
    moveQuiz.mockResolvedValue(undefined)
    deleteExercise.mockResolvedValue({ deleted_item_id: '91' })
    renderWorkspace('/courses/3/n/5?tab=practice')
    await screen.findByText('Node quiz')

    fireEvent.mouseDown(screen.getByText('Node quiz'))
    fireEvent.click(screen.getAllByRole('button', { name: /Move to node/i })[0])
    fireEvent.click(await screen.findByRole('treeitem', { name: /Chain rule/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Move' }))
    await waitFor(() => expect(moveQuiz).toHaveBeenCalledWith('50', '11'))

    fireEvent.mouseDown(screen.getByText('Drill'))
    fireEvent.click(screen.getAllByRole('button', { name: 'Delete' })[0])
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(deleteExercise).toHaveBeenCalledWith('60'))
  })

})
