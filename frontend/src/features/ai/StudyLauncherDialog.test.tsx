import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { StudyLauncherDialog } from './StudyLauncherDialog'

const generateDialog = vi.fn()
const noteComposeDialog = vi.fn()

vi.mock('./GenerateDialog', () => ({
  GenerateDialog: (props: Record<string, unknown>) => {
    generateDialog(props)
    return (
      <div
        data-testid="generate-dialog"
        data-task={props.task as string}
        data-compose-kind={
          props.initial && typeof props.initial === 'object'
            ? ((props.initial as Record<string, unknown>).composeKind as string) ?? ''
            : ''
        }
      />
    )
  },
}))

vi.mock('./NoteComposeDialog', () => ({
  NoteComposeDialog: (props: Record<string, unknown>) => {
    noteComposeDialog(props)
    return <div data-testid="note-compose-dialog" />
  },
}))

const navigate = vi.fn()
vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigate,
  useRouterState: ({ select }: { select: (state: unknown) => unknown }) =>
    select({ location: { href: '/', search: {} } }),
}))

function renderLauncher(onClose: () => void = () => undefined) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <StudyLauncherDialog
        courseId={3}
        nodeId={5}
        rootNodeId={1}
        onClose={onClose}
        onNoteCreated={() => undefined}
      />
    </QueryClientProvider>
  )
}

describe('StudyLauncherDialog', () => {
  test('lists every AI action', () => {
    renderLauncher()
    for (const label of [
      'Quiz',
      'Exercises',
      'Flashcards',
      'Study guide',
      'Summary sheet',
      'Practice set',
      'Error recap',
      'Mindmap',
      'Write a note',
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })

  test('closes via the X button and the backdrop', () => {
    const onClose = vi.fn()
    renderLauncher(onClose)

    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(onClose).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByText('Study this node'))
    fireEvent.click(screen.getByText('Quiz').closest('div.fixed')!)
    expect(onClose).toHaveBeenCalledTimes(2)
  })

  test('opens the quiz generator scoped to the node', () => {
    renderLauncher()
    fireEvent.click(screen.getByText('Quiz'))
    expect(screen.getByTestId('generate-dialog')).toHaveAttribute('data-task', 'quiz')
    expect(generateDialog).toHaveBeenCalledWith(
      expect.objectContaining({ courseId: 3, scopeNodeId: 5, rootNodeId: 1 })
    )
  })

  test('opens compose with the mindmap kind preselected', () => {
    renderLauncher()
    fireEvent.click(screen.getByText('Mindmap'))
    expect(screen.getByTestId('generate-dialog')).toHaveAttribute('data-task', 'compose')
    expect(screen.getByTestId('generate-dialog')).toHaveAttribute('data-compose-kind', 'mindmap')
  })

  test('opens the note composer', () => {
    renderLauncher()
    fireEvent.click(screen.getByText('Write a note'))
    expect(screen.getByTestId('note-compose-dialog')).toBeInTheDocument()
    expect(noteComposeDialog).toHaveBeenCalledWith(
      expect.objectContaining({ courseId: 3, nodeId: 5, rootNodeId: 1 })
    )
  })
})
