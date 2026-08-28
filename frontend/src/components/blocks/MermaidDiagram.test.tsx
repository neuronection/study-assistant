import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { MermaidDiagram } from './MermaidDiagram'

const renderMock = vi.fn()

vi.mock('mermaid', () => ({
  default: {
    initialize: vi.fn(),
    render: (...args: unknown[]) => renderMock(...(args as [string, string])),
  },
}))

describe('MermaidDiagram', () => {
  test('renders the svg on success', async () => {
    renderMock.mockImplementation(async () => ({ svg: '<svg data-testid="ok"></svg>' }))
    render(<MermaidDiagram code="graph TD; A-->B" />)
    expect(await screen.findByTestId('ok')).toBeInTheDocument()
  })

  test('render failure sweeps stray error diagrams from the body and shows the source', async () => {
    renderMock.mockImplementation(async (id: string) => {
      const stray = document.createElement('div')
      stray.id = `d${id}`
      stray.textContent = 'Syntax error in text'
      document.body.appendChild(stray)
      throw new Error('parse error')
    })
    render(<MermaidDiagram code={'flowchart TD\n    B[(x + 1)(x^2 - x + 1)]'} />)
    await waitFor(() =>
      expect(document.querySelector('pre')?.textContent).toContain('flowchart TD')
    )
    expect(document.querySelectorAll('body > [id^="dmermaid-"]')).toHaveLength(0)
  })

  test('a failed render recovers when the code is fixed', async () => {
    const { rerender } = render(<MermaidDiagram code="broken ((" />)
    await waitFor(() => expect(document.querySelector('pre')).not.toBeNull())

    renderMock.mockImplementation(async () => ({ svg: '<svg data-testid="fixed"></svg>' }))
    rerender(<MermaidDiagram code="graph TD; A-->B" />)
    expect(await screen.findByTestId('fixed')).toBeInTheDocument()
    expect(document.querySelector('pre')).toBeNull()
  })
})
