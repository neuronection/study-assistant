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

  test('render failure cleans up only its own stray container and shows the source', async () => {
    renderMock.mockImplementation(async (id: string) => {
      const stray = document.createElement('div')
      stray.id = `d${id}`
      stray.textContent = 'Syntax error in text'
      document.body.appendChild(stray)
      const foreign = document.createElement('div')
      foreign.id = 'dmermaid-unrelated'
      foreign.textContent = 'another diagram in flight'
      document.body.appendChild(foreign)
      throw new Error('parse error')
    })
    render(<MermaidDiagram code={'flowchart TD\n    B[(x + 1)(x^2 - x + 1)]'} />)
    await waitFor(() =>
      expect(document.querySelector('pre')?.textContent).toContain('flowchart TD')
    )
    expect(document.getElementById('dmermaid-unrelated')).not.toBeNull()
    expect(document.getElementById('dmermaid-r0')).toBeNull()
  })

  test('renders are serialized, never concurrent', async () => {
    let active = 0
    let maxActive = 0
    renderMock.mockImplementation(
      async () =>
        new Promise((resolve) => {
          active += 1
          maxActive = Math.max(maxActive, active)
          setTimeout(() => {
            active -= 1
            resolve({ svg: `<svg data-testid="done-${active}"></svg>` })
          }, 40)
        })
    )
    render(<MermaidDiagram code="graph TD; A-->B" />)
    await waitFor(() => expect(document.querySelectorAll('svg').length).toBe(1))
    render(<MermaidDiagram code="graph TD; C-->D" />)
    await new Promise((resolve) => setTimeout(resolve, 20))
    render(<MermaidDiagram code="graph TD; E-->F" />)
    await waitFor(() => expect(document.querySelectorAll('svg').length).toBe(3))
    expect(maxActive).toBe(1)
  })

  test('a failed render recovers when the code is fixed', async () => {
    renderMock.mockImplementation(async () => {
      throw new Error('parse error')
    })
    const { rerender } = render(<MermaidDiagram code="broken ((" />)
    await waitFor(() => expect(document.querySelector('pre')).not.toBeNull())

    renderMock.mockImplementation(async () => ({ svg: '<svg data-testid="fixed"></svg>' }))
    rerender(<MermaidDiagram code="graph TD; A-->B" />)
    expect(await screen.findByTestId('fixed')).toBeInTheDocument()
    expect(document.querySelector('pre')).toBeNull()
  })

  test('reports the render error through onError (plan 64-C)', async () => {
    const onError = vi.fn()
    renderMock.mockImplementation(async () => {
      throw new Error('Parse error on line 2')
    })
    render(<MermaidDiagram code="broken ((" onError={onError} />)
    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith('Parse error on line 2')
    )
  })

  test('reports success through onSuccess (plan 64-C)', async () => {
    const onSuccess = vi.fn()
    renderMock.mockImplementation(async () => ({ svg: '<svg data-testid="ok2"></svg>' }))
    render(<MermaidDiagram code="graph TD; A-->B" onSuccess={onSuccess} />)
    await screen.findByTestId('ok2')
    expect(onSuccess).toHaveBeenCalled()
  })
})
