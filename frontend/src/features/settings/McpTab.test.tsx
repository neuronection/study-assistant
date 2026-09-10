import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { McpTab } from './McpTab'

const listMcpInfo = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listMcpInfo: () => listMcpInfo(),
  }
})

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <McpTab />
    </QueryClientProvider>,
  )
}

describe('McpTab', () => {
  test('renders the launch command and the read-only tool list', async () => {
    listMcpInfo.mockResolvedValue({
      command: 'python -m studyassistant mcp',
      instructions: 'Read-only access.',
      tools: [
        { name: 'list_courses', description: 'List the learner’s courses.', arguments: [] },
      ],
    })
    renderTab()
    expect(await screen.findByText('python -m studyassistant mcp')).toBeInTheDocument()
    expect(screen.getByText('list_courses')).toBeInTheDocument()
    expect(screen.getByText('List the learner’s courses.')).toBeInTheDocument()
  })

  test('copies the command to the clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    listMcpInfo.mockResolvedValue({
      command: 'python -m studyassistant mcp',
      instructions: 'Read-only access.',
      tools: [],
    })
    renderTab()
    await screen.findByText('python -m studyassistant mcp')
    fireEvent.click(screen.getByRole('button', { name: 'Copy command' }))
    expect(writeText).toHaveBeenCalledWith('python -m studyassistant mcp')
  })
})
