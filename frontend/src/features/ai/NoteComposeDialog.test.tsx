import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, beforeEach, expect, test, vi } from 'vitest'

import { NoteComposeDialog } from './NoteComposeDialog'

const composeNote = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    composeNote: (body: unknown) => composeNote(body),
  }
})

function renderDialog(props: { nodeId: number; rootNodeId: number; onSuccess?: (id: number) => void }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <NoteComposeDialog
        courseId={3}
        nodeId={props.nodeId}
        rootNodeId={props.rootNodeId}
        onClose={() => undefined}
        onSuccess={props.onSuccess ?? (() => undefined)}
      />
    </QueryClientProvider>
  )
}

describe('NoteComposeDialog', () => {
  beforeEach(() => {
    composeNote.mockReset().mockResolvedValue({
      id: 42,
      title: 'Limits note',
      course_id: 3,
      node_id: 5,
      body: [{ type: 'text', md: 'A limit is...' }],
      drawings: [],
    })
  })

  test('at a node it composes with subtree scope by default', async () => {
    const onSuccess = vi.fn()
    renderDialog({ nodeId: 5, rootNodeId: 1, onSuccess })
    expect(await screen.findByLabelText('Scope')).toBeInTheDocument()
    fireEvent.change(screen.getByPlaceholderText('Title (optional)'), {
      target: { value: 'Limits note' },
    })
    fireEvent.change(screen.getByLabelText(/focus on/i), {
      target: { value: 'epsilon-delta definition' },
    })
    fireEvent.click(screen.getByRole('button', { name: /create note/i }))
    await waitFor(() => expect(composeNote).toHaveBeenCalled())
    expect(composeNote).toHaveBeenCalledWith(
      expect.objectContaining({
        course_id: 3,
        node_id: 5,
        scope: 'subtree',
        title: 'Limits note',
        instructions: 'epsilon-delta definition',
      })
    )
    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith(42))
  })

  test('at the root there is no scope picker and course scope is sent', async () => {
    renderDialog({ nodeId: 1, rootNodeId: 1 })
    expect(screen.queryByLabelText('Scope')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /create note/i }))
    await waitFor(() => expect(composeNote).toHaveBeenCalled())
    expect(composeNote).toHaveBeenCalledWith(
      expect.objectContaining({ node_id: 1, scope: 'course' })
    )
  })

  test('switching scope to this node only is forwarded', async () => {
    renderDialog({ nodeId: 5, rootNodeId: 1 })
    fireEvent.change(await screen.findByLabelText('Scope'), { target: { value: 'node' } })
    fireEvent.click(screen.getByRole('button', { name: /create note/i }))
    await waitFor(() => expect(composeNote).toHaveBeenCalled())
    expect(composeNote).toHaveBeenCalledWith(
      expect.objectContaining({ node_id: 5, scope: 'node' })
    )
  })
})
