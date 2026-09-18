import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { ToolsDialog } from './ToolsDialog'
import type { AiToolInfo } from '@/lib/api'

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string) => key,
      i18n: actual.setDefaults,
    }),
  }
})

vi.mock('@/lib/ui-overlays', () => ({
  useCloseFloatings: () => {},
}))

const catalog: AiToolInfo[] = [
  {
    name: 'CALC',
    description: 'Numeric evaluation',
    example: 'CALC 1+1',
    arguments: [],
    response: 'number',
    scope: 'Chat answers',
    kind: 'tool',
  },
  {
    name: 'PROPOSE_EDITS',
    description: 'Propose study edits as approval cards',
    example: null,
    arguments: [],
    response: 'Approval card',
    scope: 'Chat answers',
    kind: 'capability',
    hitl: true,
  },
]

vi.mock('@/lib/api', () => ({
  listAiTools: vi.fn(() => Promise.resolve(catalog)),
}))

function renderDialog() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ToolsDialog onClose={() => {}} />
    </QueryClientProvider>,
  )
}

describe('ToolsDialog', () => {
  test('capability entries render with the HITL badge', async () => {
    renderDialog()
    expect(await screen.findByText('PROPOSE_EDITS')).toBeTruthy()
    const badges = await screen.findAllByText('chat.tools.hitlBadge')
    expect(badges).toHaveLength(1)
    const badge = badges[0].closest('[data-as="chat-tools-catalog-badge"]')
    expect(badge?.getAttribute('data-tone')).toBe('warning')
  })

  test('callable tools render without a badge', async () => {
    renderDialog()
    expect(await screen.findByText('CALC')).toBeTruthy()
    const calcRow = screen.getByText('CALC').closest('div')
    expect(calcRow?.textContent).not.toContain('chat.tools.hitlBadge')
  })
})
