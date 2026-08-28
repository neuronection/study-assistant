import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { NodeSettingsMenu } from './NodeSettingsMenu'

const updateNode = vi.fn()
const updateCourse = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    updateNode: (...args: unknown[]) => updateNode(...(args as [number, object])),
    updateCourse: (...args: unknown[]) => updateCourse(...(args as [number, object])),
  }
})

const NODE = {
  id: 5,
  title: 'Derivatives',
  summary: 'Rates of change' as string | null,
  ai_hint: null as string | null,
  is_root: false,
}

function renderMenu(node: typeof NODE, examDate?: string | null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <NodeSettingsMenu courseId="3" node={node} examDate={examDate} />
    </QueryClientProvider>
  )
}

function openPanel() {
  fireEvent.click(screen.getByRole('button', { name: /node settings/i }))
  return screen.getByRole('dialog', { name: /node settings/i })
}

describe('NodeSettingsMenu', () => {
  test('non-root edits batch title, description and hint into one node PATCH', async () => {
    updateNode.mockResolvedValue(undefined)
    renderMenu(NODE)
    const panel = openPanel()

    const title = screen.getByRole('textbox', { name: /title/i })
    const description = screen.getByRole('textbox', { name: /description/i })
    const hint = screen.getByRole('textbox', { name: /ai instructions/i })
    const save = screen.getByRole('button', { name: /save/i })
    expect(save).toBeDisabled()
    expect(panel).toBeInTheDocument()

    fireEvent.change(title, { target: { value: 'Derivatives II' } })
    fireEvent.change(description, { target: { value: 'Faster rates' } })
    fireEvent.change(hint, { target: { value: 'prefer numeric answers' } })
    expect(save).toBeEnabled()

    fireEvent.click(save)
    await waitFor(() =>
      expect(updateNode).toHaveBeenCalledWith(5, {
        title: 'Derivatives II',
        summary: 'Faster rates',
        ai_hint: 'prefer numeric answers',
      })
    )
    expect(updateCourse).not.toHaveBeenCalled()
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  test('root routes title and description through the course PATCH', async () => {
    updateCourse.mockResolvedValue(undefined)
    updateNode.mockResolvedValue(undefined)
    renderMenu({ ...NODE, id: 1, is_root: true, summary: null })
    openPanel()

    fireEvent.change(screen.getByRole('textbox', { name: /^title$/i }), {
      target: { value: 'Calculus II' },
    })
    fireEvent.change(screen.getByRole('textbox', { name: /description/i }), {
      target: { value: 'Whole course description' },
    })
    fireEvent.change(screen.getByRole('textbox', { name: /ai instructions/i }), {
      target: { value: 'be terse' },
    })
    fireEvent.click(screen.getByRole('button', { name: /save/i }))

    await waitFor(() =>
      expect(updateCourse).toHaveBeenCalledWith(3, {
        title: 'Calculus II',
        description: 'Whole course description',
      })
    )
    await waitFor(() => expect(updateNode).toHaveBeenCalledWith(1, { ai_hint: 'be terse' }))
  })

  test('unchanged fields are not sent and save stays disabled without edits', async () => {
    renderMenu(NODE)
    openPanel()

    const save = screen.getByRole('button', { name: /save/i })
    expect(save).toBeDisabled()

    fireEvent.change(screen.getByRole('textbox', { name: /description/i }), {
      target: { value: 'Only the description changed' },
    })
    fireEvent.click(save)
    await waitFor(() => expect(updateNode).toHaveBeenCalledWith(5, { summary: 'Only the description changed' }))
  })

  test('failed save keeps the panel open with the typed text and an error', async () => {
    updateNode.mockRejectedValue(new Error('422: rejected'))
    renderMenu(NODE)
    openPanel()

    fireEvent.change(screen.getByRole('textbox', { name: /ai instructions/i }), {
      target: { value: 'my instructions' },
    })
    fireEvent.click(screen.getByRole('button', { name: /save/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/rejected/i)
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: /ai instructions/i })).toHaveValue(
      'my instructions'
    )
  })

  test('badge shows only when an AI instruction is set', () => {
    const { rerender } = renderMenu(NODE)
    fireEvent.click(screen.getByRole('button', { name: /node settings/i }))
    expect(screen.queryByRole('img', { name: /custom ai instructions/i })).not.toBeInTheDocument()

    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <NodeSettingsMenu courseId="3" node={{ ...NODE, ai_hint: 'be terse' }} />
      </QueryClientProvider>
    )
    expect(screen.getByRole('img', { name: /custom ai instructions/i })).toBeInTheDocument()
  })
})

describe('NodeSettingsMenu exam date', () => {
  test('root saves the exam date through the course PATCH and clears on empty', async () => {
    updateCourse.mockResolvedValue(undefined)
    const root = { ...NODE, id: 1, title: 'Calculus', is_root: true }
    renderMenu(root, '2026-09-01')
    openPanel()

    const exam = screen.getByLabelText(/exam date/i)
    expect(exam).toHaveValue('2026-09-01')

    fireEvent.change(exam, { target: { value: '2026-09-15' } })
    const save = screen.getByRole('button', { name: /save/i })
    expect(save).toBeEnabled()
    fireEvent.click(save)
    await waitFor(() =>
      expect(updateCourse).toHaveBeenCalledWith(3, { exam_date: '2026-09-15' })
    )

  })

  test('clearing the exam date sends null', async () => {
    updateCourse.mockResolvedValue(undefined)
    const root = { ...NODE, id: 1, title: 'Calculus', is_root: true }
    renderMenu(root, '2026-09-01')
    openPanel()

    fireEvent.change(screen.getByLabelText(/exam date/i), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: /save/i }))
    await waitFor(() =>
      expect(updateCourse).toHaveBeenCalledWith(3, { exam_date: null })
    )
  })

  test('non-root nodes show no exam date field', () => {
    renderMenu(NODE)
    openPanel()
    expect(screen.queryByLabelText(/exam date/i)).not.toBeInTheDocument()
  })
})
