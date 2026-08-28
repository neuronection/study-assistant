import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import type { ChatToolCall, ChatTrace } from '@/lib/api'

import { TraceTimeline } from './TraceTimeline'

const trace: ChatTrace = {
  run_id: 'abc',
  model: 'gpt-4o',
  latency_ms: 2500,
  input_tokens: 40,
  output_tokens: 120,
  repair_rounds: 0,
  rounds: [
    { index: 0, streamed: true, start_ms: 0, duration_ms: 2000, phase: 'thinking' },
    { index: 1, streamed: false, start_ms: 2100, duration_ms: 400, phase: 'thinking' },
  ],
  thinking: 'I should apply the power rule.',
}

const toolCalls: ChatToolCall[] = [
  {
    name: 'CALC',
    argument: '2**10',
    result: '1024',
    start_ms: 2050,
    duration_ms: 5,
  },
]

describe('TraceTimeline', () => {
  test('shows a collapsed summary and expands on click', () => {
    render(<TraceTimeline trace={trace} toolCalls={toolCalls} />)
    const toggle = screen.getByRole('button', { name: 'Show response trace' })
    expect(toggle).toHaveTextContent('2.5 s')
    expect(toggle).toHaveTextContent('1 tools')
    expect(toggle).toHaveTextContent('gpt-4o')
    fireEvent.click(toggle)
    expect(screen.getByText('Total 2.5 s')).toBeInTheDocument()
    expect(screen.getByText('120 tokens')).toBeInTheDocument()
    expect(screen.getAllByText('Thinking').length).toBeGreaterThan(0)
  })

  test('renders tool rows and the reasoning disclosure', () => {
    render(<TraceTimeline trace={trace} toolCalls={toolCalls} />)
    fireEvent.click(screen.getByRole('button', { name: 'Show response trace' }))
    expect(screen.getByText('CALC')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Reasoning'))
    expect(screen.getByText('I should apply the power rule.')).toBeInTheDocument()
  })
})
