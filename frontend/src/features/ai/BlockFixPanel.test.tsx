import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import {
  BlockFixPanel,
  type BlockFixGateResult,
} from './BlockFixPanel'
import type { AiTextTransformTransport } from '@/components/ui/ai-text-transform'

function fakeTransport(
  result: string,
  options: { fail?: boolean; onDelta?: (text: string) => void } = {}
): AiTextTransformTransport {
  return {
    start: async () => {
      if (options.fail) {
        throw new Error('gateway down')
      }
      return 'job-1'
    },
    subscribe: (_jobId, handlers) => {
      queueMicrotask(() => {
        if (options.onDelta) {
          options.onDelta(result)
        }
        handlers.onDone(result)
      })
      return () => {}
    },
  }
}

const okGate = async (): Promise<BlockFixGateResult> => ({ ok: true })
const failGate = async (): Promise<BlockFixGateResult> => ({
  ok: false,
  error: 'Parse error on line 2',
})

describe('BlockFixPanel', () => {
  test('AI proposal that passes the gate enables Apply', async () => {
    const onApply = vi.fn()
    render(
      <BlockFixPanel
        kind="mermaid"
        source="flowchart LR\n    A"
        diagnostic="Parse error"
        validate={okGate}
        transport={fakeTransport('flowchart LR\n    A --> B')}
        onApply={onApply}
        onDiscard={() => {}}
      />
    )
    const apply = await screen.findByRole('button', { name: 'Use this fix' })
    await waitFor(() => expect(apply).not.toBeDisabled())
    fireEvent.click(apply)
    await waitFor(() => expect(onApply).toHaveBeenCalledWith('flowchart LR\n    A --> B'))
  })

  test('gate failure disables Apply and shows the renderer error', async () => {
    render(
      <BlockFixPanel
        kind="mermaid"
        source="broken"
        diagnostic="Parse error"
        validate={failGate}
        transport={fakeTransport('still broken')}
        onApply={() => {}}
        onDiscard={() => {}}
      />
    )
    expect(await screen.findByText('Renderer still rejects it')).toBeInTheDocument()
    expect(screen.getByText(/Parse error on line 2/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Use this fix' })).toBeDisabled()
  })

  test('tier-0 repair applies without calling the transport', async () => {
    const start = vi.fn(async () => 'job-1')
    const onApply = vi.fn()
    render(
      <BlockFixPanel
        kind="mermaid"
        source="flowchart LR\n    A"
        diagnostic="Parse error"
        validate={okGate}
        tier0Repair={async () => 'flowchart LR\n    A --> B'}
        transport={{
          start,
          subscribe: (_jobId, handlers) => {
            handlers.onDone('should never appear')
            return () => {}
          },
        }}
        onApply={onApply}
        onDiscard={() => {}}
      />
    )
    const apply = await screen.findByRole('button', { name: 'Use this fix' })
    await waitFor(() => expect(apply).not.toBeDisabled())
    fireEvent.click(apply)
    await waitFor(() => expect(onApply).toHaveBeenCalledWith('flowchart LR\n    A --> B'))
    expect(start).not.toHaveBeenCalled()
    expect(screen.getByText('Fixed without AI')).toBeInTheDocument()
  })

  test('the ask box routes to the AI with the user instruction (plan 64)', async () => {
    const start = vi.fn(async () => 'job-9')
    let aiDone: ((result: string) => void) | null = null
    const onApply = vi.fn()
    render(
      <BlockFixPanel
        kind="mermaid"
        source="flowchart LR\n    A"
        diagnostic="Parse error"
        validate={okGate}
        tier0Repair={async () => 'flowchart LR\n    A --> B'}
        transport={{
          start,
          subscribe: (_jobId, handlers) => {
            aiDone = handlers.onDone
            return () => {}
          },
        }}
        onApply={onApply}
        onDiscard={() => {}}
      />
    )

    await screen.findByText('Fixed without AI')
    expect(start).not.toHaveBeenCalled()

    fireEvent.change(await screen.findByLabelText('Ask the AI'), {
      target: { value: 'make the flow top-down' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Ask AI' }))

    await waitFor(() => expect(start).toHaveBeenCalledTimes(1))
    await waitFor(() => {
      expect(aiDone).not.toBeNull()
      aiDone?.('flowchart TD\n    A --> B')
    })
    expect(await screen.findByText('AI-proposed fix')).toBeInTheDocument()
    const apply = screen.getByRole('button', { name: 'Use this fix' })
    await waitFor(() => expect(apply).not.toBeDisabled())
    fireEvent.click(apply)
    await waitFor(() => expect(onApply).toHaveBeenCalledWith('flowchart TD\n    A --> B'))
  })

  test('transport failure renders the error state with retry', async () => {
    render(
      <BlockFixPanel
        kind="math"
        source="\\frac{1}{"
        diagnostic="KaTeX parseError"
        validate={okGate}
        transport={fakeTransport('', { fail: true })}
        onApply={() => {}}
        onDiscard={() => {}}
      />
    )
    expect(await screen.findByText('gateway down')).toBeInTheDocument()
  })
})
