import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { McpConnectorsCard } from './McpConnectorsCard'

const listMcpServers = vi.fn()
const createMcpServer = vi.fn()
const updateMcpServer = vi.fn()
const deleteMcpServer = vi.fn()
const refreshMcpServer = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listMcpServers: () => listMcpServers(),
    createMcpServer: (body: unknown) => createMcpServer(body),
    updateMcpServer: (id: string, body: unknown) => updateMcpServer(id, body),
    deleteMcpServer: (id: string) => deleteMcpServer(id),
    refreshMcpServer: (id: string) => refreshMcpServer(id),
  }
})

const SERVER = {
  id: 'abc123',
  name: 'coursehub',
  command: 'python',
  args: ['-m', 'coursehub_server'],
  enabled: false,
  timeout_sec: 30,
  tools: [
    {
      name: 'search_courses',
      description: 'Search external courses',
      enabled: false,
      contract: 'none',
      url_pattern: null,
    },
  ],
  last_error: null,
  refreshed_at: null,
}

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <McpConnectorsCard />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  listMcpServers.mockReset().mockResolvedValue([SERVER])
  createMcpServer.mockReset()
  updateMcpServer.mockReset().mockResolvedValue(SERVER)
  deleteMcpServer.mockReset().mockResolvedValue(undefined)
  refreshMcpServer.mockReset().mockResolvedValue(SERVER)
})

describe('McpConnectorsCard', () => {
  test('lists servers with honest disabled state and command line', async () => {
    renderCard()
    expect(await screen.findByText('coursehub')).toBeInTheDocument()
    expect(screen.getByText('python -m coursehub_server')).toBeInTheDocument()
    expect(screen.getByText('Off')).toBeInTheDocument()
  })

  test('adding a server posts name, command and parsed args', async () => {
    createMcpServer.mockResolvedValue(SERVER)
    renderCard()
    fireEvent.click(await screen.findByRole('button', { name: /add server/i }))
    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'new-hub' },
    })
    fireEvent.change(screen.getByLabelText('Command'), {
      target: { value: '/usr/bin/python -m their_server' },
    })
    fireEvent.change(screen.getByLabelText(/arguments/i), {
      target: { value: '-m their_server --port 8080' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }))
    await waitFor(() =>
      expect(createMcpServer).toHaveBeenCalledWith({
        name: 'new-hub',
        command: '/usr/bin/python -m their_server',
        args: ['-m', 'their_server', '--port', '8080'],
      }),
    )
  })

  test('refresh lists tools that stay disabled until enabled', async () => {
    refreshMcpServer.mockResolvedValue(SERVER)
    renderCard()
    fireEvent.click(await screen.findByRole('button', { name: /refresh/i }))
    await waitFor(() => expect(refreshMcpServer).toHaveBeenCalledWith('abc123'))
    expect(
      screen.getByLabelText('Enabled: search_courses'),
    ).not.toBeChecked()
  })

  test('enabling a tool with the parse contract posts the patch', async () => {
    updateMcpServer.mockResolvedValue(SERVER)
    renderCard()
    fireEvent.click(await screen.findByRole('checkbox', { name: /enabled: search_courses/i }))
    await waitFor(() =>
      expect(updateMcpServer).toHaveBeenCalledWith('abc123', {
        tools: [{ name: 'search_courses', enabled: true }],
      }),
    )
    fireEvent.change(screen.getByLabelText(/contract: search_courses/i), {
      target: { value: 'parse' },
    })
    await waitFor(() =>
      expect(updateMcpServer).toHaveBeenCalledWith('abc123', {
        tools: [{ name: 'search_courses', contract: 'parse' }],
      }),
    )
  })

  test('delete removes the server', async () => {
    renderCard()
    fireEvent.click(await screen.findByRole('button', { name: /delete/i }))
    await waitFor(() => expect(deleteMcpServer).toHaveBeenCalledWith('abc123'))
  })
})
