import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { ConnectorsSection } from './ConnectorsSection'

const listMcpInfo = vi.fn()
const listCalendarProviders = vi.fn()
const listCalendarLinks = vi.fn()
const listCourses = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listMcpInfo: () => listMcpInfo(),
    listCalendarProviders: () => listCalendarProviders(),
    listCalendarLinks: () => listCalendarLinks(),
    listCourses: () => listCourses(),
  }
})

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ConnectorsSection />
    </QueryClientProvider>,
  )
}

describe('ConnectorsSection', () => {
  beforeEach(() => {
    listCalendarProviders.mockResolvedValue({ providers: [] })
    listCalendarLinks.mockResolvedValue([])
    listCourses.mockResolvedValue([])
  })

  test('renders the cloud calendars card', async () => {
    listMcpInfo.mockResolvedValue({ command: '', instructions: '', tools: [] })
    renderTab()
    expect(await screen.findByRole('heading', { name: 'Cloud calendars' })).toBeInTheDocument()
  })

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
